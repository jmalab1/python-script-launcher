import re
from pathlib import Path

COMPONENTS = Path(__file__).resolve().parent.parent / "static" / "js" / "components"


def run_modal_src():
    return (COMPONENTS / "RunModal.js").read_text()


def test_run_modal_loads_live_runs_by_polling_and_history_runs_by_fetching():
    src = run_modal_src()
    assert "import { pollRun, fetchHistoryRun } from '../api.js';" in src, \
        "RunModal does not import its data loaders"
    assert "pollActiveRun(runId);" in src, "live runs are not polled"
    assert "loadFromHistory(runId, runType);" in src, "history runs are not loaded"


def test_run_modal_switches_to_live_polling_for_history_entries_still_running():
    src = run_modal_src()
    assert re.search(
        r"hist\.status === 'running' \|\| hist\.status === 'starting'",
        src,
    ), "loadFromHistory does not detect in-progress entries"
    assert re.search(
        r"if \(\(hist\.status === 'running' \|\| hist\.status === 'starting'\) && !autoPolledRef\.current\) \{\s*"
        r"autoPolledRef\.current = true;\s*"
        r"pollActiveRun\(rid\);",
        src,
    ), "a still-running history entry must start polling exactly once (guard against poll/error loops)"


def test_run_modal_resets_its_poll_guard_each_time_it_opens():
    src = run_modal_src()
    assert re.search(
        r"if \(!isOpen \|\| !runId\) return;\s*"
        r"lastDataRef\.current = null;\s*"
        r"autoPolledRef\.current = false;",
        src,
    ), "the one-shot poll guard must reset whenever the modal reopens"


def test_run_modal_stops_polling_when_the_run_finishes_or_the_modal_closes():
    src = run_modal_src()
    assert re.search(
        r"if \(data\.status === 'completed' \|\| data\.status === 'failed'\) \{\s*"
        r"clearInterval\(timerRef\.current\);",
        src,
    ), "polling must stop once the run reaches a terminal status"
    assert re.search(
        r"return \(\) => \{\s*"
        r"if \(timerRef\.current\) \{ clearInterval\(timerRef\.current\); timerRef\.current = null; \}\s*"
        r"\};",
        src,
    ), "closing the modal must not leave the poll timer running"
