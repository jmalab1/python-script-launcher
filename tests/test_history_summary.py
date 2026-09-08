import json

import launcher.storage as storage
import launcher.api.history as history


def test_profile_entry_gets_duration_and_no_step_summary(store):
    store["history"].write_text(json.dumps([
        {"id": "a", "type": "profile", "started_at": 100.0, "timestamp": 104.2},
    ]))
    result = history.handle_list(1, 50, None)
    entry = result["entries"][0]
    assert entry["duration"] == 4.2, entry
    assert "steps_total" not in entry and "steps_ok" not in entry


def test_workflow_entry_gets_duration_plus_ok_total_step_counts(store):
    store["history"].write_text(json.dumps([
        {
            "id": "b",
            "type": "workflow",
            "started_at": 200.0,
            "timestamp": 205.0,
            "steps": {
                "1. A": {"status": "completed"},
                "2. B": {"status": "failed"},
                "3. C": {"status": "completed"},
            },
        },
    ]))
    entry = history.handle_list(1, 50, None)["entries"][0]
    assert entry["duration"] == 5.0, entry
    assert entry["steps_total"] == 3 and entry["steps_ok"] == 2, entry


def test_missing_or_inverted_timestamps_yield_duration_none(store):
    store["history"].write_text(json.dumps([
        {"id": "c", "type": "profile"},
        {"id": "d", "type": "profile", "started_at": 300.0, "timestamp": 299.0},
    ]))
    entries = history.handle_list(1, 50, None)["entries"]
    assert all(e["duration"] is None for e in entries), entries


def test_type_filter_respected_and_summary_only_on_workflow_entries(store):
    store["history"].write_text(json.dumps([
        {"id": "e", "type": "profile", "started_at": 1.0, "timestamp": 3.0},
        {"id": "f", "type": "workflow", "started_at": 1.0, "timestamp": 3.0,
         "steps": {"1. A": {"status": "completed"}}},
    ]))
    entries = history.handle_list(1, 50, "profile")["entries"]
    assert len(entries) == 1 and entries[0]["id"] == "e"
    assert entries[0]["duration"] == 2.0
    assert "steps_total" not in entries[0]
