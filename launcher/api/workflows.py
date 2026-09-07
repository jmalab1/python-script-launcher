import time
from ..storage import load_json, save_json
from ..config import WORKFLOWS_FILE


def handle_list():
    return load_json(WORKFLOWS_FILE)


def handle_create(data):
    workflows = load_json(WORKFLOWS_FILE)
    workflow = data
    if not workflow.get("id"):
        workflow["id"] = f"workflow_{int(time.time() * 1000)}"
    workflows = [w for w in workflows if w.get("id") != workflow["id"]]
    workflows.append(workflow)
    save_json(WORKFLOWS_FILE, workflows)
    return workflow


def handle_delete(workflow_id):
    workflows = load_json(WORKFLOWS_FILE)
    workflows = [w for w in workflows if w.get("id") != workflow_id]
    save_json(WORKFLOWS_FILE, workflows)
    return {"ok": True}


def handle_reorder(data):
    order = data.get("order") or []
    workflows = load_json(WORKFLOWS_FILE)
    by_id = {w.get("id"): w for w in workflows}
    ordered = [by_id[i] for i in order if i in by_id]
    ordered_set = {w.get("id") for w in ordered}
    ordered += [w for w in workflows if w.get("id") not in ordered_set]
    save_json(WORKFLOWS_FILE, ordered)
    return {"ok": True}
