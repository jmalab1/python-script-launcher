import time

import launcher.api.profiles as profiles


def test_handle_list_empty(store):
    assert profiles.handle_list() == []


def test_handle_create_assigns_id_and_persists(store):
    p1 = profiles.handle_create({"name": "One", "script_path": "/tmp/a.py", "args": []})
    assert p1["id"].startswith("profile_")
    saved = store.read("profiles")
    assert [p["id"] for p in saved] == [p1["id"]]


def test_handle_create_upserts_on_duplicate_id(store):
    p1 = profiles.handle_create({"name": "One", "script_path": "/tmp/a.py", "args": []})
    profiles.handle_create({"id": p1["id"], "name": "One Updated", "script_path": "/tmp/a.py", "args": []})
    saved = store.read("profiles")
    assert len(saved) == 1 and saved[0]["name"] == "One Updated"


def test_handle_create_keeps_explicit_ids(store):
    p2 = profiles.handle_create({"id": "custom", "name": "Two"})
    assert p2["id"] == "custom"


def test_handle_delete_removes_only_target(store):
    p1 = profiles.handle_create({"name": "One", "script_path": "/tmp/a.py", "args": []})
    profiles.handle_create({"id": "custom", "name": "Two"})
    time.sleep(0.002)
    p3 = profiles.handle_create({"name": "Three"})
    profiles.handle_delete("custom")
    saved = store.read("profiles")
    ids = [p["id"] for p in saved]
    assert "custom" in ids and p1["id"] in ids and p3["id"] in ids
    trashed = next(p for p in saved if p["id"] == "custom")
    assert trashed["group"] == "__trash__"


def test_handle_reorder_applies_order_and_survives_unknown_or_empty_ids(store):
    p1 = profiles.handle_create({"name": "One", "script_path": "/tmp/a.py", "args": []})
    time.sleep(0.002)
    p3 = profiles.handle_create({"name": "Three"})
    ids = [p["id"] for p in profiles.handle_list()]
    assert ids == [p1["id"], p3["id"]]

    profiles.handle_reorder({"order": list(reversed(ids))})
    assert [p["id"] for p in profiles.handle_list()] == list(reversed(ids))

    profiles.handle_reorder({"order": [p3["id"], "ghost_id"]})
    after = [p["id"] for p in profiles.handle_list()]
    assert after == [p3["id"], p1["id"]], after

    profiles.handle_reorder({"order": None})
    assert [p["id"] for p in profiles.handle_list()] == [p3["id"], p1["id"]]


def test_handle_duplicate_copies_profile_with_new_id_and_unique_name(store):
    profiles.handle_create({"id": "p1", "name": "One", "script_path": "/tmp/a.py", "args": []})
    p3 = profiles.handle_create({"id": "p3", "name": "Three", "script_path": "/tmp/c.py", "args": []})
    target = next(p for p in store.read("profiles") if p["id"] == p3["id"])
    target["custom_args"] = [{"name": "--flag", "type": "text", "value": "1"}]
    profiles.handle_create(target)

    dup = profiles.handle_duplicate(p3["id"])
    assert dup["id"].startswith("profile_") and dup["id"] != p3["id"]
    assert dup["name"] == "Three (copy)"
    saved = store.read("profiles")
    ids = [p["id"] for p in saved]
    assert len(saved) == 3
    assert ids[ids.index(p3["id"]) + 1] == dup["id"]


def test_handle_duplicate_deep_copies_custom_args(store):
    p3 = profiles.handle_create({"id": "p3", "name": "Three", "script_path": "/tmp/c.py", "args": []})
    target = next(p for p in store.read("profiles") if p["id"] == p3["id"])
    target["custom_args"] = [{"name": "--flag", "type": "text", "value": "1"}]
    profiles.handle_create(target)
    dup = profiles.handle_duplicate(p3["id"])

    target["custom_args"][0]["value"] = "changed"
    profiles.handle_create(target)
    saved = store.read("profiles")
    dup_saved = next(p for p in saved if p["id"] == dup["id"])
    assert dup_saved["custom_args"][0]["value"] == "1", dup_saved


def test_handle_duplicate_keeps_ids_and_names_unique_across_repeats(store):
    p3 = profiles.handle_create({"id": "p3", "name": "Three", "script_path": "/tmp/c.py", "args": []})
    dup = profiles.handle_duplicate(p3["id"])
    dup2 = profiles.handle_duplicate(p3["id"])
    dup3 = profiles.handle_duplicate(p3["id"])
    assert dup2["id"] != dup3["id"] and dup2["id"] != dup["id"]
    assert dup2["name"] == "Three (copy 2)" and dup3["name"] == "Three (copy 3)"


def test_handle_duplicate_returns_none_for_unknown_profiles(store):
    assert profiles.handle_duplicate("ghost_id") is None


def test_handle_create_persists_group_field(store):
    p = profiles.handle_create({"name": "Grouped", "script_path": "/tmp/a.py", "args": [], "group": "tag_123"})
    saved = store.read("profiles")
    assert saved[0]["group"] == "tag_123"


def test_handle_create_strips_empty_group(store):
    p = profiles.handle_create({"name": "NoGroup", "script_path": "/tmp/a.py", "args": [], "group": ""})
    saved = store.read("profiles")
    assert "group" not in saved[0] or saved[0].get("group") == ""


def test_handle_create_upsert_preserves_group(store):
    p = profiles.handle_create({"name": "G", "script_path": "/tmp/a.py", "args": [], "group": "f1"})
    profiles.handle_create({"id": p["id"], "name": "G Updated", "script_path": "/tmp/a.py", "args": []})
    saved = store.read("profiles")
    assert saved[0].get("group") == "" or "group" not in saved[0]


def test_handle_duplicate_preserves_group(store):
    p = profiles.handle_create({"name": "G", "script_path": "/tmp/a.py", "args": [], "group": "f1"})
    dup = profiles.handle_duplicate(p["id"])
    assert dup.get("group") == "f1"


def test_handle_create_upsert_keeps_the_items_position(store):
    profiles.handle_create({"id": "a", "name": "A", "script_path": "/tmp/a.py", "args": []})
    profiles.handle_create({"id": "b", "name": "B", "script_path": "/tmp/b.py", "args": []})
    profiles.handle_create({"id": "c", "name": "C", "script_path": "/tmp/c.py", "args": []})
    profiles.handle_reorder({"order": ["c", "a", "b"]})

    profiles.handle_create({"id": "a", "name": "A Edited", "script_path": "/tmp/a.py", "args": []})

    saved = store.read("profiles")
    assert [p["id"] for p in saved] == ["c", "a", "b"], \
        "editing a profile must not move it in the drag-ordered list"
    assert next(p for p in saved if p["id"] == "a")["name"] == "A Edited"
