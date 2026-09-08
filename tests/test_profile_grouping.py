import re
from pathlib import Path

COMPONENTS = Path(__file__).resolve().parent.parent / "static" / "js" / "components"
STATIC_JS = Path(__file__).resolve().parent.parent / "static" / "js"


# --- state.js: one global tag list shared by profiles and workflows ---

def test_state_has_one_global_tag_signal():
    src = (STATIC_JS / "state.js").read_text()
    assert "export const tags = signal(" in src, "global tags signal missing"
    assert "export const profileTags" not in src, "per-panel profileTags signal should be gone"
    assert "export const workflowTags" not in src, "per-panel workflowTags signal should be gone"
    assert "export const selectedProfileTag" in src, "selectedProfileTag signal missing"
    assert "export const selectedWorkflowTag" in src, "selectedWorkflowTag signal missing"


def test_state_merges_legacy_tag_lists_into_the_global_one():
    src = (STATIC_JS / "state.js").read_text()
    for key in ("profileTags", "profileFolders", "workflowTags", "workflowFolders"):
        assert f"'{key}'" in src, f"legacy localStorage key '{key}' is not migrated"
    assert "seen" in src, "merged legacy lists must be deduplicated by id"


def test_state_persists_tags_to_localstorage():
    src = (STATIC_JS / "state.js").read_text()
    assert "localStorage.setItem" in src, "tags not persisted to localStorage"
    assert "subscribe" in src, "tags not subscribed for persistence"


def test_state_has_tag_crud_helpers():
    src = (STATIC_JS / "state.js").read_text()
    assert "export function addTag(" in src, "addTag helper missing"
    assert "export function renameTag(" in src, "renameTag helper missing"
    assert "export function deleteTag(" in src, "deleteTag helper missing"
    assert "export function reorderTags(" in src, "reorderTags helper missing"


# --- api.js: legacy single-`group` items are normalized on load ---

def test_api_folds_legacy_group_field_into_tags_array():
    src = (STATIC_JS / "api.js").read_text()
    assert "function normalizeTags(" in src, "no legacy tag normalization on load"
    assert "item.tags || []" in src and "item.group || ''" in src, \
        "normalization must combine the tags array with the legacy group value"
    assert re.search(r"api\('GET', '/api/profiles'\)\)\.map\(normalizeTags\)", src), \
        "profiles are not normalized on load"
    assert re.search(r"api\('GET', '/api/workflows'\)\)\.map\(normalizeTags\)", src), \
        "workflows are not normalized on load"


def test_api_normalization_drops_unknown_tag_ids():
    src = (STATIC_JS / "api.js").read_text()
    assert "known.has(id)" in src, \
        "tag ids whose tag was deleted must be dropped so no 'Unknown' groupings linger"
    assert "TRASH_GROUP" in src, "the trash marker must never be treated as a tag id"


# --- ItemList.js: flat sortable list + trash section ---

def test_item_list_exists_and_is_exported():
    src = (COMPONENTS / "ItemList.js").read_text()
    assert "export function ItemList(" in src, "ItemList not exported"


def test_item_list_renders_a_flat_sortable_list():
    src = (COMPONENTS / "ItemList.js").read_text()
    assert "import { SortableList }" in src, "ItemList does not import SortableList"
    assert "<${SortableList}" in src, "ItemList does not render SortableList"
    assert "getTags" in src, "ItemList has no getTags prop (items carry several tags)"


def test_item_list_filters_by_selected_tag():
    src = (COMPONENTS / "ItemList.js").read_text()
    assert "selectedTag" in src, "ItemList has no selectedTag prop"
    assert "untagged" in src, "ItemList does not handle the 'untagged' filter"
    assert re.search(r"if\s*\(\s*selectedTag\s*\)", src), \
        "ItemList does not filter by selectedTag"


def test_item_list_keeps_hidden_items_in_place_when_reordering_filtered():
    src = (COMPONENTS / "ItemList.js").read_text()
    assert "subsetIds" in src, \
        "reordering a filtered subset must splice back into the full list"


def test_item_list_has_trash_section():
    src = (COMPONENTS / "ItemList.js").read_text()
    assert "TRASH_GROUP" in src
    assert "renderTrashSection" in src


def test_item_list_trash_collapsed_by_default():
    src = (COMPONENTS / "ItemList.js").read_text()
    assert re.search(r"useState\(\{\s*\[TRASH_GROUP\]\s*:\s*true\s*\}", src), \
        "Trash section should be collapsed by default"


def test_item_list_trash_always_visible():
    src = (COMPONENTS / "ItemList.js").read_text()
    assert "Trash is empty" in src, "Trash section should render even when empty"
    assert not re.search(r"if\s*\(\s*!trashItems\.length\s*\)\s*return", src), \
        "Trash section must not be hidden when it has no items"


def test_item_list_trash_has_no_reorder():
    src = (COMPONENTS / "ItemList.js").read_text()
    assert "onReorder=${() => {}}" in src, "Trash section should not allow reordering"


# --- TagFilter.js ---

def test_tag_filter_exists():
    src = (COMPONENTS / "TagFilter.js").read_text()
    assert "export function TagFilter(" in src, "TagFilter not exported"


def test_tag_filter_counts_items_per_tag():
    src = (COMPONENTS / "TagFilter.js").read_text()
    assert "tagCounts" in src, "TagFilter does not count items per tag"
    assert "untaggedCount" in src, "TagFilter does not count untagged items"
    assert "getTags" in src, "TagFilter does not read the item's tags array"


def test_tag_filter_excludes_trash_items():
    src = (COMPONENTS / "TagFilter.js").read_text()
    assert "TRASH_GROUP" in src
    assert "(item.group || '') === TRASH_GROUP" in src, \
        "TagFilter should skip trash items"


def test_tag_filter_has_all_pill():
    src = (COMPONENTS / "TagFilter.js").read_text()
    assert re.search(r'Pill\(.*All', src) or "All" in src, \
        "TagFilter does not have an All filter pill"


def test_tag_filter_pills_are_sticky():
    src = (COMPONENTS / "TagFilter.js").read_text()
    assert "sticky top-0" in src, "TagFilter pills are not pinned to the top of the scroll area"
    assert "bg-gray-50 dark:bg-gray-900" in src, \
        "TagFilter pills have no opaque background to mask items scrolling underneath"


# --- ProfileList.js / WorkflowList.js ---

def test_profile_list_uses_item_list():
    src = (COMPONENTS / "ProfileList.js").read_text()
    assert "import { ItemList }" in src, "ProfileList does not import ItemList"
    assert "<${ItemList}" in src, "ProfileList does not render ItemList"
    assert "import { TagFilter }" in src, "ProfileList does not import TagFilter"
    assert "<${TagFilter}" in src, "ProfileList does not render TagFilter"
    assert "tags.value" in src, "ProfileList does not use the global tags signal"
    assert "selectedProfileTag" in src, "ProfileList does not reference selectedProfileTag"


def test_workflow_list_uses_item_list():
    src = (COMPONENTS / "WorkflowList.js").read_text()
    assert "import { ItemList }" in src, "WorkflowList does not import ItemList"
    assert "<${ItemList}" in src, "WorkflowList does not render ItemList"
    assert "import { TagFilter }" in src, "WorkflowList does not import TagFilter"
    assert "<${TagFilter}" in src, "WorkflowList does not render TagFilter"
    assert "tags.value" in src, "WorkflowList does not use the global tags signal"
    assert "selectedWorkflowTag" in src, "WorkflowList does not reference selectedWorkflowTag"


# --- Modals: a profile/workflow can carry any number of tags ---

def test_profile_modal_has_multi_tag_toggles():
    src = (COMPONENTS / "ProfileModal.js").read_text()
    assert "tags" in (STATIC_JS / "state.js").read_text()
    assert "toggleTagId" in src, "ProfileModal has no multi-tag toggle"
    assert "tagIds.includes(t.id)" in src, "tag toggles do not reflect selection"
    assert not re.search(r"<select[^>]*value=\$\{group\}", src), \
        "ProfileModal still has a single-tag select"


def test_profile_modal_saves_tags_array():
    src = (COMPONENTS / "ProfileModal.js").read_text()
    assert "tags: tagIds" in src, "ProfileModal does not save the tags array"
    assert "group: ''" in src, \
        "ProfileModal must clear the legacy group field (it only marks trash now)"


def test_workflow_modal_has_multi_tag_toggles():
    src = (COMPONENTS / "WorkflowModal.js").read_text()
    assert "toggleTagId" in src, "WorkflowModal has no multi-tag toggle"
    assert "tagIds.includes(t.id)" in src, "tag toggles do not reflect selection"
    assert not re.search(r"<select[^>]*value=\$\{group\}", src), \
        "WorkflowModal still has a single-tag select"


def test_workflow_modal_saves_tags_array():
    src = (COMPONENTS / "WorkflowModal.js").read_text()
    assert "tags: tagIds" in src, "WorkflowModal does not save the tags array"
    assert "group: ''" in src, \
        "WorkflowModal must clear the legacy group field (it only marks trash now)"


# --- Cards: show the item's tags as chips ---

def test_profile_card_shows_tag_chips():
    src = (COMPONENTS / "ProfileCard.js").read_text()
    assert "itemTags" in src, "ProfileCard does not resolve its tags"
    assert "tags.value.find" in src, "ProfileCard does not look up the global tags signal"
    assert "tagColor(" in src, "ProfileCard does not tint chips with the tag's color"


def test_workflow_card_shows_tag_chips():
    src = (COMPONENTS / "WorkflowCard.js").read_text()
    assert "itemTags" in src, "WorkflowCard does not resolve its tags"
    assert "tags.value.find" in src, "WorkflowCard does not look up the global tags signal"
    assert "tagColor(" in src, "WorkflowCard does not tint chips with the tag's color"


# --- Tag colors ---

def test_tag_colors_module_defines_a_palette_with_default_fallback():
    src = (STATIC_JS / "tagColors.js").read_text()
    assert "export const TAG_COLORS" in src, "palette missing"
    assert "export const DEFAULT_TAG_COLOR" in src, "default color missing"
    assert "export function tagColor(" in src, "tagColor lookup missing"
    assert re.search(r"\|\|\s*TAG_COLORS\[0\]", src), \
        "an unknown/missing color must fall back to the default entry"


def test_tag_colors_entries_carry_chip_and_ring_classes():
    src = (STATIC_JS / "tagColors.js").read_text()
    assert "chip:" in src and "ring:" in src, "palette entries need chip and ring classes"
    assert "dark:bg-${id}-500/10" in src and "dark:text-${id}-400" in src, \
        "chip classes must cover dark mode"


def test_state_assigns_a_default_color_and_can_change_it():
    src = (STATIC_JS / "state.js").read_text()
    assert "color: tag.color || DEFAULT_TAG_COLOR" in src, \
        "tags saved before colors existed must load with a default color"
    assert "export function setTagColor(" in src, "setTagColor helper missing"
    assert "TAG_COLORS.find(c => !used.has(c.id))" in src, \
        "new tags should start on the first unused palette color"


def test_tag_manager_offers_a_color_picker_per_tag():
    src = (COMPONENTS / "TagManager.js").read_text()
    assert "setTagColor" in src, "TagManager does not apply color changes"
    assert "TAG_COLORS" in src, "TagManager does not render the palette"
    assert "colorFor" in src, "TagManager has no per-tag color-picker state"


def test_tag_filter_pills_use_the_tag_color():
    src = (COMPONENTS / "TagFilter.js").read_text()
    assert "tagColor(f)" in src, "pills are not tinted with the tag's color"


def test_modals_show_selected_tags_in_the_tag_color():
    for name in ("ProfileModal.js", "WorkflowModal.js"):
        src = (COMPONENTS / name).read_text()
        assert "tagColor(t)" in src, f"{name} does not tint tag toggles with the tag's color"


# --- TagManager: global tags, safe delete ---

def test_tag_manager_exists_and_exports():
    src = (COMPONENTS / "TagManager.js").read_text()
    assert "export function TagManager(" in src, "TagManager not exported"


def test_tag_manager_has_crud_operations():
    src = (COMPONENTS / "TagManager.js").read_text()
    assert "addTag" in src, "TagManager does not call addTag"
    assert "renameTag" in src, "TagManager does not call renameTag"
    assert "deleteTag" in src, "TagManager does not call deleteTag"
    assert "reorderTags" in src, "TagManager does not call reorderTags"


def test_tag_manager_is_global_across_profiles_and_workflows():
    src = (COMPONENTS / "TagManager.js").read_text()
    assert "[...profiles, ...workflows]" in src, \
        "TagManager must count tag usage across both profiles and workflows"
    assert "saveProfile" in src and "saveWorkflow" in src, \
        "TagManager must be able to update both kinds of item"


def test_tag_manager_delete_routes_through_confirm_modal():
    src = (COMPONENTS / "TagManager.js").read_text()
    assert "import { ConfirmModal } from './ConfirmModal.js';" in src, \
        "TagManager does not import ConfirmModal"
    assert "pendingDelete" in src, "TagManager has no pending-delete modal state"
    assert "<${ConfirmModal}" in src, "ConfirmModal is not rendered by TagManager"
    assert not re.search(r"confirm\(", src), "TagManager still uses native confirm()"


def test_tag_manager_delete_message_guards_against_no_pending_tag():
    src = (COMPONENTS / "TagManager.js").read_text()
    assert "const deleteMessage = pendingTag" in src, \
        "the delete message must be built only when a tag is actually pending " \
        "deletion — template literals evaluate eagerly, so reading pendingTag " \
        "otherwise crashes the whole TagManager"


def test_tag_manager_delete_untags_affected_items():
    src = (COMPONENTS / "TagManager.js").read_text()
    assert "item.tags.filter(t => t !== pendingDelete)" in src, \
        "deleting a tag must remove it from every item that uses it"
    assert "deleteTag(tagsSignal, pendingDelete)" in src, \
        "deleting a tag must remove the tag itself"
    assert "reloadItems" in src, "changes must be reloaded from the server after untagging"


# --- app.js ---

def test_app_renders_one_global_tag_manager():
    src = (STATIC_JS / "app.js").read_text()
    assert "import { TagManager }" in src, "app.js does not import TagManager"
    assert "<${TagManager}" in src, "app.js does not render TagManager"
    assert "tagManagerOpen" in src, "app.js has no tag manager open state"
    assert "tagManagerType" not in src, \
        "tags are global — there is one manager, not one per panel"


def test_app_both_panels_open_the_same_tag_manager():
    src = (STATIC_JS / "app.js").read_text()
    assert src.count("onClick=${() => setTagManagerOpen(true)}") >= 2, \
        "the profiles and workflows panels must both open the tag manager"


def test_app_wires_tag_manager_to_both_collections():
    src = (STATIC_JS / "app.js").read_text()
    assert "profiles=${profiles.value}" in src, "TagManager does not receive profiles"
    assert "workflows=${workflows.value}" in src, "TagManager does not receive workflows"
    assert "saveProfile=${saveProfile}" in src, "TagManager cannot save profiles"
    assert "saveWorkflow=${saveWorkflow}" in src, "TagManager cannot save workflows"
    assert "reloadItems=" in src, "TagManager cannot reload after untagging"
