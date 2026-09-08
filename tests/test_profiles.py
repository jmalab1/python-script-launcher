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
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\nALL TESTS PASSED")
