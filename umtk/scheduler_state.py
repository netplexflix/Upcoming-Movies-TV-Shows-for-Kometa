"""Thread-safe shared state between the scheduler and web UI."""

import json
import os
import threading
import time
from datetime import datetime
from typing import Optional


class SchedulerState:
    """Thread-safe shared state between the scheduler (main thread) and web UI (daemon thread)."""

    def __init__(self, config_dir: str = "config") -> None:
        self._lock = threading.Lock()
        self._config_dir = config_dir

        # Current state
        self._status: str = "idle"          # running | idle | stopped | error
        self._error_message: str = ""
        self._next_run_time: Optional[datetime] = None
        self._last_run_time: Optional[datetime] = None
        self._cron_expression: Optional[str] = None
        self._has_cron: bool = False
        self._started_at: Optional[datetime] = None
        self._last_run_summary: Optional[dict] = None

        # Cross-thread signaling
        self._wake_event = threading.Event()
        self._run_requested = threading.Event()
        self._stop_requested = threading.Event()

    # ── Getters ───────────────────────────────────────────────────────────

    def get_status_dict(self) -> dict:
        """Return a snapshot of the current state for the API."""
        with self._lock:
            now = datetime.now()
            next_run_iso = None
            next_run_seconds = None
            if self._next_run_time:
                next_run_iso = self._next_run_time.strftime("%Y-%m-%dT%H:%M:%S")
                delta = (self._next_run_time - now).total_seconds()
                next_run_seconds = max(0, int(delta))

            last_run_iso = None
            if self._last_run_time:
                last_run_iso = self._last_run_time.strftime("%Y-%m-%dT%H:%M:%S")

            started_at_iso = None
            if self._started_at:
                started_at_iso = self._started_at.strftime("%Y-%m-%dT%H:%M:%S")

            return {
                "status": self._status,
                "next_run_time": next_run_iso,
                "next_run_seconds": next_run_seconds,
                "last_run_time": last_run_iso,
                "started_at": started_at_iso,
                "cron_expression": self._cron_expression,
                "has_cron": self._has_cron,
                "error_message": self._error_message,
                "last_run_summary": self._last_run_summary,
            }

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    # ── Setters ───────────────────────────────────────────────────────────

    def set_status(self, status: str, message: str = "") -> None:
        with self._lock:
            self._status = status
            self._error_message = message
            if status == "running":
                self._started_at = datetime.now()
            elif status != "running":
                self._started_at = None
        self._save_status()

    def set_next_run(self, dt: Optional[datetime]) -> None:
        with self._lock:
            self._next_run_time = dt

    def set_last_run(self, dt: Optional[datetime]) -> None:
        with self._lock:
            self._last_run_time = dt

    def set_cron(self, expression: str) -> None:
        with self._lock:
            self._cron_expression = expression
            self._has_cron = True

    def set_last_run_summary(self, summary: dict) -> None:
        with self._lock:
            self._last_run_summary = summary

    # ── Event helpers ─────────────────────────────────────────────────────

    def is_stopped(self) -> bool:
        return self._stop_requested.is_set()

    def is_run_requested(self) -> bool:
        return self._run_requested.is_set()

    def clear_run_request(self) -> None:
        self._run_requested.clear()

    def wake(self) -> None:
        """Wake the scheduler from its interruptible sleep."""
        self._wake_event.set()

    # ── Commands (called by web UI) ───────────────────────────────────────

    def request_run(self) -> None:
        """Signal the scheduler to execute a run immediately."""
        self._run_requested.set()
        self._wake_event.set()

    def request_stop(self) -> None:
        """Signal the scheduler to pause after the current run completes."""
        self._stop_requested.set()
        self._wake_event.set()

    def request_resume(self) -> None:
        """Signal the scheduler to resume CRON scheduling."""
        self._stop_requested.clear()
        self._wake_event.set()

    # ── Persistence ───────────────────────────────────────────────────────

    def _save_status(self) -> None:
        """Write current status to config/status.json (atomic)."""
        status_path = os.path.join(self._config_dir, "status.json")
        tmp_path = status_path + ".tmp"
        try:
            os.makedirs(self._config_dir, exist_ok=True)
            data = self.get_status_dict()
            data["updated_at"] = time.time()
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            os.replace(tmp_path, status_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
