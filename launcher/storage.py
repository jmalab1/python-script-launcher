import json
import threading
import time
import uuid
from .config import DATA_DIR, PROFILES_FILE, WORKFLOWS_FILE, HISTORY_FILE

_history_lock = threading.RLock()


def load_json(path):
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_json(path, data):
    DATA_DIR.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_history():
    with _history_lock:
        history = load_json(HISTORY_FILE)
        changed = False
        for entry in history:
            if not entry.get("id"):
                entry["id"] = uuid.uuid4().hex
                changed = True
        if changed:
            save_json(HISTORY_FILE, history)
        return history


def save_history(run_id, name, run_type, status, returncode, output, started_at, workflow_log=None, steps=None):
    entry = {
        "id": uuid.uuid4().hex,
        "run_id": run_id,
        "name": name,
        "type": run_type,
        "status": status,
        "returncode": returncode,
        "output": output,
        "output_preview": "".join(output[-20:]) if output else "",
        "started_at": started_at,
        "timestamp": time.time(),
    }
    if workflow_log is not None:
        entry["workflow_log"] = workflow_log
    if steps is not None:
        entry["steps"] = steps
    with _history_lock:
        history = load_history()
        history.append(entry)
        save_json(HISTORY_FILE, history)


def update_history(run_id, status=None, returncode=None, output=None, workflow_log=None, steps=None):
    """Update the newest history entry for run_id in place. Returns True if found."""
    with _history_lock:
        history = load_history()
        target = None
        for entry in history:
            if entry.get("run_id") == run_id:
                target = entry
        if target is None:
            return False
        if status is not None:
            target["status"] = status
        if returncode is not None:
            target["returncode"] = returncode
        if output is not None:
            target["output"] = output
            target["output_preview"] = "".join(output[-20:]) if output else ""
        if workflow_log is not None:
            target["workflow_log"] = workflow_log
        if steps is not None:
            target["steps"] = steps
        target["timestamp"] = time.time()
        save_json(HISTORY_FILE, history)
        return True
