from ..storage import load_audit, load_json, save_json, record_audit
from ..config import AUDIT_FILE, PROFILES_FILE, WORKFLOWS_FILE

_LIST_FIELDS = ("id", "timestamp", "action", "entity_type", "entity_id", "name", "details")


def summarize_entry(entry):
    return {k: entry[k] for k in _LIST_FIELDS if k in entry}


def handle_list(page, per_page, action_filter=None, entity_filter=None):
    entries = load_audit()
    if action_filter:
        entries = [e for e in entries if e.get("action") == action_filter]
    if entity_filter:
        entries = [e for e in entries if e.get("entity_type") == entity_filter]
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


def handle_delete(entry_id):
    entries = load_audit()
    remaining = [e for e in entries if e.get("id") != entry_id]
    save_json(AUDIT_FILE, remaining)
    return {"ok": True}


def handle_clear():
    save_json(AUDIT_FILE, [])
    return {"ok": True}


def handle_restore(entry_id):
    """Re-create the entity captured in a 'deleted' audit entry from its snapshot."""
    matches = [e for e in load_audit() if e.get("id") == entry_id]
    if not matches:
        return None
    entry = matches[0]
    if entry.get("action") != "deleted":
        return None
    snapshot = entry.get("before")
    if not isinstance(snapshot, dict) or not snapshot.get("id"):
        return None
    if entry.get("entity_type") == "profile":
        path = PROFILES_FILE
    elif entry.get("entity_type") == "workflow":
        path = WORKFLOWS_FILE
    else:
        return None
    entities = load_json(path)
    entities = [e for e in entities if e.get("id") != snapshot["id"]]
    entities.append(snapshot)
    save_json(path, entities)
    record_audit(
        "restored",
        entry["entity_type"],
        snapshot["id"],
        entry.get("name") or snapshot.get("name"),
        after=snapshot,
        details={"restored_from": entry_id},
    )
    return snapshot
