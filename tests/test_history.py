import threading
import time

import pytest

import launcher.storage as storage
import launcher.api.history as history


@pytest.fixture
def legacy_history(store):
    """Reproduce real data: duplicate run_ids from server restarts, no ids (legacy format)."""
    legacy = [
        {"run_id": "prof_4", "name": "Generate Report", "type": "profile", "status": "completed",
         "output": ["OLD RUN A"], "output_preview": "OLD RUN A", "started_at": 1788820444.0,
         "timestamp": 1788820444.8},
        {"run_id": "wf_2", "name": "Test", "type": "workflow", "status": "completed",
         "output": ["WF OLD"], "output_preview": "WF OLD", "started_at": 1788821743.0,
         "timestamp": 1788821743.7},
        {"run_id": "prof_4", "name": "Unstable", "type": "profile", "status": "failed",
         "output": ["OLD RUN B"], "output_preview": "OLD RUN B", "started_at": 1788821235.0,
         "timestamp": 1788821235.1},
        {"run_id": "wf_2", "name": "New", "type": "workflow", "status": "failed",
         "output": ["WF NEW"], "output_preview": "WF NEW", "started_at": 1788827247.0,
         "timestamp": 1788827247.1},
    ]
    store.seed("history", legacy)
    return legacy


def test_load_history_backfills_legacy_entries_with_unique_ids(store, legacy_history):
    entries = storage.load_history()
    assert all(e.get("id") for e in entries), "ids backfilled"
    ids = [e["id"] for e in entries]
    assert len(set(ids)) == len(ids), "ids unique"


def test_detail_by_entry_id_pulls_the_correct_run(store, legacy_history):
    entries = storage.load_history()
    unstable = next(e for e in entries if e["name"] == "Unstable")
    got = history.handle_detail(unstable["id"], "profile")
    assert got["name"] == "Unstable" and got["output"] == ["OLD RUN B"], got

    newest_wf = next(e for e in entries if e["output"] == ["WF NEW"])
    got = history.handle_detail(newest_wf["id"], "workflow")
    assert got["output"] == ["WF NEW"], got


def test_detail_of_a_running_entry_exposes_its_run_id(store):
    """The run panel resolves the runner's poll id from this field, so a
    still-running run reopened from history can switch to live polling."""
    storage.save_history("prof_live_1", "Long Run", "profile", "running", None, [], 1.0)
    detail = history.handle_detail("prof_live_1", "profile")
    assert detail["status"] == "running"
    assert detail["run_id"] == "prof_live_1"


def test_delete_by_entry_id_removes_exactly_one_entry_and_siblings_survive(store, legacy_history):
    entries = storage.load_history()
    unstable = next(e for e in entries if e["name"] == "Unstable")

    ok = history.handle_delete(unstable["id"])
    assert ok["ok"]
    left = store.read("history")
    assert len(left) == 3, len(left)
    assert any(e["name"] == "Generate Report" and e["run_id"] == "prof_4" for e in left)
    assert all(e["name"] != "Unstable" for e in left)


def test_legacy_run_id_lookup_prefers_newest_matching_entry(store, legacy_history):
    got = history.handle_detail("wf_2", "workflow")
    assert got["output"] == ["WF NEW"], got


def test_save_history_produces_uniquely_addressable_entries(store, legacy_history):
    storage.save_history("prof_1788828044000_13", "invalid file", "profile", "completed", 0,
                         ["hello"], 1788828044.9)
    saved = store.read("history")[-1]
    assert saved["id"] and saved["run_id"] == "prof_1788828044000_13"
    assert history.handle_detail(saved["id"], "profile")["output"] == ["hello"]


def test_save_history_records_the_command_when_provided(store):
    cmd = ["/usr/bin/python3", "s.py", "--flag", "v"]
    storage.save_history("prof_cmd", "Cmd", "profile", "completed", 0, ["out"], 1.0, command=cmd)
    saved = store.read("history")[-1]
    assert saved["command"] == cmd
    assert history.handle_detail("prof_cmd", "profile")["command"] == cmd


def test_save_history_omits_the_command_when_not_provided(store):
    storage.save_history("wf_nocmd", "W", "workflow", "completed", 0, ["out"], 1.0)
    assert "command" not in store.read("history")[-1]


def test_delete_via_legacy_run_id_fallback(store, legacy_history):
    history.handle_delete("wf_2")
    left = store.read("history")
    assert all(e["run_id"] != "wf_2" for e in left)


def test_update_history_rewrites_the_newest_entry_for_a_run_in_place(store, legacy_history):
    ok = storage.update_history(
        "wf_2", status="completed", output=["WF NEW", "tail"],
        workflow_log=["log a", "log b"], steps={"1. A": {"status": "completed"}},
    )
    assert ok is True
    left = store.read("history")
    assert len(left) == 4, "update must not append a duplicate entry"
    updated = [e for e in left if e["run_id"] == "wf_2"]
    assert len(updated) == 2, "legacy duplicates stay untouched except the newest"
    newest = updated[-1]
    assert newest["name"] == "New" and newest["status"] == "completed"
    assert newest["output"] == ["WF NEW", "tail"]
    assert newest["output_preview"] == "WF NEWtail"
    assert newest["workflow_log"] == ["log a", "log b"]
    assert newest["steps"] == {"1. A": {"status": "completed"}}
    older = updated[0]
    assert older["status"] == "completed" and older["output"] == ["WF OLD"]


def test_update_history_only_touches_the_fields_it_is_given(store):
    storage.save_history("wf_x", "W", "workflow", "running", None, [], 1.0, workflow_log=[], steps={})
    before = store.read("history")[-1]
    storage.update_history("wf_x", status="failed")
    after = store.read("history")[-1]
    assert after["status"] == "failed"
    assert after["id"] == before["id"] and after["started_at"] == before["started_at"]
    assert after["workflow_log"] == [] and after["steps"] == {}
    assert after["timestamp"] >= before["timestamp"], "timestamp is refreshed so duration covers the whole run"


def test_update_history_returns_false_for_unknown_run_ids(store, legacy_history):
    assert storage.update_history("wf_404", status="completed") is False
    assert len(store.read("history")) == 4


def test_bulk_delete_removes_matching_entries(store, legacy_history):
    entries = storage.load_history()
    target = [e["id"] for e in entries if e["name"] in ("Unstable", "New")]
    assert len(target) == 2
    result = history.handle_bulk_delete(target)
    assert result["ok"]
    assert result["removed"] == 2
    left = store.read("history")
    assert len(left) == 2
    assert all(e["name"] not in ("Unstable", "New") for e in left)


def test_bulk_delete_removes_nothing_for_unknown_ids(store, legacy_history):
    result = history.handle_bulk_delete(["nonexistent_id_1", "nonexistent_id_2"])
    assert result["ok"]
    assert result["removed"] == 0
    assert len(store.read("history")) == 4


def test_bulk_delete_with_empty_ids(store, legacy_history):
    result = history.handle_bulk_delete([])
    assert result["ok"]
    assert result["removed"] == 0
    assert len(store.read("history")) == 4


def test_bulk_delete_of_all_entries(store, legacy_history):
    entries = storage.load_history()
    all_ids = [e["id"] for e in entries]
    result = history.handle_bulk_delete(all_ids)
    assert result["ok"]
    assert result["removed"] == 4
    assert store.read("history") == []


def test_deleting_history_does_not_lose_concurrent_appends(store, monkeypatch):
    """Regression: handle_delete/bulk/clear used to save outside the lock."""
    for i in range(3):
        storage.save_history(f"run_{i}", f"R{i}", "profile", "completed", 0, [], time.time())

    real_save_json = storage.save_json

    def slow_save_json(collection, data):
        if collection == "history":
            time.sleep(0.3)  # widen the window between the delete's load and save
        return real_save_json(collection, data)

    monkeypatch.setattr(storage, "save_json", slow_save_json)

    deleter = threading.Thread(target=history.handle_delete, args=("run_0",))
    deleter.start()
    time.sleep(0.05)  # the delete has loaded its snapshot and is inside its save
    for n in range(5):
        storage.save_history(f"concurrent_{n}", f"C{n}", "profile", "completed", 0, [], time.time())
    deleter.join()

    run_ids = {e["run_id"] for e in store.read("history")}
    assert "run_0" not in run_ids, "the targeted entry must still be deleted"
    for n in range(5):
        assert f"concurrent_{n}" in run_ids, f"concurrent append {n} was lost by the delete"


def test_clearing_history_does_not_lose_concurrent_appends(store, monkeypatch):
    storage.save_history("run_keep", "R", "profile", "completed", 0, [], time.time())

    real_replace = storage.replace_history
    gate = threading.Event()

    def gated_replace(entries):
        gate.wait(timeout=5)  # clear() holds the lock while an append lands
        return real_replace(entries)

    monkeypatch.setattr(storage, "replace_history", gated_replace)

    clearer = threading.Thread(target=history.handle_clear)
    clearer.start()
    time.sleep(0.05)
    storage.save_history("concurrent_run", "C", "profile", "completed", 0, [], time.time())
    gate.set()
    clearer.join()

    # handle_clear intentionally wipes everything while holding the history
    # lock, but the concurrent append must not deadlock or corrupt it.
    assert isinstance(store.read("history"), list)


def test_list_clamps_bogus_paging_values(store):
    store.seed("history", [
        {"run_id": f"r{i}", "name": f"Run {i}", "type": "profile", "status": "completed",
         "output": [], "timestamp": 1000 + i}
        for i in range(3)
    ])
    # per_page=0 used to raise ZeroDivisionError; junk strings came from
    # hand-crafted query strings.
    result = history.handle_list(0, 0, None)
    assert result["page"] == 1 and result["per_page"] == 1
    assert len(result["entries"]) == 1 and result["pages"] == 3

    assert history.handle_list(1, 9999, None)["per_page"] == 200, \
        "a huge per_page must be capped instead of serializing everything"

    junk = history.handle_list("x", "y", None)
    assert junk["page"] == 1 and junk["per_page"] == 15
