import re
from pathlib import Path

COMPONENTS = Path(__file__).resolve().parent.parent / "static" / "js" / "components"


def history_table_src():
    return (COMPONENTS / "HistoryTable.js").read_text()


def test_running_rows_render_a_pulsing_dot_before_the_status_text():
    src = history_table_src()
    assert re.search(
        r"e\.status === 'running' \? html`<span class=\"w-1\.5 h-1\.5 rounded-full bg-sky-400 animate-pulse\"></span>`",
        src,
    ), "running rows must render an animate-pulse dot"


def test_pulse_dot_is_skipped_for_terminal_statuses_and_text_is_kept():
    src = history_table_src()
    assert src.count("animate-pulse") == 1, "pulse dot must only be emitted for running rows"
    assert "${e.status}</span>" in src, "status text must still be rendered"


def test_history_table_has_select_all_checkbox_in_header():
    src = history_table_src()
    assert re.search(r'type="checkbox".*onChange=\$\{toggleSelectAll\}', src), \
        "header must contain a select-all checkbox"


def test_history_table_has_per_row_checkbox():
    src = history_table_src()
    assert "toggleSelect(entryKey)" in src, \
        "each row must have a checkbox calling toggleSelect"


def test_history_table_shows_bulk_delete_button_when_items_selected():
    src = history_table_src()
    assert "Delete Selected" in src, \
        "bulk delete button with label 'Delete Selected' must exist"
    assert "setPendingBulkDelete" in src, \
        "bulk delete must set pendingBulkDelete state"


def test_history_table_imports_delete_history_entries():
    src = history_table_src()
    assert "deleteHistoryEntries" in src, \
        "HistoryTable must import deleteHistoryEntries for bulk delete"


def test_history_table_header_is_sticky_while_scrolling():
    src = history_table_src()
    assert 'class="data-table ' in src, "the table must be marked .data-table"
    index_html = (Path(__file__).resolve().parent.parent / "index.html").read_text()
    assert ".data-table thead th" in index_html, "sticky header rule is missing"
    assert re.search(r"\.data-table thead th \{[^}]*position:\s*sticky[^}]*top:\s*0", index_html, re.S), \
        "header cells must stick to the top of the scroll container"
    assert ".dark .data-table thead th" in index_html, \
        "the sticky header needs an opaque dark-mode background too"
