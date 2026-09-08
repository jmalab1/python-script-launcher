import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import launcher.api.profiles as profiles

tmp = Path(tempfile.mkdtemp())
profiles.PROFILES_FILE = tmp / "profiles.json"

try:
    # 1. empty store lists empty
    assert profiles.handle_list() == []
    print("PASS: handle_list returns empty list when the file is missing")

    # 2. create assigns an id and persists
    p1 = profiles.handle_create({"name": "One", "script_path": "/tmp/a.py", "args": []})
    assert p1["id"].startswith("profile_")
    saved = json.loads(profiles.PROFILES_FILE.read_text())
    assert [p["id"] for p in saved] == [p1["id"]]
    print("PASS: handle_create assigns an id and persists")

    # 3. create with same id replaces instead of duplicating
    profiles.handle_create({"id": p1["id"], "name": "One Updated", "script_path": "/tmp/a.py", "args": []})
    saved = json.loads(profiles.PROFILES_FILE.read_text())
    assert len(saved) == 1 and saved[0]["name"] == "One Updated"
    print("PASS: handle_create upserts on duplicate id")

    # 4. explicit id is preserved
    p2 = profiles.handle_create({"id": "custom", "name": "Two"})
    assert p2["id"] == "custom"
    time.sleep(0.002)
    p3 = profiles.handle_create({"name": "Three"})
    print("PASS: handle_create keeps explicit ids")

    # 5. delete removes only the target
    profiles.handle_delete("custom")
    saved = json.loads(profiles.PROFILES_FILE.read_text())
    assert [p["id"] for p in saved] == [p1["id"], p3["id"]], saved
    print("PASS: handle_delete removes only the target profile")

    # 6. reorder honors order, ignores unknown ids, tolerates empty order
    ids = [p["id"] for p in profiles.handle_list()]
    profiles.handle_reorder({"order": list(reversed(ids))})
    assert [p["id"] for p in profiles.handle_list()] == list(reversed(ids))
    profiles.handle_reorder({"order": [p3["id"], "ghost_id"]})
    after = [p["id"] for p in profiles.handle_list()]
    assert after == [p3["id"], p1["id"]], after
    profiles.handle_reorder({"order": None})
    assert [p["id"] for p in profiles.handle_list()] == [p3["id"], p1["id"]]
    print("PASS: handle_reorder applies order and survives unknown/empty ids")
    # 7. duplicate copies a profile with a new id, unique "(copy)" name, right after the original
    saved_before = json.loads(profiles.PROFILES_FILE.read_text())
    target = next(p for p in saved_before if p["id"] == p3["id"])
    target["custom_args"] = [{"name": "--flag", "type": "text", "value": "1"}]
    profiles.handle_create(target)
    dup = profiles.handle_duplicate(p3["id"])
    assert dup["id"].startswith("profile_") and dup["id"] != p3["id"]
    assert dup["name"] == "Three (copy)"
    saved = json.loads(profiles.PROFILES_FILE.read_text())
    ids = [p["id"] for p in saved]
    assert len(saved) == 3
    assert ids[ids.index(p3["id"]) + 1] == dup["id"]
    print("PASS: handle_duplicate copies a profile with a new id and unique name")

    # 8. duplicate is a deep copy: editing the source does not affect the duplicate
    target["custom_args"][0]["value"] = "changed"
    profiles.handle_create(target)
    saved = json.loads(profiles.PROFILES_FILE.read_text())
    dup_saved = next(p for p in saved if p["id"] == dup["id"])
    assert dup_saved["custom_args"][0]["value"] == "1", dup_saved
    print("PASS: handle_duplicate deep copies custom_args")

    # 9. duplicate generates a fresh unique id every time and bumps the name
    dup2 = profiles.handle_duplicate(p3["id"])
    dup3 = profiles.handle_duplicate(p3["id"])
    assert dup2["id"] != dup3["id"] and dup2["id"] != dup["id"]
    assert dup2["name"] == "Three (copy 2)" and dup3["name"] == "Three (copy 3)"
    print("PASS: handle_duplicate keeps ids and names unique across repeats")

    # 10. duplicate of a missing id returns None
    assert profiles.handle_duplicate("ghost_id") is None
    print("PASS: handle_duplicate returns None for unknown profiles")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\nALL TESTS PASSED")
