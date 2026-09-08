"""Cron-like scheduling engine for profiles and workflows.

Pure stdlib. Expressions use the standard 5-field cron form:

    minute hour day-of-month month day-of-week

Fields support ``*``, lists (``a,b``), ranges (``a-b``), and steps
(``*/n``, ``a-b/n``, ``a/n``). Day-of-week is 0=Sunday..6=Saturday with
7 accepted as Sunday. As in classic cron, when both day-of-month and
day-of-week are restricted, a day matches if either field matches.

The scheduler itself is a daemon thread that ticks every
SCHEDULER_TICK_SECONDS and starts runs through the same code path as the
web UI, so scheduled runs show up in history and the run modal.
"""
import logging
import threading
from datetime import datetime, timedelta

log = logging.getLogger("launcher.scheduler")

FIELD_RANGES = {
    "minute": (0, 59),
    "hour": (0, 23),
    "dom": (1, 31),
    "month": (1, 12),
    "dow": (0, 7),  # 7 accepted and normalized to 0 (Sunday)
}

_FIELD_ORDER = ("minute", "hour", "dom", "month", "dow")

# Upper bound for the next-run day scan; covers leap years and rejects
# impossible expressions (e.g. 0 0 31 2 *) with a clean None instead of
# an infinite loop.
_MAX_SCAN_DAYS = 5 * 366 + 2

_DAY_NAMES = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")


def _parse_int(token, field):
    try:
        return int(token)
    except ValueError:
        raise ValueError(f"invalid number {token!r} in {field} field")


def _parse_field(token, field):
    lo, hi = FIELD_RANGES[field]
    values = set()
    for part in token.split(","):
        if not part:
            raise ValueError(f"empty list item in {field} field")
        step = 1
        range_part = part
        if "/" in part:
            range_part, _, step_text = part.partition("/")
            step = _parse_int(step_text, field)
            if step < 1:
                raise ValueError(f"step must be >= 1 in {field} field")
        if range_part == "*":
            start, end = lo, hi
        elif "-" in range_part:
            start_text, _, end_text = range_part.partition("-")
            start = _parse_int(start_text, field)
            end = _parse_int(end_text, field)
        else:
            start = _parse_int(range_part, field)
            end = hi if "/" in part else start
        if start < lo or end > hi or start > end:
            raise ValueError(f"value {range_part!r} out of range for {field} field")
        if step > (hi - lo):
            raise ValueError(f"step {step} too large for {field} field")
        values.update(range(start, end + 1, step))
    if not values:
        raise ValueError(f"{field} field matches no values")
    if field == "dow" and 7 in values:
        values.discard(7)
        values.add(0)
    return values


def parse_cron(expr):
    """Parse a 5-field cron expression into sets per field.

    Raises ValueError with a human-readable message on invalid input.
    """
    if not isinstance(expr, str) or not expr.strip():
        raise ValueError("cron expression must be a non-empty string")
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(f"cron expression must have 5 fields, got {len(fields)}")
    return {
        field: _parse_field(token, field)
        for field, token in zip(_FIELD_ORDER, fields)
    }


def _cron_dow(date):
    """Cron day-of-week (0=Sunday) for a date. Python's Monday=0 offset by 1."""
    return (date.weekday() + 1) % 7


def _day_matches(date, doms, dows, dom_wild, dow_wild):
    if dom_wild and dow_wild:
        return True
    if dom_wild:
        return _cron_dow(date) in dows
    if dow_wild:
        return date.day in doms
    return date.day in doms or _cron_dow(date) in dows


def next_after(expr, now=None):
    """Next fire time strictly after ``now`` (naive local time), or None.

    ``expr`` may be a raw cron string or a dict from parse_cron.
    """
    fields = parse_cron(expr) if isinstance(expr, str) else expr
    t = (now or datetime.now()).replace(second=0, microsecond=0) + timedelta(minutes=1)
    minutes = sorted(fields["minute"])
    hours = sorted(fields["hour"])
    doms = fields["dom"]
    months = fields["month"]
    dows = fields["dow"]
    dom_wild = doms == set(range(1, 32))
    dow_wild = dows == set(range(7))
    date = t.date()
    for _ in range(_MAX_SCAN_DAYS):
        if date.month in months and _day_matches(date, doms, dows, dom_wild, dow_wild):
            base = datetime(date.year, date.month, date.day)
            if date == t.date():
                for h in hours:
                    if h < t.hour:
                        continue
                    if h == t.hour:
                        for m in minutes:
                            if m >= t.minute:
                                return base.replace(hour=h, minute=m)
                    else:
                        return base.replace(hour=h, minute=minutes[0])
            else:
                return base.replace(hour=hours[0], minute=minutes[0])
        date += timedelta(days=1)
    return None


def describe_cron(expr):
    """Human-readable description of a cron expression (raw text if unknown)."""
    try:
        fields = parse_cron(expr)
    except (ValueError, AttributeError):
        return expr if isinstance(expr, str) else ""
    minute = fields["minute"]
    hour = fields["hour"]
    dom = fields["dom"]
    dow = fields["dow"]
    dom_wild = dom == set(range(1, 32))
    dow_wild = dow == set(range(7))
    month_wild = fields["month"] == set(range(1, 13))
    if not month_wild:
        return expr
    minute_sorted = sorted(minute)
    hour_sorted = sorted(hour)
    if minute == set(range(60)) and hour == set(range(24)):
        return "Every minute"
    if len(minute_sorted) > 1:
        step = minute_sorted[1] - minute_sorted[0]
        if step > 1 and minute == set(range(0, 60, step)) and hour == set(range(24)):
            return f"Every {step} minutes"
    if hour == set(range(24)):
        if minute == {0}:
            return "Every hour"
        if len(minute) == 1:
            return f"Every hour at :{minute_sorted[0]:02d}"
    if len(minute_sorted) == 1 and len(hour_sorted) > 1:
        step = hour_sorted[1] - hour_sorted[0]
        if step > 1 and hour == set(range(0, 24, step)):
            m = minute_sorted[0]
            return f"Every {step} hours" if m == 0 else f"Every {step} hours at :{m:02d}"
    if len(minute) == 1 and len(hour) == 1:
        m = next(iter(minute))
        h = next(iter(hour))
        time_text = f"{h:02d}:{m:02d}"
        if dom_wild and dow_wild:
            return f"Daily at {time_text}"
        if dom_wild and not dow_wild:
            days = sorted(dow)
            if days == [1, 2, 3, 4, 5]:
                return f"Weekdays at {time_text}"
            names = [_DAY_NAMES[d] + ("s" if len(days) > 1 else "") for d in days]
            if len(names) == 1:
                return f"Weekly on {names[0]} at {time_text}"
            return f"{' & '.join(names)} at {time_text}"
        if dow_wild and len(dom) == 1:
            return f"Monthly on day {next(iter(dom))} at {time_text}"
    if dow_wild and len(dom) > 1:
        dom_sorted = sorted(dom)
        step = dom_sorted[1] - dom_sorted[0]
        if step > 1 and dom == set(range(1, 32, step)) and len(minute_sorted) == 1 and len(hour_sorted) == 1:
            m = minute_sorted[0]
            h = hour_sorted[0]
            suffix = "" if (m == 0 and h == 0) else f" at {h:02d}:{m:02d}"
            return f"Every {step} days{suffix}"
    return expr


def _ts(dt):
    return dt.timestamp() if dt else None


# Run id of the most recent run started per schedule id, used to avoid
# starting a new run while the previous one is still active.
_last_scheduled_run = {}
_state_lock = threading.Lock()

_thread = None
_stop = threading.Event()


def fire_schedule(schedule):
    """Start a run for a schedule. Returns the run_id, or None if skipped.

    Skips (with a log line) when the target no longer exists or sits in
    the trash; the schedule's next_run_at still advances so this is not
    retried until the next due occurrence.
    """
    from .storage import load_json
    from .config import COL_PROFILES, COL_WORKFLOWS
    from .api import runs

    target_type = schedule.get("target_type", "profile")
    target_id = schedule.get("target_id")
    column = COL_WORKFLOWS if target_type == "workflow" else COL_PROFILES
    target = next((i for i in load_json(column) if i.get("id") == target_id), None)
    if not target or target.get("group") == "__trash__":
        log.warning(
            "Schedule %s: target %s %s is missing or trashed - skipping",
            schedule.get("id"), target_type, target_id,
        )
        return None
    if target_type == "workflow":
        result, error = runs.start_workflow_run(target, trigger="scheduled", schedule=schedule)
    else:
        result, error = runs.start_profile_run(target, trigger="scheduled", schedule=schedule)
    if error:
        log.warning("Schedule %s: could not start run: %s", schedule.get("id"), error.get("error"))
        return None
    run_id = result["run_id"]
    with _state_lock:
        _last_scheduled_run[schedule.get("id")] = run_id
    return run_id


def _schedule_busy(schedule):
    """True if the previous run started by this schedule is still active."""
    with _state_lock:
        run_id = _last_scheduled_run.get(schedule.get("id"))
    if not run_id:
        return False
    from .api import runs
    with runs.run_lock:
        info = runs.active_runs.get(run_id)
    if info and info.get("status") == "running":
        return True
    with _state_lock:
        _last_scheduled_run.pop(schedule.get("id"), None)
    return False


def run_tick(now=None, fire=None):
    """One scheduler pass. Returns a list of (schedule_id, run_id) fired.

    Loads the schedules collection fresh so API edits take effect within
    one tick, recomputes missing next_run_at values, and fires every
    enabled schedule whose next_run_at has passed.
    """
    from .storage import load_json, save_json, collection_lock
    from .config import COL_SCHEDULES

    now = now or datetime.now()
    fire = fire or fire_schedule
    now_ts = now.timestamp()
    # The whole load-fire-save pass holds the schedules collection lock so
    # it cannot interleave with API edits and lose them.
    with collection_lock(COL_SCHEDULES):
        schedules = load_json(COL_SCHEDULES)
        fired = []
        changed = False
        for sched in schedules:
            if not sched.get("enabled"):
                continue
            try:
                expr = sched.get("cron", "")
                fields = parse_cron(expr)
                next_run = sched.get("next_run_at")
                if next_run is None:
                    sched["next_run_at"] = _ts(next_after(fields, now))
                    changed = True
                    continue
                if next_run > now_ts:
                    continue
                if _schedule_busy(sched):
                    continue
                run_id = fire(sched)
                if run_id:
                    sched["last_run_at"] = now_ts
                    sched["last_run_id"] = run_id
                    sched["last_status"] = None
                    fired.append((sched.get("id"), run_id))
                sched["next_run_at"] = _ts(next_after(fields, now))
                changed = True
            except Exception:
                log.exception("Scheduler tick failed for schedule %s", sched.get("id"))
        if changed:
            save_json(COL_SCHEDULES, schedules)
    return fired


def _skip_missed(now=None):
    """Recompute stale next_run_at values without firing (skip missed runs).

    Called on server start: any due time that passed while the server was
    down is skipped and the next occurrence is scheduled instead.
    """
    from .storage import load_json, save_json, collection_lock
    from .config import COL_SCHEDULES

    now = now or datetime.now()
    now_ts = now.timestamp()
    with collection_lock(COL_SCHEDULES):
        schedules = load_json(COL_SCHEDULES)
        changed = False
        for sched in schedules:
            if not sched.get("enabled"):
                continue
            next_run = sched.get("next_run_at")
            if next_run is not None and next_run > now_ts:
                continue
            try:
                fields = parse_cron(sched.get("cron", ""))
            except ValueError:
                continue
            sched["next_run_at"] = _ts(next_after(fields, now))
            changed = True
        if changed:
            save_json(COL_SCHEDULES, schedules)


def _loop():
    from .config import SCHEDULER_TICK_SECONDS
    while not _stop.wait(SCHEDULER_TICK_SECONDS):
        try:
            run_tick()
        except Exception:
            log.exception("Scheduler tick failed")


def start():
    """Start the scheduler daemon thread (no-op if already running)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _skip_missed()
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="launcher-scheduler", daemon=True)
    _thread.start()
    log.info("Scheduler started")


def stop():
    """Signal the scheduler thread to exit after the current tick."""
    _stop.set()
