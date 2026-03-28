#!/usr/bin/env python3
"""
Upcoming Movies & TV Shows for Kometa (UMTK)
Main entry point and orchestrator for UMTK and TSSK.
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path

from umtk.constants import VERSION, BLUE, GREEN, ORANGE, RED, RESET
from umtk.config_loader import load_config, load_localization
from umtk.updater import check_for_updates


def _get_config_dir():
    """Return the config directory path."""
    if os.environ.get('DOCKER') == 'true':
        return Path('/app/config')
    return Path(__file__).parent / 'config'


class _TeeToFile:
    """Write to both an original stream and a log file, stripping ANSI from the file copy."""

    _ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')

    def __init__(self, original, log_file):
        self._original = original
        self._log_file = log_file

    def write(self, data):
        if data:
            self._original.write(data)
            try:
                clean = self._ANSI_RE.sub('', data)
                self._log_file.write(clean)
                self._log_file.flush()
            except Exception:
                pass

    def flush(self):
        self._original.flush()
        try:
            self._log_file.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._original, name)


class _RunLogger:
    """Context manager that tees all stdout/stderr to a timestamped log file for a single run."""

    MAX_LOGS = 20

    def __init__(self):
        self._log_dir = _get_config_dir() / 'logs'
        self._log_file = None
        self._old_stdout = None
        self._old_stderr = None

    def __enter__(self):
        self._log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        log_path = self._log_dir / f'UMTK_{timestamp}.log'
        try:
            self._log_file = open(log_path, 'w', encoding='utf-8', errors='replace')
        except Exception:
            return self

        self._old_stdout = sys.stdout
        self._old_stderr = sys.stderr
        sys.stdout = _TeeToFile(self._old_stdout, self._log_file)
        sys.stderr = _TeeToFile(self._old_stderr, self._log_file)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._old_stdout is not None:
            sys.stdout = self._old_stdout
        if self._old_stderr is not None:
            sys.stderr = self._old_stderr
        if self._log_file is not None:
            try:
                self._log_file.close()
            except Exception:
                pass
        self._cleanup_old_logs()
        return False

    def _cleanup_old_logs(self):
        """Keep only the most recent MAX_LOGS log files."""
        try:
            log_files = sorted(self._log_dir.glob('UMTK_*.log'))
            if len(log_files) > self.MAX_LOGS:
                for old_file in log_files[:-self.MAX_LOGS]:
                    try:
                        old_file.unlink()
                    except Exception:
                        pass
        except Exception:
            pass


def run():
    """Run UMTK and/or TSSK based on config enable flags."""
    with _RunLogger():
        _run_inner()


def _run_inner():
    """The actual run logic, wrapped by run() for per-run logging."""
    print(f"{BLUE}{'*' * 50}")
    print(f"{'*' * 1}Upcoming Movies & TV Shows for Kometa {VERSION}{'*' * 1}")
    print(f"{'*' * 50}{RESET}")

    check_for_updates()

    # Load shared config and localization
    config = load_config()
    localization = load_localization()

    # Determine what to run
    enable_umtk = str(config.get('enable_umtk', 'true')).lower() == 'true'
    enable_tssk = str(config.get('enable_tssk', 'false')).lower() == 'true'

    if not enable_umtk and not enable_tssk:
        print(f"{ORANGE}Both enable_umtk and enable_tssk are disabled. Nothing to do.{RESET}")
        return

    umtk_success = True
    tssk_success = True

    # ---- Run UMTK ----
    if enable_umtk:
        try:
            from umtk.main import main as umtk_main
            umtk_main(config, localization)
        except Exception as e:
            print(f"\n{RED}UMTK failed: {e}{RESET}")
            umtk_success = False
    else:
        print(f"{ORANGE}UMTK is disabled (enable_umtk: false){RESET}")

    # ---- Run TSSK ----
    if enable_tssk:
        print(f"\n{BLUE}{'=' * 50}{RESET}")
        print(f"{BLUE}Starting TSSK (TV Show Status for Kometa)...{RESET}")
        print(f"{BLUE}{'=' * 50}{RESET}")

        try:
            from tssk.config_loader import load_tssk_config
            from tssk.main import run_tssk

            tssk_config = load_tssk_config()
            if tssk_config is None:
                print(f"{RED}TSSK skipped: could not load tssk_config.yml{RESET}")
                tssk_success = False
            else:
                # Inject shared credentials from UMTK config
                shared_keys = [
                    'sonarr_url', 'sonarr_api_key', 'sonarr_timeout',
                    'plex_url', 'plex_token', 'tv_libraries',
                    'utc_offset', 'debug', 'simplify_next_week_dates'
                ]
                for key in shared_keys:
                    if key in config:
                        tssk_config[key] = config[key]

                run_tssk(tssk_config, localization)
        except Exception as e:
            print(f"\n{RED}TSSK failed: {e}{RESET}")
            tssk_success = False
    else:
        print(f"\n{ORANGE}TSSK is disabled (enable_tssk: false){RESET}")

    # Summary
    if enable_umtk and enable_tssk:
        print(f"\n{BLUE}{'=' * 50}{RESET}")
        umtk_status = f"{GREEN}OK{RESET}" if umtk_success else f"{RED}FAILED{RESET}"
        tssk_status = f"{GREEN}OK{RESET}" if tssk_success else f"{RED}FAILED{RESET}"
        print(f"UMTK: {umtk_status}  |  TSSK: {tssk_status}")
        print(f"{BLUE}{'=' * 50}{RESET}")

    if not umtk_success or not tssk_success:
        raise RuntimeError("One or more modules failed")


if __name__ == "__main__":
    try:
        from umtk.scheduler_state import SchedulerState
        from umtk.scheduler import get_cron_schedule, run_on_schedule

        sched_state = SchedulerState(config_dir="config")

        # Start web UI if available
        try:
            from webui import start_webui
            start_webui(scheduler_state=sched_state)
        except ImportError:
            pass
        except Exception as e:
            print(f"{ORANGE}Web UI not started: {e}{RESET}")

        # Check for CRON scheduling
        cron = get_cron_schedule()
        if cron:
            print(f"CRON scheduling enabled: {cron}")
            run_on_schedule(cron, run, state=sched_state)
            # run_on_schedule never returns
        else:
            # Single run mode
            sched_state.set_status("running")
            try:
                run()
                if sched_state.status != "error":
                    sched_state.set_status("idle")
            except Exception as e:
                sched_state.set_status("error", str(e))

            # If running in Docker without CRON, keep alive so Web UI stays accessible
            if os.environ.get('DOCKER') == 'true':
                sched_state._has_cron = True  # show Run Now / Stop controls in the UI
                if sched_state.status == "error":
                    print(f"{ORANGE}Run failed but Web UI remains available at port 2120.{RESET}")
                    print(f"{ORANGE}Fix your config in the Web UI and use 'Run Now' to retry.{RESET}")
                while True:
                    sched_state._wake_event.wait()
                    sched_state._wake_event.clear()
                    if sched_state.is_run_requested():
                        sched_state.clear_run_request()
                        sched_state.set_status("running")
                        try:
                            run()
                            if sched_state.status != "error":
                                sched_state.set_status("idle")
                        except Exception as e2:
                            sched_state.set_status("error", str(e2))
                        sched_state.set_last_run(datetime.now())
            elif sched_state.status == "error":
                sys.exit(1)

    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(0)
