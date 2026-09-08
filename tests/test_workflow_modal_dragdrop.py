import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(relpath):
    return (ROOT / relpath).read_text()


def test_sortablelist_supports_getkey_gripclass_gapclass_with_list_compatible_defaults():
    sortable = read("static/js/components/SortableList.js")
    for prop in ("getKey", "gripClass", "gapClass"):
        assert prop in sortable, f"SortableList is missing the {prop} prop"
    assert "const keyOf = getKey || (item => item.id);" in sortable
    assert "key=${keyOf(item)}" in sortable


def test_sortablelist_passes_the_row_index_to_renderitem():
    sortable = read("static/js/components/SortableList.js")
    assert "renderItem(item, i)" in sortable


def test_sortablelist_drag_events_are_safe_for_nested_lists():
    sortable = read("static/js/components/SortableList.js")
    ds = re.search(r"function handleDragStart\(e, i\) \{(.*?)\n    \}", sortable, re.S).group(1)
    assert "e.stopPropagation();" in ds
    do = re.search(r"function handleDragOver\(e, i\) \{(.*?)\n    \}", sortable, re.S).group(1)
    assert "if (dragIndex === null) return;" in do and "e.stopPropagation();" in do
    dp = re.search(r"function handleDrop\(e, i\) \{(.*?)\n    \}", sortable, re.S).group(1)
    assert "if (dragIndex === null) return;" in dp and "e.stopPropagation();" in dp


def test_sortablelist_drop_reorders_items_and_emits_the_new_array():
    sortable = read("static/js/components/SortableList.js")
    assert "const [moved] = next.splice(dragIndex, 1);" in sortable
    assert "next.splice(i, 0, moved);" in sortable
    assert "onReorder(next);" in sortable


def test_workflowmodal_renders_steps_via_sortablelist_with_stable_keys():
    modal = read("static/js/components/WorkflowModal.js")
    assert "import { SortableList } from './SortableList.js';" in modal
    assert "items=${localSteps}" in modal
    assert "getKey=${s => s._id}" in modal
    assert "onReorder=${reorderSteps}" in modal


def test_workflowmodal_assigns_stable_ids_to_steps_and_group_profiles():
    modal = read("static/js/components/WorkflowModal.js")
    # load steps, load group profiles, add step, add group, add group profile
    assert modal.count("_id: nextUid()") >= 4
    assert "_id: nextUid(), profiles:" in modal
    assert "_id: nextUid(), profile_id:" in modal


def test_workflowmodal_drag_sorts_profiles_inside_parallel_groups():
    modal = read("static/js/components/WorkflowModal.js")
    assert "items=${groupProfiles}" in modal
    assert "getKey=${p => p._id}" in modal
    assert "onReorder=${(next) => reorderGroupProfiles(i, next)}" in modal


def test_workflowmodal_no_longer_relies_on_move_up_down_buttons():
    modal = read("static/js/components/WorkflowModal.js")
    assert "function moveStep" not in modal and "upBtn" not in modal and "downBtn" not in modal


def test_handlesave_persists_clean_steps_without_local_only_fields():
    modal = read("static/js/components/WorkflowModal.js")
    save_block = modal[modal.index("const stepsToSave"):modal.index("await saveWorkflow")]
    assert not re.search(r"(?<![\w])_id\s*:", save_block), "handleSave persists local-only field _id"
    assert "_argsText:" not in save_block, "handleSave persists local-only field _argsText"
    assert "profile_id: p.profile_id" in save_block and "profile_id: s.profile_id" in save_block
