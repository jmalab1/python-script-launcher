import copy
import time
import uuid
from ..storage import load_json, save_json
from ..config import WORKFLOWS_FILE, PROFILES_FILE


def handle_list():
    return load_json(WORKFLOWS_FILE)


def _step_profile_entries(workflow):
    for step in workflow.get("steps") or []:
        if step.get("type") == "parallel":
            for entry in step.get("profiles") or []:
                yield entry
        else:
            yield step


def _embed_profile_snapshots(workflow):
    profiles = {p.get("id"): p for p in load_json(PROFILES_FILE)}
    for entry in _step_profile_entries(workflow):
        if entry.get("profile"):
            continue
        profile = profiles.get(entry.get("profile_id"))
        if profile:
            entry["profile"] = copy.deepcopy(profile)


def handle_create(data):
    workflows = load_json(WORKFLOWS_FILE)
    workflow = data
    if not workflow.get("id"):
        workflow["id"] = f"workflow_{int(time.time() * 1000)}"
    _embed_profile_snapshots(workflow)
    workflows = [w for w in workflows if w.get("id") != workflow["id"]]
    workflows.append(workflow)
    save_json(WORKFLOWS_FILE, workflows)
    return workflow


def handle_delete(workflow_id):
    workflows = load_json(WORKFLOWS_FILE)
    workflows = [w for w in workflows if w.get("id") != workflow_id]
    save_json(WORKFLOWS_FILE, workflows)
    return {"ok": True}


def handle_duplicate(workflow_id):
    workflows = load_json(WORKFLOWS_FILE)
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
    save_json(WORKFLOWS_FILE, workflows)
    return duplicate


def handle_reorder(data):
    order = data.get("order") or []
    workflows = load_json(WORKFLOWS_FILE)
    by_id = {w.get("id"): w for w in workflows}
    ordered = [by_id[i] for i in order if i in by_id]
    ordered_set = {w.get("id") for w in ordered}
    ordered += [w for w in workflows if w.get("id") not in ordered_set]
    save_json(WORKFLOWS_FILE, ordered)
    return {"ok": True}
