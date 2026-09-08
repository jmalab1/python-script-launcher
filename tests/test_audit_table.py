import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPONENTS = ROOT / "static" / "js" / "components"
JS = ROOT / "static" / "js"


def read(path):
    return path.read_text()


def test_audit_panel_is_registered_as_a_valid_panel():
    state = read(JS / "state.js")
    assert re.search(r"export const PANELS = \[[^\]]*'audit'", state), "PANELS must include 'audit'"
    for signal in ("auditPage", "auditData", "auditAction", "auditEntity"):
        assert f"export const {signal}" in state, f"missing {signal} signal"


def test_sidebar_offers_audit_in_desktop_nav_and_mobile_drawer():
    src = read(COMPONENTS / "Sidebar.js")
    assert src.count("showPanel('audit')") == 3, "desktop nav, mobile drawer, and mobile header must all link to audit"
    assert src.count("Audit\n                </button>") == 2, "desktop nav and drawer need an Audit button"
    assert ">Audit</button>" in src, "mobile header quick-switch needs an Audit button"


def test_app_renders_audit_panel_and_loads_data_on_switch():
    src = read(JS / "app.js")
    assert "import { AuditTable } from './components/AuditTable.js'" in src
    assert "currentPanel.value === 'audit'" in src
    assert "loadAudit()" in src


def test_audit_api_calls_hit_the_audit_endpoints():
    src = read(JS / "api.js")
    assert re.search(r"api\('GET', '/api/audit\?' \+ params", src)
    assert "auditAction.value" in src and "auditEntity.value" in src, "filters must be sent with the list request"
    assert "api('GET', '/api/audit/' + entryId)" in src
    assert "api('DELETE', '/api/audit/' + entryId)" in src
    assert re.search(r"api\('POST', `/api/audit/\$\{entryId\}/restore`\)", src)


def test_audit_table_has_action_and_entity_filters():
    src = read(COMPONENTS / "AuditTable.js")
    assert "<select value=${auditAction.value}" in src
    assert "<select value=${auditEntity.value}" in src
    for action in ("created", "updated", "deleted", "reordered", "restored"):
        assert f'value="{action}"' in src, f"missing filter option for {action}"


def test_audit_table_rows_offer_restore_and_delete_actions():
    src = read(COMPONENTS / "AuditTable.js")
    assert "isDeleted" in src and "confirmRestore(e)" in src, "deleted rows must expose a restore button"
    assert "deleteAuditEntry(pendingDelete.id)" in src


def test_audit_detail_modal_shows_before_and_after_snapshots():
    src = read(COMPONENTS / "AuditTable.js")
    assert "fetchAuditDetail(e.id)" in src, "row click must fetch the full entry"
    assert "JSON.stringify(entry.before, null, 2)" in src
    assert "JSON.stringify(entry.after, null, 2)" in src
    assert "JSON.stringify(entry.details, null, 2)" in src
    assert "action === 'deleted'" in src, "restore must only be offered for deleted entries"


def test_audit_table_uses_shared_pagination_and_confirm_modal():
    src = read(COMPONENTS / "AuditTable.js")
    assert "<${Pagination} data=${data} pageSignal=${pageSignal} onLoad=${onLoad} />" in src
    assert src.count("<${ConfirmModal}") >= 1, "delete needs confirmation"
