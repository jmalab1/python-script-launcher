import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from .config import DATA_DIR, DB_PATH, COL_HISTORY, COL_AUDIT

log = logging.getLogger("launcher.storage")

_history_lock = threading.RLock()
_audit_lock = threading.RLock()
AUDIT_MAX = 1000

_TABLES = {
    "profiles": "profiles",
    "workflows": "workflows",
    "history": "history",
    "audit": "audit",
    "schedules": "schedules",
}

_db_initialized = False
_db_init_lock = threading.Lock()

_LEGACY_FILES = {
    "profiles": "profiles.json",
    "workflows": "workflows.json",
    "history": "history.json",
    "audit": "audit.json",
}


def _get_conn():
    if DB_PATH.exists() and not os.access(DB_PATH, os.W_OK):
        try:
            import shutil
            uid = os.getuid()
            DB_PATH.chown(uid, -1)
            log.info("Fixed ownership of %s for uid %d", DB_PATH, uid)
        except (OSError, PermissionError):
            log.warning("Cannot fix ownership of %s — DB may be read-only", DB_PATH)
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


def _init_db(conn):
    global _db_initialized
    if _db_initialized:
        return
    with _db_init_lock:
        if _db_initialized:
            return
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS history (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                type TEXT NOT NULL,
                json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_history_run_id ON history(run_id);
            CREATE INDEX IF NOT EXISTS idx_history_type ON history(type);
            CREATE TABLE IF NOT EXISTS audit (
                id TEXT PRIMARY KEY,
                json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS schedules (
                id TEXT PRIMARY KEY,
                json TEXT NOT NULL
            );
        """)
        conn.commit()
        _migrate_legacy(conn)
        _db_initialized = True


def _migrate_legacy(conn):
    for collection, filename in _LEGACY_FILES.items():
        table = _TABLES[collection]
        count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        if count > 0:
            continue
        legacy_path = DATA_DIR / filename
        if not legacy_path.exists():
            continue
        try:
            with open(legacy_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            log.warning("Failed to read legacy file %s", legacy_path)
            continue
        if not data:
            continue
        log.info("Migrating %d records from %s into %s table", len(data), filename, table)
        for item in data:
            item_id = item.get("id")
            if item_id is None:
                item_id = uuid.uuid4().hex
                item["id"] = item_id
            if table == "history":
                conn.execute(
                    f'INSERT INTO "{table}" (id, run_id, type, json) VALUES (?, ?, ?, ?)',
                    (str(item_id), item.get("run_id", ""), item.get("type", ""), json.dumps(item, ensure_ascii=False)),
                )
            else:
                conn.execute(
                    f'INSERT INTO "{table}" (id, json) VALUES (?, ?)',
                    (str(item_id), json.dumps(item, ensure_ascii=False)),
                )
        conn.commit()


def _table(collection):
    t = _TABLES.get(collection)
    if t is None:
        raise ValueError(f"Unknown collection: {collection!r}")
    return t


def load_json(collection):
    table = _table(collection)
    conn = _get_conn()
    try:
        _init_db(conn)
        rows = conn.execute(f'SELECT json FROM "{table}"').fetchall()
        return [json.loads(r["json"]) for r in rows]
    finally:
        conn.close()


def save_json(collection, data):
    table = _table(collection)
    DATA_DIR.mkdir(exist_ok=True)
    conn = _get_conn()
    try:
        _init_db(conn)
        conn.execute(f'DELETE FROM "{table}"')
        for item in data:
            item_id = item.get("id")
            if item_id is None:
                item_id = uuid.uuid4().hex
                item["id"] = item_id
            if table == "history":
                conn.execute(
                    f'INSERT INTO "{table}" (id, run_id, type, json) VALUES (?, ?, ?, ?)',
                    (str(item_id), item.get("run_id", ""), item.get("type", ""), json.dumps(item, ensure_ascii=False)),
                )
            else:
                conn.execute(
                    f'INSERT INTO "{table}" (id, json) VALUES (?, ?)',
                    (str(item_id), json.dumps(item, ensure_ascii=False)),
                )
        conn.commit()
    finally:
        conn.close()


def append_audit(entry):
    """Append a single audit entry without rewriting the entire table."""
    table = _TABLES["audit"]
    DATA_DIR.mkdir(exist_ok=True)
    conn = _get_conn()
    try:
        _init_db(conn)
        entry_id = entry.get("id")
        if entry_id is None:
            entry_id = uuid.uuid4().hex
            entry["id"] = entry_id
        entry["_hash"] = _compute_entry_hash(entry)
        conn.execute(
            f'INSERT INTO "{table}" (id, json) VALUES (?, ?)',
            (str(entry_id), json.dumps(entry, ensure_ascii=False)),
        )
        conn.commit()
    finally:
        conn.close()


def _compute_entry_hash(entry):
    """Compute a hash of the audit entry content for integrity verification."""
    entry_copy = {k: v for k, v in entry.items() if k != "_hash"}
    content = json.dumps(entry_copy, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode()).hexdigest()


def verify_audit_integrity():
    """Verify the integrity of the audit log. Returns (is_valid, tampered_entries)."""
    with _audit_lock:
        entries = load_audit()
        tampered = []
        for entry in entries:
            expected_hash = _compute_entry_hash(entry)
            if entry.get("_hash") != expected_hash:
                tampered.append(entry.get("id"))
        return len(tampered) == 0, tampered


def load_history():
    with _history_lock:
        history = load_json(COL_HISTORY)
        changed = False
        for entry in history:
            if not entry.get("id"):
                entry["id"] = uuid.uuid4().hex
                changed = True
        if changed:
            save_json(COL_HISTORY, history)
        return history


def save_history(run_id, name, run_type, status, returncode, output, started_at, workflow_log=None, steps=None, command=None, trigger=None, schedule_id=None, schedule_name=None):
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
    if trigger is not None:
        entry["trigger"] = trigger
    if schedule_id is not None:
        entry["schedule_id"] = schedule_id
    if schedule_name is not None:
        entry["schedule_name"] = schedule_name
    if workflow_log is not None:
        entry["workflow_log"] = workflow_log
    if steps is not None:
        entry["steps"] = steps
    if command is not None:
        entry["command"] = command
    with _history_lock:
        history = load_history()
        history.append(entry)
        save_json(COL_HISTORY, history)


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
        save_json(COL_HISTORY, history)
        return True


def load_audit():
    with _audit_lock:
        entries = load_json(COL_AUDIT)
        changed = False
        for entry in entries:
            if not entry.get("id"):
                entry["id"] = uuid.uuid4().hex
                changed = True
            if "_hash" not in entry:
                entry["_hash"] = _compute_entry_hash(entry)
                changed = True
        if changed:
            save_json(COL_AUDIT, entries)
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
        append_audit(entry)
        entries = load_audit()
        if len(entries) > AUDIT_MAX:
            entries = entries[-AUDIT_MAX:]
            save_json(COL_AUDIT, entries)
    return entry
