from ..storage import load_history, remove_history, replace_history


def summarize_entry(entry):
    summary = dict(entry)
    started_at = entry.get("started_at")
    timestamp = entry.get("timestamp")
    if entry.get("status") == "running":
        summary["duration"] = None
    elif (
        isinstance(started_at, (int, float))
        and isinstance(timestamp, (int, float))
        and timestamp >= started_at
    ):
        summary["duration"] = round(timestamp - started_at, 1)
    else:
        summary["duration"] = None
    if entry.get("type") == "workflow" and isinstance(entry.get("steps"), dict):
        steps = entry["steps"]
        summary["steps_total"] = len(steps)
        summary["steps_ok"] = sum(
            1 for s in steps.values() if s.get("status") == "completed"
        )
    return summary


def handle_list(page, per_page, type_filter):
    all_history = load_history()
    if type_filter:
        all_history = [e for e in all_history if e.get("type") == type_filter]
    all_history.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    total = len(all_history)
    start = (page - 1) * per_page
    end = start + per_page
    return {
        "entries": [summarize_entry(e) for e in all_history[start:end]],
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
    removed = remove_history(lambda e: e.get("id") == entry_key)
    if not removed:
        remove_history(lambda e: e.get("run_id") == entry_key)
    return {"ok": True}


def handle_bulk_delete(ids):
    id_set = set(ids)
    removed = remove_history(lambda e: e.get("id") in id_set)
    return {"ok": True, "removed": removed}


def handle_clear():
    replace_history([])
    return {"ok": True}
