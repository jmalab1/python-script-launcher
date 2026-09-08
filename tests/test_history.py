import json

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
    store["history"].write_text(json.dumps(legacy))
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


def test_delete_by_entry_id_removes_exactly_one_entry_and_siblings_survive(store, legacy_history):
    entries = storage.load_history()
    unstable = next(e for e in entries if e["name"] == "Unstable")

    ok = history.handle_delete(unstable["id"])
    assert ok["ok"]
    left = storage.load_json(store["history"])
    assert len(left) == 3, len(left)
    assert any(e["name"] == "Generate Report" and e["run_id"] == "prof_4" for e in left)
    assert all(e["name"] != "Unstable" for e in left)


def test_legacy_run_id_lookup_prefers_newest_matching_entry(store, legacy_history):
    got = history.handle_detail("wf_2", "workflow")
    assert got["output"] == ["WF NEW"], got


def test_save_history_produces_uniquely_addressable_entries(store, legacy_history):
    storage.save_history("prof_1788828044000_13", "invalid file", "profile", "completed", 0,
                         ["hello"], 1788828044.9)
    saved = storage.load_json(store["history"])[-1]
    assert saved["id"] and saved["run_id"] == "prof_1788828044000_13"
    assert history.handle_detail(saved["id"], "profile")["output"] == ["hello"]


def test_delete_via_legacy_run_id_fallback(store, legacy_history):
    history.handle_delete("wf_2")
    left = storage.load_json(store["history"])
    assert all(e["run_id"] != "wf_2" for e in left)


def test_update_history_rewrites_the_newest_entry_for_a_run_in_place(store, legacy_history):
    ok = storage.update_history(
        "wf_2", status="completed", output=["WF NEW", "tail"],
        workflow_log=["log a", "log b"], steps={"1. A": {"status": "completed"}},
    )
    assert ok is True
    left = storage.load_json(store["history"])
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
    before = storage.load_json(store["history"])[-1]
    storage.update_history("wf_x", status="failed")
    after = storage.load_json(store["history"])[-1]
    assert after["status"] == "failed"
    assert after["id"] == before["id"] and after["started_at"] == before["started_at"]
    assert after["workflow_log"] == [] and after["steps"] == {}
    assert after["timestamp"] >= before["timestamp"], "timestamp is refreshed so duration covers the whole run"


def test_update_history_returns_false_for_unknown_run_ids(store, legacy_history):
    assert storage.update_history("wf_404", status="completed") is False
    assert len(storage.load_json(store["history"])) == 4
