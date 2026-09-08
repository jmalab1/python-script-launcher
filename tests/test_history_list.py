import launcher.storage as storage
import launcher.api.history as history


def test_load_json_defaults_to_empty(store):
    assert store.read("history") == []


def test_save_load_roundtrip(store):
    data = [{"id": "1"}, {"id": "2"}]
    storage.save_json("history", data)
    assert store.read("history") == data


def test_handle_list_sorts_newest_first_and_paginates(store):
    entries = [
        {"id": f"e{i}", "run_id": f"r{i}", "name": f"n{i}",
         "type": "profile" if i % 2 else "workflow", "timestamp": 1000.0 + i}
        for i in range(5)
    ]
    storage.save_json("history", entries)

    page = history.handle_list(1, 2, None)
    assert page["total"] == 5 and page["pages"] == 3 and page["page"] == 1 and page["per_page"] == 2
    assert [e["id"] for e in page["entries"]] == ["e4", "e3"]
    assert [e["id"] for e in history.handle_list(2, 2, None)["entries"]] == ["e2", "e1"]
    assert [e["id"] for e in history.handle_list(3, 2, None)["entries"]] == ["e0"]


def test_handle_list_filters_by_type(store):
    entries = [
        {"id": f"e{i}", "run_id": f"r{i}", "name": f"n{i}",
         "type": "profile" if i % 2 else "workflow", "timestamp": 1000.0 + i}
        for i in range(5)
    ]
    storage.save_json("history", entries)

    filtered = history.handle_list(1, 10, "profile")
    assert filtered["total"] == 2
    assert all(e["type"] == "profile" for e in filtered["entries"])


def _seed_history():
    entries = [
        {"id": "e1", "run_id": "r1", "name": "Database Backup", "type": "profile",
         "status": "completed", "timestamp": 1000.0},
        {"id": "e2", "run_id": "r2", "name": "backup logs", "type": "profile",
         "status": "failed", "timestamp": 2000.0},
        {"id": "e3", "run_id": "r3", "name": "Deploy Site", "type": "workflow",
         "status": "running", "timestamp": 3000.0},
    ]
    storage.save_json("history", entries)


def test_handle_list_filters_by_name_case_insensitively(store):
    _seed_history()
    res = history.handle_list(1, 10, None, name="BACKUP")
    assert res["total"] == 2
    assert {e["id"] for e in res["entries"]} == {"e1", "e2"}


def test_handle_list_filters_by_status(store):
    _seed_history()
    res = history.handle_list(1, 10, None, status="failed")
    assert res["total"] == 1
    assert res["entries"][0]["id"] == "e2"


def test_handle_list_filters_by_date_range_inclusive(store):
    _seed_history()
    # Both bounds are inclusive of the exact timestamps they match.
    res = history.handle_list(1, 10, None, since=1000.0, until=2000.0)
    assert res["total"] == 2
    assert {e["id"] for e in res["entries"]} == {"e1", "e2"}

    res = history.handle_list(1, 10, None, since=1000.001)
    assert res["total"] == 2


def test_handle_list_filters_on_the_shown_start_time_not_the_last_update(store):
    # A run that started on day 1 but only finished (i.e. got its history
    # entry last updated) on day 5. The table shows its start time, so a
    # "since day 3" filter must not pull it in via the update time.
    storage.save_json("history", [
        {"id": "long", "run_id": "r1", "name": "Long Job", "type": "profile",
         "status": "completed", "started_at": 1000.0, "timestamp": 5000.0},
        {"id": "short", "run_id": "r2", "name": "Short Job", "type": "profile",
         "status": "completed", "started_at": 3000.0, "timestamp": 3001.0},
    ])
    res = history.handle_list(1, 10, None, since=2000.0)
    assert res["total"] == 1 and res["entries"][0]["id"] == "short", \
        "date filters must match the displayed start time, not the finish time"

    res = history.handle_list(1, 10, None, until=2000.0)
    assert res["total"] == 1 and res["entries"][0]["id"] == "long"


def test_handle_list_combines_filters_with_and(store):
    _seed_history()
    res = history.handle_list(1, 10, "profile", name="backup", status="failed")
    assert res["total"] == 1
    assert res["entries"][0]["id"] == "e2"

    # Filtered totals drive pagination: 3 entries, 2 match name, per_page=1
    res = history.handle_list(1, 1, None, name="backup")
    assert res["total"] == 2 and res["pages"] == 2


def test_save_history_previews_last_20_lines_and_stores_optional_fields(store):
    storage.save_history("run1", "Job", "profile", "completed", 0,
                         [f"line{i}\n" for i in range(30)], 42.0)
    saved = store.read("history")[-1]
    assert saved["id"] and saved["run_id"] == "run1" and saved["returncode"] == 0
    assert saved["output_preview"] == "".join(f"line{i}\n" for i in range(10, 30))
    assert "workflow_log" not in saved and "steps" not in saved

    storage.save_history("run2", "WF", "workflow", "completed", None, [], 43.0,
                         workflow_log=["log"], steps={"S": {"status": "completed"}})
    saved = store.read("history")[-1]
    assert saved["workflow_log"] == ["log"]
    assert saved["steps"] == {"S": {"status": "completed"}}


def test_handle_clear_empties_history(store):
    storage.save_json("history", [{"id": "1"}])
    assert history.handle_clear() == {"ok": True}
    assert store.read("history") == []
