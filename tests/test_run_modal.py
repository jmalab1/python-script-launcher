import re
from pathlib import Path

COMPONENTS = Path(__file__).resolve().parent.parent / "static" / "js" / "components"


def run_modal_src():
    return (COMPONENTS / "RunModal.js").read_text()


def test_run_modal_loads_live_runs_by_polling_and_history_runs_by_fetching():
    src = run_modal_src()
    assert "import { pollRun, fetchHistoryRun, cancelRun } from '../api.js';" in src, \
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
        r"liveRunIdRef\.current = hist\.run_id \|\| rid;",
        src,
    ), "the history entry must reveal the runner's run id — the entry id alone cannot be polled"
    assert re.search(
        r"if \(\(hist\.status === 'running' \|\| hist\.status === 'starting'\) && !autoPolledRef\.current\) \{\s*"
        r"autoPolledRef\.current = true;\s*"
        r"pollActiveRun\(liveRunIdRef\.current\);",
        src,
    ), "a still-running history entry must be polled by its run id (the runner's key), exactly once (guard against poll/error loops)"


def test_run_modal_does_not_reload_history_over_live_data_while_polling():
    src = run_modal_src()
    assert re.search(
        r"if \(runType && !timerRef\.current\) \{\s*"
        r"loadFromHistory\(runId, runType\);\s*"
        r"\}",
        src,
    ), "switching tabs must not clobber live polled output with the stale history snapshot"


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
        r"if \(data\.status === 'completed' \|\| data\.status === 'failed' \|\| data\.status === 'cancelled'\) \{\s*"
        r"clearInterval\(timerRef\.current\);",
        src,
    ), "polling must stop once the run reaches a terminal status, including cancelled"
    assert re.search(
        r"return \(\) => \{\s*"
        r"if \(timerRef\.current\) \{ clearInterval\(timerRef\.current\); timerRef\.current = null; \}\s*"
        r"openRef\.current = false;\s*"
        r"\};",
        src,
    ), "closing the modal must mark it closed and clear the poll timer"


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


# ------------------------------------------------------------- right-side panel


def test_run_modal_renders_as_a_right_side_panel():
    src = run_modal_src()
    assert "fixed inset-0 z-50" in src, \
        "the panel must sit above the page while it is open"
    assert "absolute right-0 top-0 h-full" in src, \
        "the run output must dock to the right edge as a full-height panel"
    assert "bg-black/60 backdrop-blur-sm" not in src, \
        "the panel replaces the centered dark-backdrop modal"


def test_clicking_outside_the_run_panel_closes_it():
    src = run_modal_src()
    assert "fixed inset-0 z-50 pointer-events-none" in src, \
        "outside clicks must reach the page, so the overlay must be click-through"
    assert "pointer-events-auto" in src, \
        "only the panel itself must capture pointer events"
    assert re.search(
        r"document\.addEventListener\('click', onOutsideClick, true\);",
        src,
    ), "the panel must listen for outside clicks in the capture phase"
    assert re.search(
        r"if \(panelRef\.current && !panelRef\.current\.contains\(e\.target\)\) \{\s*"
        r"onCloseRef\.current\(\);",
        src,
    ), "only clicks outside the panel must close it"
    assert re.search(
        r"document\.removeEventListener\('click', onOutsideClick, true\);",
        src,
    ), "the outside-click listener must be removed when the panel closes"
    assert 'class="absolute inset-0" onClick=${onClose}' not in src, \
        "no blocking click-away layer should swallow page clicks"


def test_run_panel_slides_in_and_out():
    src = run_modal_src()
    html_src = (Path(__file__).resolve().parent.parent / "index.html").read_text()
    assert html_src.count("translateX(100%)") == 2, \
        "the style sheet must define slide-in and slide-out keyframes"
    assert ".run-panel-in {" in html_src and ".run-panel-out {" in html_src, \
        "the keyframes must be applied through .run-panel-in/.run-panel-out rules"
    assert "isOpen ? 'run-panel-in' : 'run-panel-out'" in src, \
        "the panel must switch between the in and out animation classes"
    assert "if (!visible) return null;" in src, \
        "the panel must stay rendered until its slide-out animation finishes"
    assert re.search(
        r"onAnimationEnd=\$\{\(e\) => \{ if \(e\.target === e\.currentTarget && !isOpen\) setVisible\(false\); \}\}",
        src,
    ), "the slide-out animation must report done by unmounting the panel, but only when closing — the slide-in's own animationend must not close it"


def test_run_panel_shows_a_grip_indicator_on_its_left_edge():
    src = run_modal_src()
    assert "cursor-col-resize" in src, \
        "the left edge must show the column-resize cursor"
    assert "-left-1.5" in src, \
        "the grip handle must hang off the panel's left edge"
    assert "rounded-full" in src, \
        "the handle must carry a grip pill that hints it can be dragged"
    assert src.count('h-1 w-0.5 rounded-full bg-current') == 3, \
        "the grip pill must show three dots like other resize handles"
    assert "my-auto" in src, \
        "the grip pill must be vertically centered on the panel edge"


def test_run_panel_opens_wider_than_the_old_modal_default():
    src = run_modal_src()
    assert re.search(r"\|\| (\d+)\)", src), "the panel width has no numeric default"
    default_width = int(re.search(r"\|\| (\d+)\)", src).group(1))
    assert default_width >= 720, \
        f"the default width ({default_width}px) should be a bit wider than before"


def test_run_panel_width_is_resizable_and_persisted():
    src = run_modal_src()
    assert "localStorage.getItem('runPanelWidth')" in src, \
        "the panel must remember its width across page reloads"
    assert "function startResize(ev)" in src, "the panel has no drag-to-resize handler"
    assert "onPointerDown=${startResize}" in src, \
        "the resize handle must be wired to the pointer-down event"
    assert "cursor-col-resize" in src, \
        "the left edge must show the column-resize cursor"
    assert "window.addEventListener('pointermove', onMove);" in src \
        and "window.addEventListener('pointerup', onUp);" in src, \
        "dragging must track the pointer so it keeps working outside the handle"
    assert "window.removeEventListener('pointermove', onMove);" in src \
        and "window.removeEventListener('pointerup', onUp);" in src, \
        "the drag listeners must be removed when the drag ends"
    assert "localStorage.setItem('runPanelWidth', String(finalWidth));" in src, \
        "the final width must be saved for the next open"
    assert "Math.max(px, min)" in src, "the panel must never shrink below the minimum width"
    assert "window.innerWidth - 60" in src, \
        "the panel must never grow wider than the window minus a small gutter"
    assert "style=${{ width: width + 'px'," in src, \
        "the measured width must drive the panel's rendered size"


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


def test_poll_timer_cannot_outlive_a_closed_modal():
    """Closing the modal while the first history fetch was still in flight
    used to start the interval after cleanup, polling orphaned forever."""
    src = run_modal_src()
    assert "openRef.current = true;" in src, "opening must mark the modal open"
    assert "openRef.current = false;" in src, "cleanup must mark the modal closed"
    assert re.search(
        r"async function pollActiveRun\(rid\)\s*\{\s*if \(!openRef\.current\) return;",
        src,
    ), "a poll started after close must be refused"
    assert re.search(
        r"setInterval\(async \(\) => \{\s*"
        r"if \(!openRef\.current\) \{\s*"
        r"clearInterval\(timerRef\.current\);",
        src,
    ), "ticks that arrive after close must tear the timer down"
