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
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\nALL TESTS PASSED")
