import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import launcher.storage as storage
import launcher.api.history as history

tmp = Path(tempfile.mkdtemp())
hist_file = tmp / "history.json"
storage.HISTORY_FILE = hist_file
history.HISTORY_FILE = hist_file

# Reproduce real data: duplicate run_ids from server restarts, no ids (legacy format)
legacy = [
    {"run_id": "prof_4", "name": "Generate Report", "type": "profile", "status": "completed",
     "output": ["OLD RUN A"], "output_preview": "OLD RUN A", "started_at": 1788820444.0, "timestamp": 1788820444.8},
    {"run_id": "wf_2", "name": "Test", "type": "workflow", "status": "completed",
     "output": ["WF OLD"], "output_preview": "WF OLD", "started_at": 1788821743.0, "timestamp": 1788821743.7},
    {"run_id": "prof_4", "name": "Unstable", "type": "profile", "status": "failed",
     "output": ["OLD RUN B"], "output_preview": "OLD RUN B", "started_at": 1788821235.0, "timestamp": 1788821235.1},
    {"run_id": "wf_2", "name": "New", "type": "workflow", "status": "failed",
     "output": ["WF NEW"], "output_preview": "WF NEW", "started_at": 1788827247.0, "timestamp": 1788827247.1},
]
hist_file.write_text(json.dumps(legacy))

# 1. load_history backfills unique ids
entries = storage.load_history()
assert all(e.get("id") for e in entries), "ids backfilled"
ids = [e["id"] for e in entries]
assert len(set(ids)) == len(ids), "ids unique"
print("PASS: legacy entries backfilled with unique ids")

# 2. detail by id returns the exact entry (previously returned oldest match)
unstable = next(e for e in entries if e["name"] == "Unstable")
got = history.handle_detail(unstable["id"], "profile")
assert got["name"] == "Unstable" and got["output"] == ["OLD RUN B"], got
newest_wf = next(e for e in entries if e["output"] == ["WF NEW"])
got = history.handle_detail(newest_wf["id"], "workflow")
assert got["output"] == ["WF NEW"], got
print("PASS: detail by entry id pulls the correct run")

# 3. delete by id removes only that entry, duplicates of same run_id survive
ok = history.handle_delete(unstable["id"])
assert ok["ok"]
left = storage.load_json(hist_file)
assert len(left) == 3, len(left)
assert any(e["name"] == "Generate Report" and e["run_id"] == "prof_4" for e in left)
assert all(e["name"] != "Unstable" for e in left)
print("PASS: delete by id removes exactly one entry, sibling run_id untouched")

# 4. legacy lookup by run_id still works: prefers type match, then newest
got = history.handle_detail("wf_2", "workflow")
assert got["output"] == ["WF NEW"], got
print("PASS: legacy run_id lookup prefers newest matching entry")

# 5. new-style save_history: unique id + collision-proof run_id
storage.save_history("prof_1788828044000_13", "invalid file", "profile", "completed", 0,
                     ["hello"], 1788828044.9)
saved = storage.load_json(hist_file)[-1]
assert saved["id"] and saved["run_id"] == "prof_1788828044000_13"
assert history.handle_detail(saved["id"], "profile")["output"] == ["hello"]
print("PASS: save_history produces uniquely addressable entries")

# 6. delete via legacy run_id fallback
history.handle_delete("wf_2")
left = storage.load_json(hist_file)
assert all(e["run_id"] != "wf_2" for e in left)
print("PASS: legacy run_id delete fallback works")

print("\nALL TESTS PASSED")
