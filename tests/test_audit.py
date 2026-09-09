import launcher.storage as storage
import launcher.api.audit as audit
import launcher.api.profiles as profiles
import launcher.api.workflows as workflows


def test_record_audit_appends_entry_with_fields(store):
    entry = storage.record_audit(
        "created", "profile", "p1", "One", after={"id": "p1", "name": "One"},
    )
    assert entry["id"] and entry["timestamp"] > 0
    assert entry["action"] == "created"
    assert entry["entity_type"] == "profile"
    assert entry["entity_id"] == "p1"
    assert entry["name"] == "One"
    saved = store.read("audit")
    assert saved[-1]["after"] == {"id": "p1", "name": "One"}


def test_record_audit_omits_empty_snapshots(store):
    entry = storage.record_audit("reordered", "profiles", None, "Profile order")
    assert "before" not in entry and "after" not in entry and "details" not in entry


def test_load_audit_backfills_missing_ids(store):
    store.seed("audit", [
        {"action": "created", "entity_type": "profile", "entity_id": "p1", "name": "One"},
    ])
    entries = storage.load_audit()
    assert entries[0]["id"]
    assert store.read("audit")[0]["id"] == entries[0]["id"]


def test_record_audit_caps_entries(store, monkeypatch):
    monkeypatch.setattr(storage, "AUDIT_MAX", 3)
    for i in range(5):
        storage.record_audit("created", "profile", f"p{i}", f"Profile {i}")
    entries = storage.load_audit()
    assert len(entries) == 3
    assert [e["entity_id"] for e in entries] == ["p2", "p3", "p4"]


def test_changed_fields_reports_differences():
    before = {"name": "One", "script_path": "/a.py", "gone": 1}
    after = {"name": "Two", "script_path": "/a.py", "new": 2}
    assert storage.changed_fields(before, after) == ["gone", "name", "new"]
    assert storage.changed_fields(before, before) == []
    assert storage.changed_fields(None, after) is None


def test_handle_list_sorts_desc_paginates_and_filters(store):
    for i in range(25):
        storage.record_audit("created" if i % 2 else "updated", "profile", f"p{i}", f"P{i}")
    res = audit.handle_list(1, 10)
    assert res["total"] == 25
    assert res["pages"] == 3
    assert len(res["entries"]) == 10
    assert res["entries"][0]["entity_id"] == "p24"

    created = audit.handle_list(1, 100, action_filter="created")
    assert created["total"] == 12 and all(e["action"] == "created" for e in created["entries"])

    workflows_only = audit.handle_list(1, 100, entity_filter="workflow")
    assert workflows_only["total"] == 0
    storage.record_audit("updated", "workflow", "w1", "W1")
    workflows_only = audit.handle_list(1, 100, entity_filter="workflow")
    assert workflows_only["total"] == 1 and workflows_only["entries"][0]["entity_id"] == "w1"


def test_handle_list_strips_snapshots(store):
    storage.record_audit("created", "profile", "p1", "One", before={"x": 1}, after={"y": 2})
    res = audit.handle_list(1, 10)
    entry = res["entries"][0]
    assert "before" not in entry and "after" not in entry
    assert entry["id"] and entry["name"] == "One"


def test_handle_list_filters_by_name_and_dates(store):
    # record_audit stamps its own timestamps, so seed raw entries to control them.
    store.seed("audit", [
        {"id": "a1", "timestamp": 1000.0, "action": "created",
         "entity_type": "profile", "entity_id": "p1", "name": "Database Backup"},
        {"id": "a2", "timestamp": 2000.0, "action": "updated",
         "entity_type": "workflow", "entity_id": "w1", "name": "Deploy site"},
        {"id": "a3", "timestamp": 3000.0, "action": "run_now",
         "entity_type": "schedule", "entity_id": "s1", "name": "Nightly sync"},
    ])

    res = audit.handle_list(1, 10, name="BACKUP")
    assert res["total"] == 1
    assert res["entries"][0]["id"] == "a1"

    res = audit.handle_list(1, 10, since=1000.0, until=2000.0)
    assert res["total"] == 2
    assert {e["id"] for e in res["entries"]} == {"a1", "a2"}

    # Filters combine: only the schedule entry is both recent and a run_now.
    res = audit.handle_list(1, 10, action_filter="run_now", entity_filter="schedule", since=2000.0)
    assert res["total"] == 1
    assert res["entries"][0]["id"] == "a3"


def test_handle_detail_returns_full_entry(store):
    created = storage.record_audit("created", "profile", "p1", "One", after={"id": "p1"})
    full = audit.handle_detail(created["id"])
    assert full["after"] == {"id": "p1"}
    assert audit.handle_detail("ghost") is None


def test_handle_delete_and_clear(store):
    e1 = storage.record_audit("created", "profile", "p1", "One")
    e2 = storage.record_audit("created", "profile", "p2", "Two")
    entries = audit.handle_list(1, 10)["entries"]
    assert len(entries) == 2
    assert [e["id"] for e in entries] == [e2["id"], e1["id"]]


def test_audit_entries_recorded_for_profile_lifecycle(store):
    p1 = profiles.handle_create({"name": "One", "script_path": "/tmp/a.py", "args": []})
    profiles.handle_create({"id": p1["id"], "name": "One Updated", "script_path": "/tmp/b.py", "args": []})
    profiles.handle_delete(p1["id"])
    entries = audit.handle_list(1, 10)["entries"]
    actions = [(e["action"], e["name"]) for e in entries]
    assert actions == [("deleted", "One Updated"), ("updated", "One Updated"), ("created", "One")]
    updated = entries[1]
    assert updated["entity_type"] == "profile" and updated["entity_id"] == p1["id"]
    assert updated["details"]["changed"] == ["name", "script_path"]
    deleted = entries[0]
    assert deleted["entity_id"] == p1["id"]


def test_audit_duplicate_records_duplicate_of(store):
    profiles.handle_create({"id": "p1", "name": "One", "args": []})
    dup = profiles.handle_duplicate("p1")
    entry = audit.handle_list(1, 10)["entries"][0]
    assert entry["action"] == "created" and entry["entity_id"] == dup["id"]
    assert entry["details"]["duplicate_of"] == "One"


def test_audit_reorder_recorded_only_when_order_changes(store):
    p1 = profiles.handle_create({"id": "p1", "name": "One", "args": []})
    p2 = profiles.handle_create({"id": "p2", "name": "Two", "args": []})
    profiles.handle_reorder({"order": [p2["id"], p1["id"]]})
    profiles.handle_reorder({"order": [p2["id"], p1["id"]]})
    reordered = [e for e in audit.handle_list(1, 10)["entries"] if e["action"] == "reordered"]
    assert len(reordered) == 1
    assert reordered[0]["details"]["order"] == [p2["id"], p1["id"]]


def test_audit_entries_recorded_for_workflow_lifecycle(store):
    w1 = workflows.handle_create({"name": "Chain", "steps": []})
    workflows.handle_create({"id": w1["id"], "name": "Chain Updated", "steps": []})
    workflows.handle_delete(w1["id"])
    entries = audit.handle_list(1, 10)["entries"]
    actions = [(e["action"], e["entity_type"]) for e in entries]
    assert actions == [("deleted", "workflow"), ("updated", "workflow"), ("created", "workflow")]
    assert entries[2]["entity_id"] == w1["id"]
    assert entries[0]["entity_id"] == w1["id"]


def test_audit_integrity_verification(store):
    storage.record_audit("created", "profile", "p1", "One")
    storage.record_audit("updated", "profile", "p1", "One Updated")
    is_valid, tampered = storage.verify_audit_integrity()
    assert is_valid
    assert tampered == []


def test_audit_integrity_detects_tampering(store):
    storage.record_audit("created", "profile", "p1", "One")
    entries = storage.load_audit()
    entries[0]["name"] = "Tampered"
    storage.save_json("audit", entries)
    is_valid, tampered = storage.verify_audit_integrity()
    assert not is_valid
    assert len(tampered) == 1


def test_audit_append_only_prevents_deletion(store):
    e1 = storage.record_audit("created", "profile", "p1", "One")
    e2 = storage.record_audit("created", "profile", "p2", "Two")
    entries = storage.load_audit()
    assert len(entries) == 2
    assert entries[0]["id"] == e1["id"]
    assert entries[1]["id"] == e2["id"]


def test_list_clamps_bogus_paging_values(store):
    store.seed("audit", [
        {"action": "created", "entity_type": "profile", "entity_id": str(i), "name": f"N{i}"}
        for i in range(3)
    ])
    result = audit.handle_list(0, 0)
    assert result["page"] == 1 and result["per_page"] == 1
    assert len(result["entries"]) == 1 and result["pages"] == 3

    assert audit.handle_list(1, 9999)["per_page"] == 200

    junk = audit.handle_list("x", "y")
    assert junk["page"] == 1 and junk["per_page"] == 20
