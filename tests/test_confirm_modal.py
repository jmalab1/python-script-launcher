import re
from pathlib import Path

COMPONENTS = Path(__file__).resolve().parent.parent / "static" / "js" / "components"


def test_confirm_modal_component_exists_and_is_exported():
    modal_src = (COMPONENTS / "ConfirmModal.js").read_text()
    assert "export function ConfirmModal(" in modal_src, "ConfirmModal is not exported"


def test_confirm_modal_renders_backdrop_cancel_and_busy_guarded_confirm_buttons():
    modal_src = (COMPONENTS / "ConfirmModal.js").read_text()
    assert 'class="fixed inset-0 z-50"' in modal_src, "modal has no backdrop wrapper"
    assert re.search(r'onClick=\$\{onClose\}[^>]*disabled=\$\{busy\}', modal_src), "cancel button missing"
    assert 'onClick=${handleConfirm}' in modal_src, "confirm button missing"
    assert "Deleting..." in modal_src and "disabled:opacity-50" in modal_src, \
        "confirm button lacks busy/disabled state"


def test_confirm_modal_awaits_onconfirm_before_closing():
    modal_src = (COMPONENTS / "ConfirmModal.js").read_text()
    assert "await onConfirm();" in modal_src and "onClose();" in modal_src, \
        "confirm flow does not await onConfirm before closing"


def test_history_table_routes_deletion_through_the_confirm_modal():
    table_src = (COMPONENTS / "HistoryTable.js").read_text()
    assert "import { ConfirmModal } from './ConfirmModal.js';" in table_src, \
        "HistoryTable does not import ConfirmModal"
    assert "useState(null)" in table_src and "pendingDelete" in table_src, \
        "HistoryTable has no pending-delete modal state"
    assert "setPendingDelete({ id: entryKey, name: e.name })" in table_src, \
        "trash button does not open the delete modal"
    assert "<${ConfirmModal}" in table_src, "ConfirmModal is not rendered by HistoryTable"
    assert not re.search(r'onClick=\$\{\(ev\) => \{[^}]*deleteHistoryEntry', table_src), \
        "trash button still deletes directly"


def test_profile_card_routes_deletion_through_the_confirm_modal():
    card_src = (COMPONENTS / "ProfileCard.js").read_text()
    assert "import { ConfirmModal } from './ConfirmModal.js';" in card_src, \
        "ProfileCard does not import ConfirmModal"
    assert "pendingDelete" in card_src, \
        "ProfileCard has no pending-delete modal state"
    assert "setPendingDelete" in card_src, \
        "delete button does not open the delete modal"
    assert "<${ConfirmModal}" in card_src, "ConfirmModal is not rendered by ProfileCard"
    assert not re.search(r'confirm\(', card_src), \
        "ProfileCard still uses native confirm()"


def test_workflow_card_routes_deletion_through_the_confirm_modal():
    card_src = (COMPONENTS / "WorkflowCard.js").read_text()
    assert "import { ConfirmModal } from './ConfirmModal.js';" in card_src, \
        "WorkflowCard does not import ConfirmModal"
    assert "pendingDelete" in card_src, \
        "WorkflowCard has no pending-delete modal state"
    assert "setPendingDelete" in card_src, \
        "delete button does not open the delete modal"
    assert "<${ConfirmModal}" in card_src, "ConfirmModal is not rendered by WorkflowCard"
    assert not re.search(r'confirm\(\s*[\'"]Delete this workflow', card_src), \
        "WorkflowCard still uses native confirm() for delete"
