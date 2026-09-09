import copy
import functools
import time
import uuid
from datetime import datetime

from ..storage import load_json, save_json, record_audit, changed_fields, collection_lock
from ..config import COL_SCHEDULES, COL_PROFILES, COL_WORKFLOWS
from .. import scheduler
from ..scheduler import parse_cron, next_after, describe_cron

PREVIEW_COUNT = 3


def _locked(fn):
    """Serialize read-modify-write access to the schedules collection."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with collection_lock(COL_SCHEDULES):
            return fn(*args, **kwargs)
    return wrapper


def _find_target(target_type, target_id):
    column = COL_WORKFLOWS if target_type == "workflow" else COL_PROFILES
    return next((i for i in load_json(column) if i.get("id") == target_id), None)


def _audit_name(schedule):
    if schedule.get("name"):
        return schedule["name"]
    target = _find_target(schedule.get("target_type", "profile"), schedule.get("target_id"))
    return target.get("name") if target else None


def _enrich(schedule):
    out = dict(schedule)
    target = _find_target(schedule.get("target_type", "profile"), schedule.get("target_id"))
    out["target_name"] = target.get("name") if target else None
    out["target_trashed"] = bool(target and target.get("group") == "__trash__")
    out["description"] = describe_cron(schedule.get("cron", ""))
    return out


def handle_list():
    return [_enrich(s) for s in load_json(COL_SCHEDULES)]


def _validate(data):
    cron = data.get("cron", "")
    try:
        parse_cron(cron)
    except ValueError as e:
        return f"Invalid cron expression: {e}"
    target_type = data.get("target_type", "profile")
    if target_type not in ("profile", "workflow"):
        return "target_type must be 'profile' or 'workflow'"
    target = _find_target(target_type, data.get("target_id"))
    if not target:
        return "Target not found"
    if target.get("group") == "__trash__":
        return "Target is in the trash"
    return None


def _next_run_at(cron_expr):
    try:
        nxt = next_after(cron_expr)
    except ValueError:
        return None
    return nxt.timestamp() if nxt else None


@_locked
def handle_create(data):
    """Create or update a schedule. Returns (schedule, error)."""
    error = _validate(data)
    if error:
        return None, {"error": error}

    schedules = load_json(COL_SCHEDULES)
    existing = next((s for s in schedules if s.get("id") == data.get("id")), None)
    before = copy.deepcopy(existing) if existing else None

    if existing:
        schedule = copy.deepcopy(existing)
    else:
        schedule = {
            "id": f"sched_{uuid.uuid4().hex[:12]}",
            "created_at": time.time(),
            "last_run_at": None,
            "last_run_id": None,
            "last_status": None,
            "next_run_at": None,
        }
    schedule["name"] = (data.get("name") or "").strip()
    schedule["target_type"] = data.get("target_type", "profile")
    schedule["target_id"] = data.get("target_id")
    schedule["cron"] = data.get("cron", "").strip()
    schedule["enabled"] = bool(data.get("enabled", True))

    cron_changed = existing is None or existing.get("cron") != schedule["cron"]
    if schedule["enabled"]:
        if cron_changed or existing is None or existing.get("next_run_at") is None:
            schedule["next_run_at"] = _next_run_at(schedule["cron"])
        else:
            schedule["next_run_at"] = existing.get("next_run_at")
    else:
        schedule["next_run_at"] = None

    schedules = [s for s in schedules if s.get("id") != schedule["id"]]
    schedules.append(schedule)
    save_json(COL_SCHEDULES, schedules)
    record_audit(
        "created" if before is None else "updated",
        "schedule",
        schedule["id"],
        _audit_name(schedule),
        before=before,
        after=copy.deepcopy(schedule),
        details={"changed": changed_fields(before, schedule)} if before else None,
    )
    return schedule, None


@_locked
def handle_toggle(schedule_id):
    """Enable/disable a schedule. Returns (schedule, error)."""
    schedules = load_json(COL_SCHEDULES)
    target = next((s for s in schedules if s.get("id") == schedule_id), None)
    if not target:
        return None, {"error": "Schedule not found"}
    before = copy.deepcopy(target)
    target["enabled"] = not target.get("enabled")
    if target["enabled"]:
        target["next_run_at"] = _next_run_at(target.get("cron", ""))
    else:
        target["next_run_at"] = None
    save_json(COL_SCHEDULES, schedules)
    record_audit(
        "updated",
        "schedule",
        schedule_id,
        _audit_name(target),
        before=before,
        after=copy.deepcopy(target),
        details={"changed": changed_fields(before, target)},
    )
    return target, None


@_locked
def handle_run_now(schedule_id):
    """Fire a schedule immediately without touching its cadence."""
    schedules = load_json(COL_SCHEDULES)
    sched = next((s for s in schedules if s.get("id") == schedule_id), None)
    if not sched:
        return None, {"error": "Schedule not found"}
    run_id = scheduler.fire_schedule(sched)
    if not run_id:
        return None, {"error": "Could not start run (target missing or script missing)"}
    sched["last_run_at"] = time.time()
    sched["last_run_id"] = run_id
    save_json(COL_SCHEDULES, schedules)
    record_audit(
        "run_now",
        "schedule",
        schedule_id,
        _audit_name(sched),
        after=copy.deepcopy(sched),
        details={"run_id": run_id},
    )
    return {"run_id": run_id}, None


@_locked
def handle_duplicate(schedule_id):
    schedules = load_json(COL_SCHEDULES)
    source = next((s for s in schedules if s.get("id") == schedule_id), None)
    if not source:
        return None, {"error": "Schedule not found"}
    duplicate = copy.deepcopy(source)
    duplicate["id"] = f"sched_{uuid.uuid4().hex[:12]}"
    duplicate["created_at"] = time.time()
    duplicate["last_run_at"] = None
    duplicate["last_run_id"] = None
    duplicate["last_status"] = None
    base = source.get("name") or "Schedule"
    existing_names = {s.get("name") for s in schedules}
    name = f"{base} (copy)"
    n = 2
    while name in existing_names:
        name = f"{base} (copy {n})"
        n += 1
    duplicate["name"] = name
    if duplicate.get("enabled"):
        duplicate["next_run_at"] = _next_run_at(duplicate.get("cron", ""))
    else:
        duplicate["next_run_at"] = None
    schedules.append(duplicate)
    save_json(COL_SCHEDULES, schedules)
    record_audit(
        "created",
        "schedule",
        duplicate["id"],
        duplicate.get("name"),
        after=copy.deepcopy(duplicate),
        details={"duplicate_of": _audit_name(source)},
    )
    return duplicate, None


@_locked
def handle_delete(schedule_id):
    schedules = load_json(COL_SCHEDULES)
    target = next((s for s in schedules if s.get("id") == schedule_id), None)
    schedules = [s for s in schedules if s.get("id") != schedule_id]
    save_json(COL_SCHEDULES, schedules)
    if target:
        record_audit(
            "deleted",
            "schedule",
            schedule_id,
            _audit_name(target),
            before=copy.deepcopy(target),
        )
    return {"ok": True}, None


def handle_preview(cron_expr):
    """Next few fire times for a cron expression, for the schedule editor."""
    try:
        parse_cron(cron_expr)
    except ValueError as e:
        return None, {"error": f"Invalid cron expression: {e}"}
    upcoming = []
    t = datetime.now()
    for _ in range(PREVIEW_COUNT):
        n = next_after(cron_expr, t)
        if n is None:
            break
        upcoming.append({
            "ts": n.timestamp(),
            "local": n.strftime("%Y-%m-%d %H:%M"),
        })
        t = n
    return {
        "cron": cron_expr,
        "description": describe_cron(cron_expr),
        "next": upcoming,
    }, None
