from ..storage import load_json, save_json
from ..config import HISTORY_FILE


def handle_list(page, per_page, type_filter):
    all_history = load_json(HISTORY_FILE)
    if type_filter:
        all_history = [e for e in all_history if e.get("type") == type_filter]
    all_history.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    total = len(all_history)
    start = (page - 1) * per_page
    end = start + per_page
    return {
        "entries": all_history[start:end],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


def handle_detail(run_id, type_filter=None):
    history = load_json(HISTORY_FILE)
    matches = [e for e in history if e.get("run_id") == run_id]
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        entry = next((e for e in matches if e.get("type") == type_filter), matches[0])
        return entry
    return None


def handle_delete(run_id):
    history = load_json(HISTORY_FILE)
    history = [e for e in history if e.get("run_id") != run_id]
    save_json(HISTORY_FILE, history)
    return {"ok": True}


def handle_clear():
    save_json(HISTORY_FILE, [])
    return {"ok": True}
