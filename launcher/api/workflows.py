import copy
import functools
import time
import uuid
from ..storage import load_json, save_json, record_audit, changed_fields, collection_lock
from ..config import COL_WORKFLOWS, COL_PROFILES, COL_SCHEDULES


def _locked(fn):
    """Serialize read-modify-write access to the workflows collection."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with collection_lock(COL_WORKFLOWS):
            return fn(*args, **kwargs)
    return wrapper


def handle_list():
    return load_json(COL_WORKFLOWS)


def _step_profile_entries(workflow):
    for step in workflow.get("steps") or []:
        if step.get("type") == "parallel":
            for entry in step.get("profiles") or []:
                yield entry
        else:
            yield step


def _embed_profile_snapshots(workflow):
    profiles = {p.get("id"): p for p in load_json(COL_PROFILES)}
    for entry in _step_profile_entries(workflow):
        if entry.get("profile"):
            continue
        profile = profiles.get(entry.get("profile_id"))
        if profile:
            entry["profile"] = copy.deepcopy(profile)


@_locked
def handle_create(data):
    workflows = load_json(COL_WORKFLOWS)
    workflow = data
    if not workflow.get("id"):
        workflow["id"] = f"workflow_{int(time.time() * 1000)}"
    existing = next((w for w in workflows if w.get("id") == workflow["id"]), None)
    before = copy.deepcopy(existing) if existing else None
    _embed_profile_snapshots(workflow)
    if existing:
        # Updating an existing workflow replaces it in place: appending it
        # would reshuffle the list on every save and undo the user's
        # drag-to-reorder arrangement.
        workflows = [workflow if w.get("id") == workflow["id"] else w for w in workflows]
    else:
        workflows.append(workflow)
    save_json(COL_WORKFLOWS, workflows)
    record_audit(
        "created" if before is None else "updated",
        "workflow",
        workflow["id"],
        workflow.get("name"),
        before=before,
        after=copy.deepcopy(workflow),
        details={"changed": changed_fields(before, workflow)} if before else None,
    )
    return workflow


@_locked
def handle_delete(workflow_id):
    workflows = load_json(COL_WORKFLOWS)
    target = next((w for w in workflows if w.get("id") == workflow_id), None)
    if not target:
        return {"ok": True}
    before = copy.deepcopy(target)
    target["group"] = "__trash__"
    save_json(COL_WORKFLOWS, workflows)
    record_audit(
        "deleted",
        "workflow",
        workflow_id,
        target.get("name"),
        before=before,
        after=copy.deepcopy(target),
    )
    return {"ok": True}


@_locked
def handle_restore(workflow_id):
    workflows = load_json(COL_WORKFLOWS)
    target = next((w for w in workflows if w.get("id") == workflow_id), None)
    if not target or target.get("group") != "__trash__":
        return None
    before = copy.deepcopy(target)
    target["group"] = ""
    save_json(COL_WORKFLOWS, workflows)
    record_audit(
        "restored",
        "workflow",
        workflow_id,
        target.get("name"),
        before=before,
        after=copy.deepcopy(target),
    )
    return target


@_locked
def handle_permanent_delete(workflow_id):
    workflows = load_json(COL_WORKFLOWS)
    target = next((w for w in workflows if w.get("id") == workflow_id), None)
    workflows = [w for w in workflows if w.get("id") != workflow_id]
    save_json(COL_WORKFLOWS, workflows)
    if target:
        with collection_lock(COL_SCHEDULES):
            schedules = load_json(COL_SCHEDULES)
            removed_schedules = [s["id"] for s in schedules if s.get("target_id") == workflow_id]
            if removed_schedules:
                save_json(COL_SCHEDULES, [s for s in schedules if s.get("target_id") != workflow_id])
        record_audit(
            "permanently_deleted",
            "workflow",
            workflow_id,
            target.get("name"),
            before=copy.deepcopy(target),
            details={"schedules_removed": removed_schedules} if removed_schedules else None,
        )
    return {"ok": True}


@_locked
def handle_duplicate(workflow_id):
    workflows = load_json(COL_WORKFLOWS)
    index = next((i for i, w in enumerate(workflows) if w.get("id") == workflow_id), None)
    if index is None:
        return None
    source = workflows[index]
    duplicate = copy.deepcopy(source)
    duplicate["id"] = f"workflow_{uuid.uuid4().hex[:12]}"
    _embed_profile_snapshots(duplicate)
    base = source.get("name") or "Workflow"
    existing_names = {w.get("name") for w in workflows}
    name = f"{base} (copy)"
    n = 2
    while name in existing_names:
        name = f"{base} (copy {n})"
        n += 1
    duplicate["name"] = name
    workflows.insert(index + 1, duplicate)
    save_json(COL_WORKFLOWS, workflows)
    record_audit(
        "created",
        "workflow",
        duplicate["id"],
        duplicate.get("name"),
        after=copy.deepcopy(duplicate),
        details={"duplicate_of": source.get("name")},
    )
    return duplicate


@_locked
def handle_reorder(data):
    order = data.get("order") or []
    workflows = load_json(COL_WORKFLOWS)
    by_id = {w.get("id"): w for w in workflows}
    ordered = [by_id[i] for i in order if i in by_id]
    ordered_set = {w.get("id") for w in ordered}
    ordered += [w for w in workflows if w.get("id") not in ordered_set]
    previous = [w.get("id") for w in workflows]
    current = [w.get("id") for w in ordered]
    save_json(COL_WORKFLOWS, ordered)
    if current != previous:
        record_audit(
            "reordered",
            "workflows",
            None,
            "Workflow order",
            details={"order": current},
        )
    return {"ok": True}
