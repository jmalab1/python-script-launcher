import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPONENTS = ROOT / "static" / "js" / "components"
JS = ROOT / "static" / "js"


def read(path):
    return path.read_text()


def test_state_defines_filter_signals_for_history_and_audit():
    src = read(JS / "state.js")
    for signal in ("profileHistoryFilters", "workflowHistoryFilters",
                   "auditName", "auditSince", "auditUntil"):
        assert f"export const {signal}" in src, f"missing {signal} signal"


def test_api_sends_filter_params_with_list_requests():
    src = read(JS / "api.js")
    assert "addHistoryFilterParams(params, profileHistoryFilters.value)" in src
    assert "addHistoryFilterParams(params, workflowHistoryFilters.value)" in src
    assert "params.set('name', f.name)" in src
    assert "params.set('status', f.status)" in src
    assert "params.set('name', auditName.value)" in src


def test_api_converts_picked_days_to_inclusive_epoch_ranges():
    src = read(JS / "api.js")
    assert "Date.parse(day + 'T00:00:00') / 1000" in src, "since must be local midnight"
    assert "Date.parse(day + 'T23:59:59') / 1000" in src, "until must cover the whole picked day"


def test_list_filters_has_search_status_and_date_controls():
    src = read(COMPONENTS / "ListFilters.js")
    assert 'type="search"' in src
    assert "setTimeout" in src, "search input must debounce before committing"
    assert 'type="date"' in src, "date range needs two date pickers"
    for status in ("running", "completed", "failed"):
        assert f'<option value="{status}">' in src, f"missing status option {status}"
    assert "Clear" in src, "an active filter bar must offer a Clear button"


def test_filter_changes_reset_pagination_to_page_one():
    src = read(COMPONENTS / "ListFilters.js")
    assert "pageSignal.value = 1" in src, "changing filters must go back to page 1"


def test_history_table_renders_filters_in_populated_and_empty_states():
    src = read(COMPONENTS / "HistoryTable.js")
    assert "import { HistoryFilters, hasActiveFilters } from './ListFilters.js';" in src
    assert src.count("<${HistoryFilters}") == 2, "filter bar must render in both empty and populated states"
    assert "No runs match the current filters." in src, "empty state should say filters are active"


def test_app_passes_filter_state_to_history_tables():
    src = read(JS / "app.js")
    assert "filters=${profileHistoryFilters}" in src
    assert "filters=${workflowHistoryFilters}" in src
