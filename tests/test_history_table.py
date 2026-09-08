import re
from pathlib import Path

COMPONENTS = Path(__file__).resolve().parent.parent / "static" / "js" / "components"


def history_table_src():
    return (COMPONENTS / "HistoryTable.js").read_text()


def test_running_rows_render_an_animated_spinner_before_the_status_text():
    src = history_table_src()
    assert re.search(
        r"e\.status === 'running' \? html`<svg class=\"w-3 h-3 animate-spin\"",
        src,
    ), "running rows must render an animate-spin spinner"
    assert "<circle" in src and "<path" in src, "spinner svg is incomplete"


def test_spinner_is_skipped_for_terminal_statuses_and_text_is_kept():
    src = history_table_src()
    assert src.count("animate-spin") == 1, "spinner must only be emitted for running rows"
    assert "${e.status}</span>" in src, "status text must still be rendered"
