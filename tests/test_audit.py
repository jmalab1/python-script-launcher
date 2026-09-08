import json

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
    saved = json.loads(store["audit"].read_text())
    assert saved[-1]["after"] == {"id": "p1", "name": "One"}


def test_record_audit_omits_empty_snapshots(store):
    entry = storage.record_audit("reordered", "profiles", None, "Profile order")
    assert "before" not in entry and "after" not in entry and "details" not in entry


def test_load_audit_backfills_missing_ids(store):
    store["audit"].write_text(json.dumps([
        {"action": "created", "entity_type": "profile", "entity_id": "p1", "name": "One"},
    ]))
    entries = storage.load_audit()
    assert entries[0]["id"]
    assert json.loads(store["audit"].read_text())[0]["id"] == entries[0]["id"]


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


def test_handle_detail_returns_full_entry(store):
    created = storage.record_audit("created", "profile", "p1", "One", after={"id": "p1"})
    full = audit.handle_detail(created["id"])
    assert full["after"] == {"id": "p1"}
    assert audit.handle_detail("ghost") is None


def test_handle_delete_and_clear(store):
    e1 = storage.record_audit("created", "profile", "p1", "One")
    e2 = storage.record_audit("created", "profile", "p2", "Two")
    audit.handle_delete(e1["id"])
    remaining = audit.handle_list(1, 10)["entries"]
    assert [e["id"] for e in remaining] == [e2["id"]]
    audit.handle_clear()
    assert audit.handle_list(1, 10)["total"] == 0


def test_restore_deleted_profile_round_trip(store):
    p1 = profiles.handle_create({"name": "One", "script_path": "/tmp/a.py", "args": []})
    profiles.handle_delete(p1["id"])
    assert profiles.handle_list() == []
    deleted_entry = [e for e in audit.handle_list(1, 10)["entries"] if e["action"] == "deleted"][0]
    restored = audit.handle_restore(deleted_entry["id"])
    assert restored["id"] == p1["id"] and restored["name"] == "One"
    saved = profiles.handle_list()
    assert [p["id"] for p in saved] == [p1["id"]]
    actions = [e["action"] for e in audit.handle_list(1, 10)["entries"]]
    assert actions[0] == "restored"
    assert audit.handle_list(1, 10)["entries"][0]["details"]["restored_from"] == deleted_entry["id"]


def test_restore_deleted_workflow_round_trip(store):
    w1 = workflows.handle_create({"name": "Chain", "steps": []})
    workflows.handle_delete(w1["id"])
    deleted_entry = [e for e in audit.handle_list(1, 10)["entries"] if e["action"] == "deleted"][0]
    restored = audit.handle_restore(deleted_entry["id"])
    assert restored["id"] == w1["id"]
    assert [w["id"] for w in workflows.handle_list()] == [w1["id"]]


def test_restore_replaces_existing_entity_with_same_id(store):
    p1 = profiles.handle_create({"id": "p1", "name": "One", "args": []})
    profiles.handle_delete("p1")
    profiles.handle_create({"id": "p1", "name": "Interloper", "args": []})
    deleted_entry = [e for e in audit.handle_list(1, 10)["entries"] if e["action"] == "deleted"][0]
    audit.handle_restore(deleted_entry["id"])
    saved = [p["name"] for p in profiles.handle_list()]
    assert saved == ["One"]


def test_restore_rejects_unknown_or_non_deletable_entries(store):
    profiles.handle_create({"id": "p1", "name": "One", "args": []})
    created_entry = audit.handle_list(1, 10)["entries"][0]
    assert audit.handle_restore("ghost") is None
    assert audit.handle_restore(created_entry["id"]) is None


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
