from ..storage import load_history, remove_history, replace_history

# Hard caps so a bogus query string (per_page=0 would previously divide
# by zero; a huge value would serialize the whole table) gets a sane
# response instead of a 500.
MAX_PER_PAGE = 200


def _clamp_paging(page, per_page, default_per_page):
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(per_page)
    except (TypeError, ValueError):
        per_page = default_per_page
    return max(1, page), max(1, min(per_page, MAX_PER_PAGE))


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


def _entry_time(entry):
    """The time a history entry is shown for: when the run started.

    The history table displays started_at, so date filters match on it too.
    Legacy entries predating that field fall back to their timestamp.
    """
    started = entry.get("started_at")
    return started if isinstance(started, (int, float)) else entry.get("timestamp", 0)


def handle_list(page, per_page, type_filter, name=None, status=None, since=None, until=None):
    page, per_page = _clamp_paging(page, per_page, 15)
    all_history = load_history()
    if type_filter:
        all_history = [e for e in all_history if e.get("type") == type_filter]
    if name:
        # Case-insensitive substring so "back" finds "Database Backup"
        needle = name.lower()
        all_history = [e for e in all_history if needle in (e.get("name") or "").lower()]
    if status:
        all_history = [e for e in all_history if e.get("status") == status]
    if since is not None:
        all_history = [e for e in all_history if _entry_time(e) >= since]
    if until is not None:
        all_history = [e for e in all_history if _entry_time(e) <= until]
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
