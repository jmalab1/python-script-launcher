import re
from pathlib import Path

COMPONENTS = Path(__file__).resolve().parent.parent / "static" / "js" / "components"
STATIC_JS = Path(__file__).resolve().parent.parent / "static" / "js"


def test_state_has_tag_signals():
    src = (STATIC_JS / "state.js").read_text()
    assert "export const profileTags" in src, "profileTags signal missing"
    assert "export const workflowTags" in src, "workflowTags signal missing"
    assert "export const selectedProfileTag" in src, "selectedProfileTag signal missing"
    assert "export const selectedWorkflowTag" in src, "selectedWorkflowTag signal missing"


def test_state_has_tag_crud_helpers():
    src = (STATIC_JS / "state.js").read_text()
    assert "export function addTag(" in src, "addTag helper missing"
    assert "export function renameTag(" in src, "renameTag helper missing"
    assert "export function deleteTag(" in src, "deleteTag helper missing"
    assert "export function reorderTags(" in src, "reorderTags helper missing"


def test_state_persists_tags_to_localstorage():
    src = (STATIC_JS / "state.js").read_text()
    assert "localStorage.setItem" in src, "tags not persisted to localStorage"
    assert "subscribe" in src, "tags not subscribed for persistence"


def test_state_loads_legacy_folder_keys():
    src = (STATIC_JS / "state.js").read_text()
    assert "'profileFolders'" in src and "'workflowFolders'" in src, \
        "state.js does not fall back to legacy folder localStorage keys"


def test_grouped_sortable_list_exists():
    src = (COMPONENTS / "GroupedSortableList.js").read_text()
    assert "export function GroupedSortableList(" in src, "GroupedSortableList not exported"


def test_grouped_sortable_list_renders_tags():
    src = (COMPONENTS / "GroupedSortableList.js").read_text()
    assert "collapsed" in src, "GroupedSortableList has no collapse state"
    assert "toggleTag" in src, "GroupedSortableList has no toggle function"
    assert "SortableList" in src, "GroupedSortableList does not use SortableList"


def test_grouped_sortable_list_handles_selected_filter():
    src = (COMPONENTS / "GroupedSortableList.js").read_text()
    assert "selectedTag" in src, "GroupedSortableList has no selectedTag prop"
    assert re.search(r'if\s*\(\s*selectedTag\s*\)', src), \
        "GroupedSortableList does not filter by selectedTag"


def test_grouped_sortable_list_preserves_reorder_across_groups():
    src = (COMPONENTS / "GroupedSortableList.js").read_text()
    assert "makeGroupReorderFn" in src, "GroupedSortableList missing makeGroupReorderFn"
    assert "onReorder" in src, "GroupedSortableList does not call onReorder"


def test_tag_manager_exists_and_exports():
    src = (COMPONENTS / "TagManager.js").read_text()
    assert "export function TagManager(" in src, "TagManager not exported"


def test_tag_manager_has_crud_operations():
    src = (COMPONENTS / "TagManager.js").read_text()
    assert "addTag" in src, "TagManager does not call addTag"
    assert "renameTag" in src, "TagManager does not call renameTag"
    assert "deleteTag" in src, "TagManager does not call deleteTag"
    assert "reorderTags" in src, "TagManager does not call reorderTags"


def test_tag_manager_has_inline_rename():
    src = (COMPONENTS / "TagManager.js").read_text()
    assert "editingId" in src, "TagManager has no inline rename state"
    assert "handleKeyDown" in src, "TagManager has no keyboard handler"
    assert "Enter" in src, "TagManager does not handle Enter key"
    assert "handleRename" in src, "TagManager does not have handleRename function"


def test_tag_filter_exists():
    src = (COMPONENTS / "TagFilter.js").read_text()
    assert "export function TagFilter(" in src, "TagFilter not exported"


def test_tag_filter_counts_items_per_tag():
    src = (COMPONENTS / "TagFilter.js").read_text()
    assert "tagCounts" in src, "TagFilter does not count items per tag"
    assert "untaggedCount" in src, "TagFilter does not count untagged items"


def test_tag_filter_has_all_pill():
    src = (COMPONENTS / "TagFilter.js").read_text()
    assert re.search(r'Pill\(.*All', src) or "All" in src, \
        "TagFilter does not have an All filter pill"


def test_tag_filter_pills_are_sticky():
    src = (COMPONENTS / "TagFilter.js").read_text()
    assert "sticky top-0" in src, "TagFilter pills are not pinned to the top of the scroll area"
    assert "bg-gray-50 dark:bg-gray-900" in src, \
        "TagFilter pills have no opaque background to mask items scrolling underneath"


def test_profile_list_uses_grouped_sortable_list():
    src = (COMPONENTS / "ProfileList.js").read_text()
    assert "import { GroupedSortableList }" in src, \
        "ProfileList does not import GroupedSortableList"
    assert "<${GroupedSortableList}" in src, \
        "ProfileList does not render GroupedSortableList"
    assert "import { TagFilter }" in src, \
        "ProfileList does not import TagFilter"
    assert "<${TagFilter}" in src, \
        "ProfileList does not render TagFilter"
    assert "profileTags" in src, \
        "ProfileList does not reference profileTags"
    assert "selectedProfileTag" in src, \
        "ProfileList does not reference selectedProfileTag"


def test_workflow_list_uses_grouped_sortable_list():
    src = (COMPONENTS / "WorkflowList.js").read_text()
    assert "import { GroupedSortableList }" in src, \
        "WorkflowList does not import GroupedSortableList"
    assert "<${GroupedSortableList}" in src, \
        "WorkflowList does not render GroupedSortableList"
    assert "import { TagFilter }" in src, \
        "WorkflowList does not import TagFilter"
    assert "<${TagFilter}" in src, \
        "WorkflowList does not render TagFilter"
    assert "workflowTags" in src, \
        "WorkflowList does not reference workflowTags"
    assert "selectedWorkflowTag" in src, \
        "WorkflowList does not reference selectedWorkflowTag"


def test_profile_modal_has_tag_selector():
    src = (COMPONENTS / "ProfileModal.js").read_text()
    assert "profileTags" in src, \
        "ProfileModal does not import profileTags"
    assert re.search(r'<select[^>]*value=\$\{group\}[^>]*onChange=\$\{e => setGroup', src), \
        "ProfileModal has no tag select with group state"
    assert "No tag" in src, \
        "ProfileModal tag selector missing 'No tag' option"


def test_workflow_modal_has_tag_selector():
    src = (COMPONENTS / "WorkflowModal.js").read_text()
    assert "workflowTags" in src, \
        "WorkflowModal does not import workflowTags"
    assert re.search(r'<select[^>]*value=\$\{group\}[^>]*onChange=\$\{e => setGroup', src), \
        "WorkflowModal has no tag select with group state"
    assert "No tag" in src, \
        "WorkflowModal tag selector missing 'No tag' option"


def test_profile_modal_saves_group_field():
    src = (COMPONENTS / "ProfileModal.js").read_text()
    assert "group" in src, "ProfileModal does not handle group field"
    assert "profileData.group" in src or "profile.group" in src, \
        "ProfileModal does not include group in save data"


def test_workflow_modal_saves_group_field():
    src = (COMPONENTS / "WorkflowModal.js").read_text()
    assert "group" in src, "WorkflowModal does not handle group field"
    assert "workflowData.group" in src or "workflow.group" in src, \
        "WorkflowModal does not include group in save data"


def test_app_renders_tag_manager_modal():
    src = (STATIC_JS / "app.js").read_text()
    assert "import { TagManager }" in src, "app.js does not import TagManager"
    assert "<${TagManager}" in src, "app.js does not render TagManager"
    assert "tagManagerOpen" in src, "app.js has no tag manager open state"
    assert "tagManagerType" in src, "app.js has no tag manager type state"


def test_app_has_manage_tags_button_in_profiles_panel():
    src = (STATIC_JS / "app.js").read_text()
    assert "setTagManagerType('profiles')" in src, \
        "app.js profiles panel has no button to open tag manager for profiles"


def test_app_has_manage_tags_button_in_workflows_panel():
    src = (STATIC_JS / "app.js").read_text()
    assert "setTagManagerType('workflows')" in src, \
        "app.js workflows panel has no button to open tag manager for workflows"
