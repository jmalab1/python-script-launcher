from ..storage import save_json, load_history
from ..config import HISTORY_FILE


def handle_list(page, per_page, type_filter):
    all_history = load_history()
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


def handle_detail(entry_key, type_filter=None):
    all_history = load_history()
    matches = [e for e in all_history if e.get("id") == entry_key]
    if not matches:
        matches = [e for e in all_history if e.get("run_id") == entry_key]
    if not matches:
        return None
    if type_filter:
        typed = [e for e in matches if e.get("type") == type_filter]
        if typed:
            matches = typed
    matches.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return matches[0]


def handle_delete(entry_key):
    all_history = load_history()
    remaining = [e for e in all_history if e.get("id") != entry_key]
    if len(remaining) == len(all_history):
        remaining = [e for e in all_history if e.get("run_id") != entry_key]
    save_json(HISTORY_FILE, remaining)
    return {"ok": True}


def handle_clear():
    save_json(HISTORY_FILE, [])
    return {"ok": True}
