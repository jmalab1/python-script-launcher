import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SORTABLE = (ROOT / "static/js/components/SortableList.js").read_text()
MODAL = (ROOT / "static/js/components/WorkflowModal.js").read_text()

# --- SortableList generalization ---

# 1. supports custom keys, grip alignment, and row spacing (needed by the modal)
for prop in ("getKey", "gripClass", "gapClass"):
    assert prop in SORTABLE, f"SortableList is missing the {prop} prop"
assert "const keyOf = getKey || (item => item.id);" in SORTABLE
assert "key=${keyOf(item)}" in SORTABLE
print("PASS: SortableList supports getKey/gripClass/gapClass with list-compatible defaults")

# 2. renderItem receives the row index so callers can update by position
assert "renderItem(item, i)" in SORTABLE
print("PASS: SortableList passes the row index to renderItem")

# 3. nested lists don't steal each other's drag events:
#    - a row's dragstart never bubbles to an outer list
#    - dragover/drop are ignored when the active drag belongs to an outer list
ds = re.search(r"function handleDragStart\(e, i\) \{(.*?)\n    \}", SORTABLE, re.S).group(1)
assert "e.stopPropagation();" in ds
do = re.search(r"function handleDragOver\(e, i\) \{(.*?)\n    \}", SORTABLE, re.S).group(1)
assert "if (dragIndex === null) return;" in do and "e.stopPropagation();" in do
dp = re.search(r"function handleDrop\(e, i\) \{(.*?)\n    \}", SORTABLE, re.S).group(1)
assert "if (dragIndex === null) return;" in dp and "e.stopPropagation();" in dp
print("PASS: SortableList drag events are safe for nested lists")

# 4. drop still reorders via splice and reports the new array
assert "const [moved] = next.splice(dragIndex, 1);" in SORTABLE
assert "next.splice(i, 0, moved);" in SORTABLE
assert "onReorder(next);" in SORTABLE
print("PASS: SortableList drop reorders items and emits the new array")

# --- WorkflowModal wiring ---

# 5. steps render through SortableList with stable drag keys
assert "import { SortableList } from './SortableList.js';" in MODAL
assert "items=${localSteps}" in MODAL
assert "getKey=${s => s._id}" in MODAL
assert "onReorder=${reorderSteps}" in MODAL
print("PASS: WorkflowModal renders steps via SortableList with stable keys")

# 6. every step and group profile gets a stable id (on load and when added)
assert MODAL.count("_id: nextUid()") >= 4  # load steps, load group profiles, add step, add group, add group profile
assert "_id: nextUid(), profiles:" in MODAL
assert "_id: nextUid(), profile_id:" in MODAL
print("PASS: WorkflowModal assigns stable _ids to steps and group profiles")

# 7. profiles inside parallel groups are drag-sortable too
assert "items=${groupProfiles}" in MODAL
assert "getKey=${p => p._id}" in MODAL
assert "onReorder=${(next) => reorderGroupProfiles(i, next)}" in MODAL
print("PASS: WorkflowModal drag-sorts profiles inside parallel groups")

# 8. the old up/down buttons are gone in favor of drag handles
assert "function moveStep" not in MODAL and "upBtn" not in MODAL and "downBtn" not in MODAL
print("PASS: WorkflowModal no longer relies on move up/down buttons")

# 9. saved steps stay clean: local-only fields (_id/_argsText) are not persisted as keys
save_block = MODAL[MODAL.index("const stepsToSave"):MODAL.index("await saveWorkflow")]
assert not re.search(r"(?<![\w])_id\s*:", save_block), "handleSave persists local-only field _id"
assert "_argsText:" not in save_block, "handleSave persists local-only field _argsText"
assert "profile_id: p.profile_id" in save_block and "profile_id: s.profile_id" in save_block
print("PASS: handleSave persists clean steps without local-only fields")

print("ALL PASS")
