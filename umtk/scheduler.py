"""CRON-based scheduling for UMTK."""

import os
import time
from datetime import datetime, timedelta
from typing import Optional, Callable


def _parse_cron_field(field: str, min_val: int, max_val: int) -> list:
    """Parse a single CRON field into a sorted list of matching integers."""
    values = set()

    for part in field.split(","):
        part = part.strip()

        if part.startswith("*/"):
            step = int(part[2:])
            values.update(range(min_val, max_val + 1, step))
        elif part == "*":
            values.update(range(min_val, max_val + 1))
        elif "-" in part:
            if "/" in part:
                range_part, step_part = part.split("/")
                lo, hi = map(int, range_part.split("-"))
                step = int(step_part)
                values.update(range(lo, hi + 1, step))
            else:
                lo, hi = map(int, part.split("-"))
                values.update(range(lo, hi + 1))
        else:
            values.add(int(part))

    return sorted(v for v in values if min_val <= v <= max_val)


def _convert_dow(cron_dows: list) -> set:
    """Convert CRON day-of-week (0=Sunday) to Python weekday (0=Monday)."""
    mapping = {0: 6, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}
    return {mapping[d] for d in cron_dows}


def next_cron_time(cron_expr: str, after: Optional[datetime] = None) -> datetime:
    """Return the next datetime matching cron_expr (5-field: min hour dom month dow)."""
    fields = cron_expr.strip().split()
    if len(fields) != 5:
        raise ValueError(f"CRON expression must have 5 fields, got {len(fields)}: '{cron_expr}'")

    minutes = _parse_cron_field(fields[0], 0, 59)
    hours = _parse_cron_field(fields[1], 0, 23)
    doms = _parse_cron_field(fields[2], 1, 31)
    months = _parse_cron_field(fields[3], 1, 12)
    dows = _parse_cron_field(fields[4], 0, 6)

    if after is None:
        after = datetime.now()

    candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    max_search = after + timedelta(days=366 * 2)

    while candidate < max_search:
        if (candidate.month in months
                and candidate.day in doms
                and candidate.weekday() in _convert_dow(dows)
                and candidate.hour in hours
                and candidate.minute in minutes):
            return candidate
        candidate += timedelta(minutes=1)

    raise ValueError(f"No matching time found for CRON expression: '{cron_expr}'")


def format_wait(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


def run_on_schedule(cron_expr: str, run_fn: Callable, state=None) -> None:
    """
    Execute run_fn immediately, then re-execute at every CRON match.
    Blocks forever (designed for Docker entrypoint use).
    """
    if state is not None:
        state.set_cron(cron_expr)

    # Validate expression early
    nxt = next_cron_time(cron_expr)
    print(f"Next scheduled run: {nxt.strftime('%Y-%m-%d %H:%M')}")

    # Run immediately on start
    print("=" * 60)
    print(f"UMTK – Initial run on container start")
    print("=" * 60)
    if state is not None:
        state.set_status("running")
    try:
        run_fn()
        if state is not None:
            state.set_last_run(datetime.now())
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

        # Calculate next CRON time
        else:
            now = datetime.now()
            nxt = next_cron_time(cron_expr, after=now)
            wait_seconds = (nxt - now).total_seconds()

            if state is not None:
                state.set_next_run(nxt)
                state.set_status("idle")

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
                if state.is_run_requested():
                    state.clear_run_request()
                elif not woken:
                    pass
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
        except Exception as e:
            print(f"Scheduled run failed: {e}")
            print("The Web UI remains available — fix your config and trigger a new run.")
            if state is not None:
                state.set_status("error", str(e))
        if state is not None:
            state.set_last_run(datetime.now())


def get_cron_schedule() -> Optional[str]:
    """Read CRON or CRON_SCHEDULE from environment. Returns None if not set."""
    val = os.environ.get("CRON_SCHEDULE", "").strip()
    if not val:
        val = os.environ.get("CRON", "").strip()
    return val if val else None
