import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPONENTS = ROOT / "static" / "js" / "components"

try:
    # 1. ConfirmModal component exists and exports ConfirmModal
    modal_path = COMPONENTS / "ConfirmModal.js"
    assert modal_path.is_file(), "ConfirmModal.js is missing"
    modal_src = modal_path.read_text()
    assert "export function ConfirmModal(" in modal_src, "ConfirmModal is not exported"
    print("PASS: ConfirmModal component exists and is exported")

    # 2. ConfirmModal renders a proper dialog: backdrop, cancel and confirm buttons
    assert 'class="fixed inset-0 z-50"' in modal_src, "modal has no backdrop wrapper"
    assert re.search(r'onClick=\$\{onClose\}[^>]*disabled=\$\{busy\}', modal_src), "cancel button missing"
    assert 'onClick=${handleConfirm}' in modal_src, "confirm button missing"
    assert "Deleting..." in modal_src and "disabled:opacity-50" in modal_src, "confirm button lacks busy/disabled state"
    print("PASS: ConfirmModal renders backdrop, cancel and busy-guarded confirm buttons")

    # 3. ConfirmModal awaits onConfirm before closing so failures keep the modal open
    assert "await onConfirm();" in modal_src and "onClose();" in modal_src, "confirm flow does not await onConfirm before closing"
    print("PASS: ConfirmModal awaits onConfirm before closing")

    # 4. HistoryTable opens the modal instead of deleting immediately
    table_path = COMPONENTS / "HistoryTable.js"
    table_src = table_path.read_text()
    assert "import { ConfirmModal } from './ConfirmModal.js';" in table_src, "HistoryTable does not import ConfirmModal"
    assert "useState(null)" in table_src and "pendingDelete" in table_src, "HistoryTable has no pending-delete modal state"
    assert "setPendingDelete({ id: entryKey, name: e.name })" in table_src, "trash button does not open the delete modal"
    assert "<${ConfirmModal}" in table_src, "ConfirmModal is not rendered by HistoryTable"
    assert not re.search(r'onClick=\$\{\(ev\) => \{[^}]*deleteHistoryEntry', table_src), "trash button still deletes directly"
    print("PASS: HistoryTable routes run deletion through the confirm modal")
except AssertionError as exc:
    print(f"FAIL: {exc}")
    sys.exit(1)
