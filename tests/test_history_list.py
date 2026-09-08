import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import launcher.storage as storage
import launcher.api.history as history

tmp = Path(tempfile.mkdtemp())
storage.HISTORY_FILE = tmp / "history.json"
history.HISTORY_FILE = tmp / "history.json"

try:
    # 1. load_json defaults and save/load roundtrip
    assert storage.load_json(tmp / "missing.json") == []
    data = [{"id": 1}, {"id": 2}]
    storage.save_json(tmp / "store.json", data)
    assert storage.load_json(tmp / "store.json") == data
    print("PASS: load_json defaults to empty and save/load roundtrip")

    # 2. handle_list sorts newest first and paginates
    entries = [
        {"id": f"e{i}", "run_id": f"r{i}", "name": f"n{i}",
         "type": "profile" if i % 2 else "workflow", "timestamp": 1000.0 + i}
        for i in range(5)
    ]
    storage.save_json(storage.HISTORY_FILE, entries)
    page = history.handle_list(1, 2, None)
    assert page["total"] == 5 and page["pages"] == 3 and page["page"] == 1 and page["per_page"] == 2
    assert [e["id"] for e in page["entries"]] == ["e4", "e3"]
    assert [e["id"] for e in history.handle_list(2, 2, None)["entries"]] == ["e2", "e1"]
    assert [e["id"] for e in history.handle_list(3, 2, None)["entries"]] == ["e0"]
    print("PASS: handle_list sorts newest first and paginates")

    # 3. type filter
    filtered = history.handle_list(1, 10, "profile")
    assert filtered["total"] == 2
    assert all(e["type"] == "profile" for e in filtered["entries"])
    print("PASS: handle_list filters by type")

    # 4. save_history builds preview and optional fields
    storage.save_history("run1", "Job", "profile", "completed", 0,
                         [f"line{i}\n" for i in range(30)], 42.0)
    saved = storage.load_json(storage.HISTORY_FILE)[-1]
    assert saved["id"] and saved["run_id"] == "run1" and saved["returncode"] == 0
    assert saved["output_preview"] == "".join(f"line{i}\n" for i in range(10, 30))
    assert "workflow_log" not in saved and "steps" not in saved
    storage.save_history("run2", "WF", "workflow", "completed", None, [], 43.0,
                         workflow_log=["log"], steps={"S": {"status": "completed"}})
    saved = storage.load_json(storage.HISTORY_FILE)[-1]
    assert saved["workflow_log"] == ["log"]
    assert saved["steps"] == {"S": {"status": "completed"}}
    print("PASS: save_history previews the last 20 lines and stores optional fields")

    # 5. handle_clear empties history
    assert history.handle_clear() == {"ok": True}
    assert storage.load_json(storage.HISTORY_FILE) == []
    print("PASS: handle_clear empties history")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\nALL TESTS PASSED")
