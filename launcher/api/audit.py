from ..storage import load_audit
from ..config import COL_AUDIT

_LIST_FIELDS = ("id", "timestamp", "action", "entity_type", "entity_id", "name", "details")


def summarize_entry(entry):
    return {k: entry[k] for k in _LIST_FIELDS if k in entry}


def handle_list(page, per_page, action_filter=None, entity_filter=None, name=None, since=None, until=None):
    entries = load_audit()
    if action_filter:
        entries = [e for e in entries if e.get("action") == action_filter]
    if entity_filter:
        entries = [e for e in entries if e.get("entity_type") == entity_filter]
    if name:
        # Case-insensitive substring so "Back" finds "Backup"
        needle = name.lower()
        entries = [e for e in entries if needle in (e.get("name") or "").lower()]
    if since is not None:
        entries = [e for e in entries if e.get("timestamp", 0) >= since]
    if until is not None:
        entries = [e for e in entries if e.get("timestamp", 0) <= until]
    entries.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    total = len(entries)
    start = (page - 1) * per_page
    end = start + per_page
    return {
        "entries": [summarize_entry(e) for e in entries[start:end]],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


def handle_detail(entry_id):
    matches = [e for e in load_audit() if e.get("id") == entry_id]
    if not matches:
        return None
    return matches[0]

