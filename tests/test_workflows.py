import time

import launcher.api.workflows as workflows


def write_profiles(store, data):
    store.seed("profiles", data)


def test_handle_list_empty(store):
    assert workflows.handle_list() == []


def test_handle_create_assigns_id_and_persists(store):
    w1 = workflows.handle_create({"name": "Chain", "steps": []})
    assert w1["id"].startswith("workflow_")
    saved = store.read("workflows")
    assert [w["id"] for w in saved] == [w1["id"]]


def test_handle_create_upserts_on_duplicate_id(store):
    w1 = workflows.handle_create({"name": "Chain", "steps": []})
    workflows.handle_create({"id": w1["id"], "name": "Chain Updated", "steps": []})
    saved = store.read("workflows")
    assert len(saved) == 1 and saved[0]["name"] == "Chain Updated"


def test_handle_create_keeps_explicit_ids(store):
    w2 = workflows.handle_create({"id": "custom", "name": "Other"})
    assert w2["id"] == "custom"


def test_handle_delete_removes_only_target(store):
    w1 = workflows.handle_create({"name": "Chain", "steps": []})
    workflows.handle_create({"id": "custom", "name": "Other"})
    time.sleep(0.002)
    w3 = workflows.handle_create({"name": "Third"})
    workflows.handle_delete("custom")
    saved = store.read("workflows")
    assert [w["id"] for w in saved] == [w1["id"], w3["id"]], saved


def test_handle_reorder_applies_order_and_survives_unknown_or_empty_ids(store):
    w1 = workflows.handle_create({"name": "Chain", "steps": []})
    time.sleep(0.002)
    w3 = workflows.handle_create({"name": "Third"})
    ids = [w["id"] for w in workflows.handle_list()]
    assert ids == [w1["id"], w3["id"]]

    workflows.handle_reorder({"order": list(reversed(ids))})
    assert [w["id"] for w in workflows.handle_list()] == list(reversed(ids))

    workflows.handle_reorder({"order": [w3["id"], "ghost_id"]})
    after = [w["id"] for w in workflows.handle_list()]
    assert after == [w3["id"], w1["id"]], after

    workflows.handle_reorder({"order": None})
    assert [w["id"] for w in workflows.handle_list()] == [w3["id"], w1["id"]]


def test_handle_create_embeds_profile_snapshots_into_steps(store):
    write_profiles(store, [
        {"id": "p1", "name": "One", "script_path": "/x/one.py", "args": [],
         "custom_args": [{"name": "--a", "type": "text", "value": "1"}]},
        {"id": "p2", "name": "Two", "script_path": "/x/two.py", "args": [], "custom_args": []},
    ])
    w4 = workflows.handle_create({"name": "Snap", "steps": [
        {"type": "sequential", "profile_id": "p1", "args": []},
        {"type": "parallel", "profiles": [{"profile_id": "p2", "args": []}, {"profile_id": "ghost", "args": []}]},
    ]})
    assert w4["steps"][0]["profile"]["name"] == "One"
    assert w4["steps"][0]["profile"]["custom_args"] == [{"name": "--a", "type": "text", "value": "1"}]
    assert w4["steps"][1]["profiles"][0]["profile"]["name"] == "Two"
    assert "profile" not in w4["steps"][1]["profiles"][1]


def test_workflow_snapshots_stay_stable_when_profiles_change(store):
    write_profiles(store, [
        {"id": "p1", "name": "One", "script_path": "/x/one.py", "args": [],
         "custom_args": [{"name": "--a", "type": "text", "value": "1"}]},
    ])
    w4 = workflows.handle_create({"name": "Snap", "steps": [
        {"type": "sequential", "profile_id": "p1", "args": []},
    ]})

    write_profiles(store, [
        {"id": "p1", "name": "Renamed", "script_path": "/x/changed.py", "args": [], "custom_args": []},
    ])
    saved_w4 = next(w for w in workflows.handle_list() if w["id"] == w4["id"])
    assert saved_w4["steps"][0]["profile"]["name"] == "One"
    assert saved_w4["steps"][0]["profile"]["script_path"] == "/x/one.py"


def test_handle_create_keeps_existing_snapshot_on_upsert(store):
    write_profiles(store, [
        {"id": "p1", "name": "One", "script_path": "/x/one.py", "args": [], "custom_args": []},
    ])
    w4 = workflows.handle_create({"name": "Snap", "steps": [
        {"type": "sequential", "profile_id": "p1", "args": []},
    ]})

    workflows.handle_create({"id": w4["id"], "name": "Snap Edited", "steps": [
        {"type": "sequential", "profile_id": "p1",
         "profile": {"id": "p1", "name": "One", "script_path": "/x/one.py", "args": [], "custom_args": []},
         "args": []},
    ]})
    saved_w4 = next(w for w in workflows.handle_list() if w["id"] == w4["id"])
    assert saved_w4["steps"][0]["profile"]["name"] == "One"
    assert saved_w4["steps"][0]["profile"]["script_path"] == "/x/one.py"


def test_handle_duplicate_copies_workflow_with_steps_and_snapshots(store):
    write_profiles(store, [
        {"id": "p1", "name": "One", "script_path": "/x/one.py", "args": [], "custom_args": []},
    ])
    w4 = workflows.handle_create({"name": "Snap", "steps": [
        {"type": "sequential", "profile_id": "p1", "args": []},
    ]})
    source = next(w for w in store.read("workflows") if w["id"] == w4["id"])

    dup = workflows.handle_duplicate(w4["id"])
    assert dup["id"].startswith("workflow_") and dup["id"] != w4["id"]
    assert dup["name"] == "Snap (copy)"
    saved = store.read("workflows")
    dup_saved = next(w for w in saved if w["id"] == dup["id"])
    assert [w["id"] for w in saved][-2:] == [w4["id"], dup["id"]]
    assert dup_saved["steps"] == source["steps"]
    assert dup_saved["steps"][0]["profile"]["name"] == "One"


def test_handle_duplicate_deep_copies_workflow_steps(store):
    write_profiles(store, [
        {"id": "p1", "name": "One", "script_path": "/x/one.py", "args": [], "custom_args": []},
    ])
    w4 = workflows.handle_create({"name": "Snap", "steps": [
        {"type": "sequential", "profile_id": "p1", "args": []},
    ]})
    dup = workflows.handle_duplicate(w4["id"])

    source = next(w for w in store.read("workflows") if w["id"] == w4["id"])
    source["steps"][0]["profile"]["name"] = "Mutated"
    workflows.handle_create({"id": w4["id"], **source})
    saved = store.read("workflows")
    dup_saved = next(w for w in saved if w["id"] == dup["id"])
    assert dup_saved["steps"][0]["profile"]["name"] == "One", dup_saved


def test_handle_duplicate_keeps_workflow_names_unique_across_repeats(store):
    w4 = workflows.handle_create({"name": "Snap", "steps": []})
    dup = workflows.handle_duplicate(w4["id"])
    dup2 = workflows.handle_duplicate(w4["id"])
    assert dup["name"] == "Snap (copy)"
    assert dup2["name"] == "Snap (copy 2)"


def test_handle_duplicate_returns_none_for_unknown_workflows(store):
    assert workflows.handle_duplicate("ghost_id") is None


def test_handle_create_persists_group_field(store):
    w = workflows.handle_create({"name": "Grouped", "steps": [], "group": "folder_456"})
    saved = store.read("workflows")
    assert saved[0]["group"] == "folder_456"


def test_handle_create_upsert_strips_empty_group(store):
    w = workflows.handle_create({"name": "G", "steps": [], "group": "f1"})
    workflows.handle_create({"id": w["id"], "name": "G Updated", "steps": []})
    saved = store.read("workflows")
    assert saved[0].get("group") == "" or "group" not in saved[0]


def test_handle_duplicate_preserves_group(store):
    w = workflows.handle_create({"name": "G", "steps": [], "group": "f1"})
    dup = workflows.handle_duplicate(w["id"])
    assert dup.get("group") == "f1"
