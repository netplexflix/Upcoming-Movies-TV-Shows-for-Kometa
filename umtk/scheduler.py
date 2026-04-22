"""Scheduling for UMTK (dual-mode: hours interval or cron).

Schedule source-of-truth order:
    config.yml  >  env vars (CRON / CRON_SCHEDULE / SCHEDULE_HOURS)  >  default (24h)

On first launch, env-var values are persisted back to config.yml so the
Web UI can render them and the user can edit them live without a restart.
"""

import os
import time
from datetime import datetime, timedelta
from typing import Optional, Callable


def format_wait(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


def _load_initial_schedule(state, config_path: str) -> None:
    """Seed the scheduler state from config.yml, falling back to env vars.

    Precedence: config.yml > env vars (CRON / CRON_SCHEDULE / SCHEDULE_HOURS)
    > default (hours=24). When a schedule was resolved from env vars, it is
    persisted back to config.yml so the Web UI always has values to render
    and future restarts use config (not env).
    """
    try:
        from croniter import croniter
    except ImportError:
        print("croniter package not installed — scheduling disabled.")
        return

    import yaml  # lazy: only needed in scheduled mode

    # Read existing config
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except Exception:
        config = {}

    cfg_type = (config.get("schedule_type") or "").strip().lower()
    cfg_hours = config.get("schedule_hours")
    cfg_cron = (config.get("schedule_cron") or "").strip()

    schedule_type: Optional[str] = None
    schedule_hours: int = 24
    cron_expr: str = ""

    if cfg_type in ("hours", "cron"):
        # Config is the source of truth
        schedule_type = cfg_type
        if cfg_type == "hours":
            try:
                schedule_hours = int(cfg_hours) if cfg_hours is not None else 24
            except (TypeError, ValueError):
                schedule_hours = 24
            if schedule_hours < 1:
                schedule_hours = 24
        else:
            cron_expr = cfg_cron
            if not croniter.is_valid(cron_expr):
                print(f"Invalid schedule_cron in config.yml: {cron_expr} — falling back to hours=24")
                schedule_type = "hours"
                schedule_hours = 24
                cron_expr = ""
    else:
        # Fall back to env vars (initial defaults on first launch)
        env_cron = os.environ.get("CRON", "").strip()
        if not env_cron:
            env_cron = os.environ.get("CRON_SCHEDULE", "").strip()
        if env_cron:
            if croniter.is_valid(env_cron):
                schedule_type = "cron"
                cron_expr = env_cron
            else:
                print(f"Invalid CRON env var: {env_cron} — falling back to SCHEDULE_HOURS")
        if schedule_type is None:
            schedule_type = "hours"
            try:
                schedule_hours = int(os.environ.get("SCHEDULE_HOURS", "24"))
            except (TypeError, ValueError):
                schedule_hours = 24
            if schedule_hours < 1:
                schedule_hours = 24

        # Persist resolved values back into config.yml so the Settings page
        # has values to render and future restarts use config (not env).
        try:
            config["schedule_type"] = schedule_type
            config["schedule_hours"] = schedule_hours
            config["schedule_cron"] = cron_expr
            from webui.routes import _save_yaml
            _save_yaml(config_path, config)
        except Exception as e:
            print(f"Could not persist initial schedule to config.yml: {e}")

    if schedule_type == "cron":
        print(f"Using CRON schedule: {cron_expr}")
    else:
        print(f"Will run every {schedule_hours} hours")

    if state is not None:
        state.update_schedule(schedule_type, schedule_hours, cron_expr)
        # update_schedule sets the schedule_changed flag; clear it because the
        # initial seeding is not a "live edit" — the loop hasn't started yet.
        state.clear_schedule_changed()


def run_on_schedule(run_fn: Callable, state=None) -> None:
    """
    Execute run_fn immediately, then re-execute on the configured schedule.
    Blocks forever (designed for Docker entrypoint use).

    The active schedule (hours-interval or cron) is pulled fresh from *state*
    on every loop iteration, so live edits from the Web UI take effect on the
    next pass without a container restart.
    """
    from croniter import croniter

    # Run immediately on start
    print("=" * 60)
    print("UMTK – Initial run on container start")
    print("=" * 60)
    if state is not None:
        state.set_status("running")
    try:
        run_fn()
        if state is not None:
            state.set_last_run(datetime.now())
            if state.status != "error":
                state.set_status("idle")
    except Exception as e:
        print(f"Initial run failed: {e}")
        print("The Web UI remains available — fix your config and trigger a new run.")
        if state is not None:
            state.set_status("error", str(e))
            state.set_last_run(datetime.now())

    # Schedule loop
    while True:
        # Stopped state: wait until resumed or run-now
        if state is not None and state.is_stopped():
            state.set_status("stopped")
            print(f"\n{'=' * 60}")
            print("UMTK – Scheduler paused by user")
            print(f"{'=' * 60}\n")
            state._wake_event.wait()
            state._wake_event.clear()
            if state.is_run_requested():
                state.clear_run_request()
            elif state.is_stopped():
                continue
            else:
                continue
        else:
            # Read the active schedule fresh each iteration so live edits
            # from the Web UI take effect on the next loop pass.
            if state is not None:
                schedule_type, schedule_hours, cron_expr = state.get_schedule()
            else:
                schedule_type = "hours"
                schedule_hours = int(os.environ.get("SCHEDULE_HOURS", "24"))
                cron_expr = ""

            now = datetime.now()
            if schedule_type == "cron" and cron_expr:
                nxt = croniter(cron_expr, now).get_next(datetime)
                wait_seconds = (nxt - now).total_seconds()
            else:
                nxt = now + timedelta(hours=schedule_hours)
                wait_seconds = schedule_hours * 3600

            if state is not None:
                state.set_next_run(nxt)
                state.set_status("idle")
                state.clear_schedule_changed()

            print(f"\n{'=' * 60}")
            print(f"Next scheduled run: {nxt.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Waiting {format_wait(wait_seconds)}...")
            print(f"{'=' * 60}\n")

            # Interruptible wait
            if state is not None:
                woken = state._wake_event.wait(timeout=max(0, wait_seconds))
                state._wake_event.clear()

                if state.is_stopped():
                    continue
                if state.is_schedule_changed():
                    state.clear_schedule_changed()
                    continue
                if state.is_run_requested():
                    state.clear_run_request()
                elif not woken:
                    pass  # timeout reached, time for scheduled run
                else:
                    continue
            else:
                time.sleep(max(0, wait_seconds))

        # Execute
        print("=" * 60)
        print(f"UMTK – Scheduled run at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        if state is not None:
            state.set_status("running")
        try:
            run_fn()
            if state is not None and state.status != "error":
                state.set_status("idle")
        except Exception as e:
            print(f"Scheduled run failed: {e}")
            print("The Web UI remains available — fix your config and trigger a new run.")
            if state is not None:
                state.set_status("error", str(e))
        if state is not None:
            state.set_last_run(datetime.now())


def get_cron_schedule() -> Optional[str]:
    """Legacy helper: read CRON or CRON_SCHEDULE from environment.

    Kept for backwards compatibility with any callers outside UMTK.py; the
    main entry point now uses _load_initial_schedule() instead.
    """
    val = os.environ.get("CRON_SCHEDULE", "").strip()
    if not val:
        val = os.environ.get("CRON", "").strip()
    return val if val else None
