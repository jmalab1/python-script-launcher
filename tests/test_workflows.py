import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import launcher.api.workflows as workflows

tmp = Path(tempfile.mkdtemp())
workflows.WORKFLOWS_FILE = tmp / "workflows.json"
workflows.PROFILES_FILE = tmp / "profiles.json"

try:
    # 1. empty store lists empty
    assert workflows.handle_list() == []
    print("PASS: handle_list returns empty list when the file is missing")

    # 2. create assigns an id and persists
    w1 = workflows.handle_create({"name": "Chain", "steps": []})
    assert w1["id"].startswith("workflow_")
    saved = json.loads(workflows.WORKFLOWS_FILE.read_text())
    assert [w["id"] for w in saved] == [w1["id"]]
    print("PASS: handle_create assigns an id and persists")

    # 3. create with same id replaces instead of duplicating
    workflows.handle_create({"id": w1["id"], "name": "Chain Updated", "steps": []})
    saved = json.loads(workflows.WORKFLOWS_FILE.read_text())
    assert len(saved) == 1 and saved[0]["name"] == "Chain Updated"
    print("PASS: handle_create upserts on duplicate id")

    # 4. explicit id is preserved
    w2 = workflows.handle_create({"id": "custom", "name": "Other"})
    assert w2["id"] == "custom"
    time.sleep(0.002)
    w3 = workflows.handle_create({"name": "Third"})
    print("PASS: handle_create keeps explicit ids")

    # 5. delete removes only the target
    workflows.handle_delete("custom")
    saved = json.loads(workflows.WORKFLOWS_FILE.read_text())
    assert [w["id"] for w in saved] == [w1["id"], w3["id"]], saved
    print("PASS: handle_delete removes only the target workflow")

    # 6. reorder honors order, ignores unknown ids, tolerates empty order
    ids = [w["id"] for w in workflows.handle_list()]
    workflows.handle_reorder({"order": list(reversed(ids))})
    assert [w["id"] for w in workflows.handle_list()] == list(reversed(ids))
    workflows.handle_reorder({"order": [w3["id"], "ghost_id"]})
    after = [w["id"] for w in workflows.handle_list()]
    assert after == [w3["id"], w1["id"]], after
    workflows.handle_reorder({"order": None})
    assert [w["id"] for w in workflows.handle_list()] == [w3["id"], w1["id"]]
    print("PASS: handle_reorder applies order and survives unknown/empty ids")

    # 7. create embeds a snapshot of each referenced profile into the steps
    (tmp / "profiles.json").write_text(json.dumps([
        {"id": "p1", "name": "One", "script_path": "/x/one.py", "args": [],
         "custom_args": [{"name": "--a", "type": "text", "value": "1"}]},
        {"id": "p2", "name": "Two", "script_path": "/x/two.py", "args": [], "custom_args": []},
    ]))
    w4 = workflows.handle_create({"name": "Snap", "steps": [
        {"type": "sequential", "profile_id": "p1", "args": []},
        {"type": "parallel", "profiles": [{"profile_id": "p2", "args": []}, {"profile_id": "ghost", "args": []}]},
    ]})
    assert w4["steps"][0]["profile"]["name"] == "One"
    assert w4["steps"][0]["profile"]["custom_args"] == [{"name": "--a", "type": "text", "value": "1"}]
    assert w4["steps"][1]["profiles"][0]["profile"]["name"] == "Two"
    assert "profile" not in w4["steps"][1]["profiles"][1]
    print("PASS: handle_create embeds profile snapshots into steps")

    # 8. snapshots are deep copies: later profile edits don't leak into saved workflows
    (tmp / "profiles.json").write_text(json.dumps([
        {"id": "p1", "name": "Renamed", "script_path": "/x/changed.py", "args": [], "custom_args": []},
    ]))
    saved_w4 = next(w for w in workflows.handle_list() if w["id"] == w4["id"])
    assert saved_w4["steps"][0]["profile"]["name"] == "One"
    assert saved_w4["steps"][0]["profile"]["script_path"] == "/x/one.py"
    print("PASS: workflow snapshots stay stable when profiles change")

    # 9. editing a workflow keeps its existing snapshot instead of re-syncing
    workflows.handle_create({"id": w4["id"], "name": "Snap Edited", "steps": [
        {"type": "sequential", "profile_id": "p1",
         "profile": {"id": "p1", "name": "One", "script_path": "/x/one.py", "args": [], "custom_args": []},
         "args": []},
    ]})
    saved_w4 = next(w for w in workflows.handle_list() if w["id"] == w4["id"])
    assert saved_w4["steps"][0]["profile"]["name"] == "One"
    assert saved_w4["steps"][0]["profile"]["script_path"] == "/x/one.py"
    print("PASS: handle_create keeps an existing snapshot on upsert")
    # 10. duplicate copies a workflow with a new id, unique name and deep-copied steps
    saved_before = json.loads(workflows.WORKFLOWS_FILE.read_text())
    source = next(w for w in saved_before if w["id"] == w4["id"])
    dup = workflows.handle_duplicate(w4["id"])
    assert dup["id"].startswith("workflow_") and dup["id"] != w4["id"]
    assert dup["name"] == "Snap Edited (copy)"
    saved = json.loads(workflows.WORKFLOWS_FILE.read_text())
    dup_saved = next(w for w in saved if w["id"] == dup["id"])
    assert [w["id"] for w in saved][-2:] == [w4["id"], dup["id"]]
    assert dup_saved["steps"] == source["steps"]
    assert dup_saved["steps"][0]["profile"]["name"] == "One"
    print("PASS: handle_duplicate copies a workflow with steps and snapshots")

    # 11. duplicate is a deep copy: editing the source steps does not affect the duplicate
    source["steps"][0]["profile"]["name"] = "Mutated"
    workflows.handle_create({"id": w4["id"], **source})
    saved = json.loads(workflows.WORKFLOWS_FILE.read_text())
    dup_saved = next(w for w in saved if w["id"] == dup["id"])
    assert dup_saved["steps"][0]["profile"]["name"] == "One", dup_saved
    print("PASS: handle_duplicate deep copies workflow steps")

    # 12. duplicate bumps the name when a copy already exists
    dup2 = workflows.handle_duplicate(w4["id"])
    assert dup2["name"] == "Snap Edited (copy 2)"
    print("PASS: handle_duplicate keeps workflow names unique across repeats")

    # 13. duplicate of a missing id returns None
    assert workflows.handle_duplicate("ghost_id") is None
    print("PASS: handle_duplicate returns None for unknown workflows")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\nALL TESTS PASSED")
