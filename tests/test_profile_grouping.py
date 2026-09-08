import re
from pathlib import Path

COMPONENTS = Path(__file__).resolve().parent.parent / "static" / "js" / "components"
STATIC_JS = Path(__file__).resolve().parent.parent / "static" / "js"


def test_state_has_folder_signals():
    src = (STATIC_JS / "state.js").read_text()
    assert "export const profileFolders" in src, "profileFolders signal missing"
    assert "export const workflowFolders" in src, "workflowFolders signal missing"
    assert "export const selectedProfileFolder" in src, "selectedProfileFolder signal missing"
    assert "export const selectedWorkflowFolder" in src, "selectedWorkflowFolder signal missing"


def test_state_has_folder_crud_helpers():
    src = (STATIC_JS / "state.js").read_text()
    assert "export function addFolder(" in src, "addFolder helper missing"
    assert "export function renameFolder(" in src, "renameFolder helper missing"
    assert "export function deleteFolder(" in src, "deleteFolder helper missing"
    assert "export function reorderFolders(" in src, "reorderFolders helper missing"


def test_state_persists_folders_to_localstorage():
    src = (STATIC_JS / "state.js").read_text()
    assert "localStorage.setItem" in src, "folders not persisted to localStorage"
    assert "subscribe" in src, "folders not subscribed for persistence"


def test_grouped_sortable_list_exists():
    src = (COMPONENTS / "GroupedSortableList.js").read_text()
    assert "export function GroupedSortableList(" in src, "GroupedSortableList not exported"


def test_grouped_sortable_list_renders_folders():
    src = (COMPONENTS / "GroupedSortableList.js").read_text()
    assert "collapsed" in src, "GroupedSortableList has no collapse state"
    assert "toggleFolder" in src, "GroupedSortableList has no toggle function"
    assert "SortableList" in src, "GroupedSortableList does not use SortableList"


def test_grouped_sortable_list_handles_selected_filter():
    src = (COMPONENTS / "GroupedSortableList.js").read_text()
    assert "selectedFolder" in src, "GroupedSortableList has no selectedFolder prop"
    assert re.search(r'if\s*\(\s*selectedFolder\s*\)', src), \
        "GroupedSortableList does not filter by selectedFolder"


def test_grouped_sortable_list_preserves_reorder_across_groups():
    src = (COMPONENTS / "GroupedSortableList.js").read_text()
    assert "makeGroupReorderFn" in src, "GroupedSortableList missing makeGroupReorderFn"
    assert "onReorder" in src, "GroupedSortableList does not call onReorder"


def test_folder_manager_exists_and_exports():
    src = (COMPONENTS / "FolderManager.js").read_text()
    assert "export function FolderManager(" in src, "FolderManager not exported"


def test_folder_manager_has_crud_operations():
    src = (COMPONENTS / "FolderManager.js").read_text()
    assert "addFolder" in src, "FolderManager does not call addFolder"
    assert "renameFolder" in src, "FolderManager does not call renameFolder"
    assert "deleteFolder" in src, "FolderManager does not call deleteFolder"
    assert "reorderFolders" in src, "FolderManager does not call reorderFolders"


def test_folder_manager_has_inline_rename():
    src = (COMPONENTS / "FolderManager.js").read_text()
    assert "editingId" in src, "FolderManager has no inline rename state"
    assert "handleKeyDown" in src, "FolderManager has no keyboard handler"
    assert "Enter" in src, "FolderManager does not handle Enter key"
    assert "handleRename" in src, "FolderManager does not have handleRename function"


def test_folder_filter_exists():
    src = (COMPONENTS / "FolderFilter.js").read_text()
    assert "export function FolderFilter(" in src, "FolderFilter not exported"


def test_folder_filter_counts_items_per_folder():
    src = (COMPONENTS / "FolderFilter.js").read_text()
    assert "folderCounts" in src, "FolderFilter does not count items per folder"
    assert "ungroupedCount" in src, "FolderFilter does not count ungrouped items"


def test_folder_filter_has_all_pill():
    src = (COMPONENTS / "FolderFilter.js").read_text()
    assert re.search(r'Pill\(.*All', src) or "All" in src, \
        "FolderFilter does not have an All filter pill"


def test_profile_list_uses_grouped_sortable_list():
    src = (COMPONENTS / "ProfileList.js").read_text()
    assert "import { GroupedSortableList }" in src, \
        "ProfileList does not import GroupedSortableList"
    assert "<${GroupedSortableList}" in src, \
        "ProfileList does not render GroupedSortableList"
    assert "import { FolderFilter }" in src, \
        "ProfileList does not import FolderFilter"
    assert "<${FolderFilter}" in src, \
        "ProfileList does not render FolderFilter"
    assert "profileFolders" in src, \
        "ProfileList does not reference profileFolders"
    assert "selectedProfileFolder" in src, \
        "ProfileList does not reference selectedProfileFolder"


def test_workflow_list_uses_grouped_sortable_list():
    src = (COMPONENTS / "WorkflowList.js").read_text()
    assert "import { GroupedSortableList }" in src, \
        "WorkflowList does not import GroupedSortableList"
    assert "<${GroupedSortableList}" in src, \
        "WorkflowList does not render GroupedSortableList"
    assert "import { FolderFilter }" in src, \
        "WorkflowList does not import FolderFilter"
    assert "<${FolderFilter}" in src, \
        "WorkflowList does not render FolderFilter"
    assert "workflowFolders" in src, \
        "WorkflowList does not reference workflowFolders"
    assert "selectedWorkflowFolder" in src, \
        "WorkflowList does not reference selectedWorkflowFolder"


def test_profile_modal_has_folder_selector():
    src = (COMPONENTS / "ProfileModal.js").read_text()
    assert "profileFolders" in src, \
        "ProfileModal does not import profileFolders"
    assert re.search(r'<select[^>]*value=\$\{group\}[^>]*onChange=\$\{e => setGroup', src), \
        "ProfileModal has no folder select with group state"
    assert "No folder" in src, \
        "ProfileModal folder selector missing 'No folder' option"


def test_workflow_modal_has_folder_selector():
    src = (COMPONENTS / "WorkflowModal.js").read_text()
    assert "workflowFolders" in src, \
        "WorkflowModal does not import workflowFolders"
    assert re.search(r'<select[^>]*value=\$\{group\}[^>]*onChange=\$\{e => setGroup', src), \
        "WorkflowModal has no folder select with group state"
    assert "No folder" in src, \
        "WorkflowModal folder selector missing 'No folder' option"


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


def test_app_renders_folder_manager_modal():
    src = (STATIC_JS / "app.js").read_text()
    assert "import { FolderManager }" in src, "app.js does not import FolderManager"
    assert "<${FolderManager}" in src, "app.js does not render FolderManager"
    assert "folderManagerOpen" in src, "app.js has no folder manager open state"
    assert "folderManagerType" in src, "app.js has no folder manager type state"


def test_app_has_manage_folders_button_in_profiles_panel():
    src = (STATIC_JS / "app.js").read_text()
    assert "setFolderManagerType('profiles')" in src, \
        "app.js profiles panel has no button to open folder manager for profiles"


def test_app_has_manage_folders_button_in_workflows_panel():
    src = (STATIC_JS / "app.js").read_text()
    assert "setFolderManagerType('workflows')" in src, \
        "app.js workflows panel has no button to open folder manager for workflows"
