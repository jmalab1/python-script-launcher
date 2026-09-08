import json
import time
from .config import DATA_DIR, PROFILES_FILE, WORKFLOWS_FILE, HISTORY_FILE


def load_json(path):
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_json(path, data):
    DATA_DIR.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def save_history(run_id, name, run_type, status, returncode, output, started_at, workflow_log=None, steps=None):
    entry = {
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
    history = load_json(HISTORY_FILE)
    history.append(entry)
    save_json(HISTORY_FILE, history)
