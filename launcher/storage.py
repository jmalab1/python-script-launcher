import json
import threading
import time
import uuid
from .config import DATA_DIR, PROFILES_FILE, WORKFLOWS_FILE, HISTORY_FILE, AUDIT_FILE

_history_lock = threading.RLock()
_audit_lock = threading.RLock()
AUDIT_MAX = 1000


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


def load_audit():
    with _audit_lock:
        entries = load_json(AUDIT_FILE)
        changed = False
        for entry in entries:
            if not entry.get("id"):
                entry["id"] = uuid.uuid4().hex
                changed = True
        if changed:
            save_json(AUDIT_FILE, entries)
        return entries


def changed_fields(before, after):
    """Return the sorted top-level field names that differ, or None if no before state."""
    if before is None:
        return None
    keys = set(before) | set(after)
    return sorted(k for k in keys if before.get(k) != after.get(k))


def record_audit(action, entity_type, entity_id, name, before=None, after=None, details=None):
    """Append an audit entry describing a profile/workflow change."""
    entry = {
        "id": uuid.uuid4().hex,
        "timestamp": time.time(),
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "name": name,
    }
    if before is not None:
        entry["before"] = before
    if after is not None:
        entry["after"] = after
    if details is not None:
        entry["details"] = details
    with _audit_lock:
        entries = load_audit()
        entries.append(entry)
        if len(entries) > AUDIT_MAX:
            entries = entries[-AUDIT_MAX:]
        save_json(AUDIT_FILE, entries)
    return entry
