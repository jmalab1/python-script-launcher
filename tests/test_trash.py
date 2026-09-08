import re
from pathlib import Path

import launcher.api.profiles as profiles
import launcher.api.workflows as workflows

COMPONENTS = Path(__file__).resolve().parent.parent / "static" / "js" / "components"
STATIC_JS = Path(__file__).resolve().parent.parent / "static" / "js"


# --- Backend: profile soft-delete, restore, permanent-delete ---

def test_profile_soft_delete_sets_trash_group(store):
    p = profiles.handle_create({"name": "P1", "script_path": "/tmp/a.py"})
    profiles.handle_delete(p["id"])
    saved = store.read("profiles")
    assert len(saved) == 1
    assert saved[0]["group"] == "__trash__"
    assert saved[0]["id"] == p["id"]


def test_profile_soft_delete_noop_for_unknown(store):
    result = profiles.handle_delete("nonexistent")
    assert result == {"ok": True}
    assert store.read("profiles") == []


def test_profile_restore_clears_group(store):
    p = profiles.handle_create({"name": "P1", "script_path": "/tmp/a.py", "group": "f1"})
    profiles.handle_delete(p["id"])
    restored = profiles.handle_restore(p["id"])
    assert restored is not None
    assert restored["group"] == ""
    saved = store.read("profiles")
    assert saved[0]["group"] == ""


def test_profile_restore_noop_for_non_trashed(store):
    p = profiles.handle_create({"name": "P1", "script_path": "/tmp/a.py"})
    result = profiles.handle_restore(p["id"])
    assert result is None
    saved = store.read("profiles")
    assert saved[0].get("group", "") == ""


def test_profile_restore_noop_for_unknown(store):
    result = profiles.handle_restore("nonexistent")
    assert result is None


def test_profile_permanent_delete_removes_from_db(store):
    p = profiles.handle_create({"name": "P1", "script_path": "/tmp/a.py"})
    profiles.handle_delete(p["id"])
    profiles.handle_permanent_delete(p["id"])
    saved = store.read("profiles")
    assert len(saved) == 0


def test_profile_permanent_delete_noop_for_unknown(store):
    result = profiles.handle_permanent_delete("nonexistent")
    assert result == {"ok": True}


def test_profile_soft_delete_preserves_other_fields(store):
    p = profiles.handle_create({
        "name": "P1",
        "script_path": "/tmp/a.py",
        "args": ["--verbose"],
        "custom_args": [{"name": "--name", "type": "text", "value": "hi"}],
        "group": "f1",
    })
    profiles.handle_delete(p["id"])
    saved = store.read("profiles")
    assert saved[0]["script_path"] == "/tmp/a.py"
    assert saved[0]["args"] == ["--verbose"]
    assert saved[0]["custom_args"] == [{"name": "--name", "type": "text", "value": "hi"}]
    assert saved[0]["group"] == "__trash__"


# --- Backend: workflow soft-delete, restore, permanent-delete ---

def test_workflow_soft_delete_sets_trash_group(store):
    w = workflows.handle_create({"name": "W1", "steps": []})
    workflows.handle_delete(w["id"])
    saved = store.read("workflows")
    assert len(saved) == 1
    assert saved[0]["group"] == "__trash__"


def test_workflow_restore_clears_group(store):
    w = workflows.handle_create({"name": "W1", "steps": [], "group": "f1"})
    workflows.handle_delete(w["id"])
    restored = workflows.handle_restore(w["id"])
    assert restored is not None
    assert restored["group"] == ""


def test_workflow_permanent_delete_removes_from_db(store):
    w = workflows.handle_create({"name": "W1", "steps": []})
    workflows.handle_delete(w["id"])
    workflows.handle_permanent_delete(w["id"])
    saved = store.read("workflows")
    assert len(saved) == 0


# --- Frontend: state.js ---

def test_state_exports_trash_group_constant():
    src = (STATIC_JS / "state.js").read_text()
    assert "export const TRASH_GROUP" in src
    assert "__trash__" in src


# --- Frontend: api.js ---

def test_api_has_restore_profile():
    src = (STATIC_JS / "api.js").read_text()
    assert "export async function restoreProfile(" in src
    assert "/api/profiles/" in src
    assert "/restore" in src


def test_api_has_permanent_delete_profile():
    src = (STATIC_JS / "api.js").read_text()
    assert "export async function permanentDeleteProfile(" in src
    assert "/permanent" in src


def test_api_has_restore_workflow():
    src = (STATIC_JS / "api.js").read_text()
    assert "export async function restoreWorkflow(" in src
    assert "/api/workflows/" in src
    assert "/restore" in src


def test_api_has_permanent_delete_workflow():
    src = (STATIC_JS / "api.js").read_text()
    assert "export async function permanentDeleteWorkflow(" in src
    assert "/permanent" in src


# --- Frontend: GroupedSortableList.js ---

def test_grouped_sortable_list_has_trash_section():
    src = (COMPONENTS / "GroupedSortableList.js").read_text()
    assert "TRASH_GROUP" in src
    assert "renderTrashSection" in src


def test_grouped_sortable_list_trash_collapsed_by_default():
    src = (COMPONENTS / "GroupedSortableList.js").read_text()
    assert re.search(r"useState\(\{\s*\[TRASH_GROUP\]\s*:\s*true\s*\}", src), \
        "Trash section should be collapsed by default"


def test_grouped_sortable_list_separates_trash_items():
    src = (COMPONENTS / "GroupedSortableList.js").read_text()
    assert "trashItems" in src
    assert "TRASH_GROUP" in src


def test_grouped_sortable_list_trash_always_visible():
    src = (COMPONENTS / "GroupedSortableList.js").read_text()
    assert "Trash is empty" in src, "Trash section should render even when empty"
    assert not re.search(r"if\s*\(\s*!trashItems\.length\s*\)\s*return", src), \
        "Trash section must not be hidden when it has no items"


def test_grouped_sortable_list_trash_has_no_reorder():
    src = (COMPONENTS / "GroupedSortableList.js").read_text()
    assert re.search(r"onReorder.*\(\).*=>.*\{\}", src) or "onReorder=${() => {}}" in src, \
        "Trash section should not allow reordering"


# --- Frontend: ProfileCard.js ---

def test_profile_card_has_trash_imports():
    src = (COMPONENTS / "ProfileCard.js").read_text()
    assert "TRASH_GROUP" in src
    assert "restoreProfile" in src
    assert "permanentDeleteProfile" in src


def test_profile_card_has_trash_detection():
    src = (COMPONENTS / "ProfileCard.js").read_text()
    assert "isTrashed" in src
    assert "TRASH_GROUP" in src


def test_profile_card_has_restore_button():
    src = (COMPONENTS / "ProfileCard.js").read_text()
    assert "handleRestore" in src
    assert "Restore" in src


def test_profile_card_has_permanent_delete_modal():
    src = (COMPONENTS / "ProfileCard.js").read_text()
    assert "pendingPermanentDelete" in src
    assert "handleConfirmPermanentDelete" in src
    assert "Permanently delete" in src


def test_profile_card_delete_message_says_trash():
    src = (COMPONENTS / "ProfileCard.js").read_text()
    assert "to the trash" in src


# --- Frontend: WorkflowCard.js ---

def test_workflow_card_has_trash_imports():
    src = (COMPONENTS / "WorkflowCard.js").read_text()
    assert "TRASH_GROUP" in src
    assert "restoreWorkflow" in src
    assert "permanentDeleteWorkflow" in src


def test_workflow_card_has_trash_detection():
    src = (COMPONENTS / "WorkflowCard.js").read_text()
    assert "isTrashed" in src


def test_workflow_card_has_restore_button():
    src = (COMPONENTS / "WorkflowCard.js").read_text()
    assert "handleRestore" in src
    assert "Restore" in src


def test_workflow_card_has_permanent_delete_modal():
    src = (COMPONENTS / "WorkflowCard.js").read_text()
    assert "pendingPermanentDelete" in src
    assert "handleConfirmPermanentDelete" in src


def test_workflow_card_delete_message_says_trash():
    src = (COMPONENTS / "WorkflowCard.js").read_text()
    assert "to the trash" in src


# --- Frontend: TagFilter.js ---

def test_tag_filter_excludes_trash_items():
    src = (COMPONENTS / "TagFilter.js").read_text()
    assert "TRASH_GROUP" in src
    assert re.search(r"if\s*\(\s*g\s*===\s*TRASH_GROUP\s*\)\s*continue", src), \
        "TagFilter should skip trash items"


# --- Frontend: server.py routes ---

def test_server_has_restore_routes():
    src = (Path(__file__).resolve().parent.parent / "launcher" / "server.py").read_text()
    assert "/restore" in src
    assert "handle_restore" in src


def test_server_has_permanent_delete_routes():
    src = (Path(__file__).resolve().parent.parent / "launcher" / "server.py").read_text()
    assert "/permanent" in src
    assert "handle_permanent_delete" in src
