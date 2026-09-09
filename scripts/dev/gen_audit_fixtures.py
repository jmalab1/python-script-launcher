#!/usr/bin/env python3
"""Generate audit-hash compatibility fixtures for the Go port.

The Go server must verify audit hashes written by the Python app, so this
script runs the real Python implementation (launcher.storage) over a set
of entries covering unicode, nested structures, floats, bools and nulls,
and records the hash each entry would get. The Go test
(TestAuditHashCompat) asserts Go produces identical hashes.

Run from the repo root:  python3 scripts/dev/gen_audit_fixtures.py
Output: internal/store/testdata/audit_hash_fixtures.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from launcher.storage import _compute_entry_hash  # noqa: E402

ENTRIES = [
    {
        "id": "a1",
        "timestamp": 1759234567.123456,
        "action": "created",
        "entity_type": "profile",
        "entity_id": "profile_123",
        "name": "Backup <script> & run",
    },
    {
        "id": "a2",
        "timestamp": 1759234567.0,
        "action": "updated",
        "entity_type": "workflow",
        "entity_id": "workflow_abc",
        "name": "Unicode: héllo wörld 日本語 🎉",
        "before": {"timeout": None, "args": ["--x", "1"], "enabled": True},
        "after": {"timeout": 2.5, "args": [], "enabled": False},
        "details": {"changed": ["timeout", "args", "enabled"]},
    },
    {
        "id": "a3",
        "timestamp": 1760000000,
        "action": "reordered",
        "entity_type": "profiles",
        "entity_id": None,
        "name": "Profile order",
        "details": {"order": ["p3", "p1", "p2"]},
        "nested": {"deep": {"deeper": [{"list": ["a", 1, 2.5, None, True]}]}},
        "escapes": "line\nbreak\ttab\"quote\\back slash/solid",
    },
    {
        "id": "a4",
        "timestamp": 1760000001.5,
        "action": "deleted",
        "entity_type": "schedule",
        "entity_id": "sched_x",
        "name": "0",
        "zero": 0,
        "empty": {},
        "empty_list": [],
        "flag": False,
    },
]


def main():
    fixtures = []
    for entry in ENTRIES:
        entry = dict(entry)
        entry["_hash"] = _compute_entry_hash(entry)
        fixtures.append(entry)
    out = Path(__file__).resolve().parent.parent.parent / "internal/store/testdata/audit_hash_fixtures.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fixtures, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {len(fixtures)} fixtures to {out}")


if __name__ == "__main__":
    main()
