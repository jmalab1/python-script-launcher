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
    for signal in ("auditPage", "auditData", "auditAction", "auditEntity",
                   "auditName", "auditSince", "auditUntil"):
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
    assert "restoreAuditEntry" not in src, "restore-from-audit must be removed (trash is the restore path)"


def test_audit_table_has_action_and_entity_filters():
    src = read(COMPONENTS / "AuditTable.js")
    assert "<select value=${auditAction.value}" in src
    assert "<select value=${auditEntity.value}" in src
    for action in ("created", "updated", "deleted", "reordered", "restored", "run_now"):
        assert f'value="{action}"' in src, f"missing filter option for {action}"
    for entity in ("profile", "workflow", "schedule"):
        assert f'value="{entity}"' in src, f"missing filter option for {entity}"


def test_audit_filters_include_search_dates_and_clear():
    src = read(COMPONENTS / "AuditTable.js")
    assert "<${SearchInput} value=${auditName.value}" in src, "audit filter bar needs a name search"
    assert "onSince=${(since) => update(auditSince, since)}" in src
    assert "onUntil=${(until) => update(auditUntil, until)}" in src
    assert "auditPage.value = 1" in src, "filter changes must reset to page 1"
    assert "Clear" in src, "active filters must offer a clear button"


def test_audit_table_rows_have_no_restore_action():
    src = read(COMPONENTS / "AuditTable.js")
    assert "confirmRestore" not in src, "restore must not be offered from audit rows"
    assert "onRestore" not in src, "detail modal must not offer restore"
    assert "restoreAuditEntry" not in src, "restore api must not be used"
    assert "deleteAuditEntry" not in src, "delete functionality should be removed"


def test_audit_detail_modal_shows_before_and_after_snapshots():
    src = read(COMPONENTS / "AuditTable.js")
    assert "fetchAuditDetail(e.id)" in src, "row click must fetch the full entry"
    assert "JSON.stringify(entry.before, null, 2)" in src
    assert "JSON.stringify(entry.after, null, 2)" in src
    assert "JSON.stringify(entry.details, null, 2)" in src


def test_audit_table_uses_shared_pagination():
    src = read(COMPONENTS / "AuditTable.js")
    assert "<${Pagination} data=${data} pageSignal=${pageSignal} onLoad=${onLoad} />" in src
    assert "ConfirmModal" not in src, "confirm modal should not be used for audit entries"


def test_audit_table_header_is_sticky_while_scrolling():
    src = read(COMPONENTS / "AuditTable.js")
    assert 'class="data-table ' in src, "the table must be marked .data-table so index.html's sticky header rule applies"
