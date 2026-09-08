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


def test_run_modal_shows_the_command_that_ran():
    src = run_modal_src()
    assert "function commandFor(data)" in src, "the command lookup helper is missing"
    assert re.search(
        r"if \(tab !== 'workflow' && stepData\[tab\]\?\.command\) \{",
        src,
    ), "workflow steps must use their own recorded command"
    assert "return data.command || null;" in src, "profile runs must fall back to the entry-level command"
    assert "Command: " in src and "command.join(' ')" in src, \
        "the command must be rendered above the output as a single joined string"


def test_run_modal_updates_the_command_on_load_poll_and_tab_switch():
    src = run_modal_src()
    assert re.search(
        r"setOutput\(linesFor\(hist\)\);\s*"
        r"setCommand\(commandFor\(hist\)\);",
        src,
    ), "the command must load with history entries"
    assert re.search(
        r"setOutput\(linesFor\(data\)\);\s*"
        r"setCommand\(commandFor\(data\)\);",
        src,
    ), "the command must refresh while polling a live run"
    assert re.search(
        r"if \(data\) \{\s*"
        r"setOutput\(linesFor\(data\)\);\s*"
        r"setCommand\(commandFor\(data\)\);\s*"
        r"\}",
        src,
    ), "switching tabs must swap the command to the selected step"
    assert "setCommand(null);" in src, "the command must reset when the modal reopens"


# ------------------------------------------------------------------ output export


def test_run_modal_exports_the_run_as_a_text_file():
    src = run_modal_src()
    assert "function exportOutput()" in src, "the export helper is missing"
    assert "new Blob(" in src and "text/plain" in src, \
        "the output must be exported as a plain-text blob"
    assert "a.download =" in src, "the download must go through an anchor element"
    assert "URL.revokeObjectURL(url);" in src, "the object URL must be released"
    assert "onClick=${exportOutput}" in src, "the footer must have a wired Export button"
    assert re.search(
        r"onClick=\$\{exportOutput\}[\s\S]*?>\s*Export\s*<",
        src,
    ), "the export button must be labeled Export"


def test_run_modal_export_refuses_an_empty_output_and_names_the_file():
    src = run_modal_src()
    assert "No output to export." in src, \
        "exporting an empty run must tell the user instead of downloading nothing"
    assert "a.download = `${slug(title)}-${stamp}.txt`;" in src, \
        "the filename must combine the run title and a timestamp"


def test_run_modal_export_combines_workflow_logs_and_steps_into_one_document():
    src = run_modal_src()
    assert "const data = lastDataRef.current;" in src, \
        "the export must build from the loaded run data, not the displayed tab"
    assert "'Workflow log\\n------------\\n'" in src, \
        "workflow exports start with the progress log section"
    assert "for (const [name, step] of Object.entries(steps)) {" in src, \
        "every step must get its own section"
    assert re.search(
        r"parts\.push\(`\\n\$\{name\}\\n\$\{'-'\.repeat[^`]*\}\\n`\);",
        src,
    ), "step sections carry the step name as an underlined header"
    assert "`Command: ${[].concat(step.command).join(' ')}\\n`" in src, \
        "each step section records the command that ran"
    assert re.search(
        r"else \{[\s\S]*?parts\.push\(\.\.\.\(data\.output \|\| \[\]\)\);\s*\}",
        src,
    ), "profile runs export their plain output without step sections"


# --------------------------------------------------------------- timed-out badge


def test_run_modal_shows_a_badged_notice_when_the_run_timed_out():
    src = run_modal_src()
    assert "const [timedOut, setTimedOut] = useState(false);" in src, \
        "the modal must track whether the run hit its timeout"
    assert "setTimedOut(!!hist.timed_out);" in src, \
        "a history-loaded run must show the timeout notice"
    assert "setTimedOut(!!data.timed_out);" in src, \
        "a polled live run must show the timeout notice"
    assert "setTimedOut(false);" in src, \
        "the notice must reset when the modal reopens"
    assert re.search(
        r"\$\{timedOut \? html`[\s\S]*?<span>Timed out</span>",
        src,
    ), "a 'Timed out' badge must render next to the status badge"
