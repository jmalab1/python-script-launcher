import launcher.storage as storage
import launcher.api.history as history


def test_load_json_defaults_to_empty_and_save_load_roundtrip(store):
    assert storage.load_json(store["history"].parent / "missing.json") == []
    data = [{"id": 1}, {"id": 2}]
    storage.save_json(store["history"].parent / "store.json", data)
    assert storage.load_json(store["history"].parent / "store.json") == data


def test_handle_list_sorts_newest_first_and_paginates(store):
    entries = [
        {"id": f"e{i}", "run_id": f"r{i}", "name": f"n{i}",
         "type": "profile" if i % 2 else "workflow", "timestamp": 1000.0 + i}
        for i in range(5)
    ]
    storage.save_json(store["history"], entries)

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
    storage.save_json(store["history"], entries)

    filtered = history.handle_list(1, 10, "profile")
    assert filtered["total"] == 2
    assert all(e["type"] == "profile" for e in filtered["entries"])


def test_save_history_previews_last_20_lines_and_stores_optional_fields(store):
    storage.save_history("run1", "Job", "profile", "completed", 0,
                         [f"line{i}\n" for i in range(30)], 42.0)
    saved = storage.load_json(store["history"])[-1]
    assert saved["id"] and saved["run_id"] == "run1" and saved["returncode"] == 0
    assert saved["output_preview"] == "".join(f"line{i}\n" for i in range(10, 30))
    assert "workflow_log" not in saved and "steps" not in saved

    storage.save_history("run2", "WF", "workflow", "completed", None, [], 43.0,
                         workflow_log=["log"], steps={"S": {"status": "completed"}})
    saved = storage.load_json(store["history"])[-1]
    assert saved["workflow_log"] == ["log"]
    assert saved["steps"] == {"S": {"status": "completed"}}


def test_handle_clear_empties_history(store):
    storage.save_json(store["history"], [{"id": 1}])
    assert history.handle_clear() == {"ok": True}
    assert storage.load_json(store["history"]) == []
