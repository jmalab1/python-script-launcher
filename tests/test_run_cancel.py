import re
import time
from pathlib import Path

import pytest

import launcher.api.runs as runs
import launcher.runner as runner
from launcher.runner import cancel_run, run_script

COMPONENTS = Path(__file__).resolve().parent.parent / "static" / "js" / "components"


@pytest.fixture
def hang_script(tmp_path):
    script = tmp_path / "hang.py"
    script.write_text("import time\nprint('start', flush=True)\ntime.sleep(30)\n")
    return script


@pytest.fixture(autouse=True)
def clean_active_runs():
    """Runs started here would leak into later tests that expect a clean poll."""
    runner.active_runs.clear()
    yield
    runner.active_runs.clear()


@pytest.fixture
def quick_script(tmp_path):
    script = tmp_path / "quick.py"
    script.write_text("print('done quick')\n")
    return script


def wait_terminal(run_id, timeout=10):
    """Poll until the run reaches any final status, and return the poll data."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = runs.handle_poll(run_id)
        if info and info["status"] in ("completed", "failed", "cancelled"):
            return info
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish in time")


def wait_for_output(run_id, needle, timeout=10):
    """Poll until the run's output contains `needle` somewhere."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = runs.handle_poll(run_id)
        if info and any(needle in line for line in info["output"]):
            return info
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} never printed {needle!r}")


def wait_for_history(store, run_id, timeout=5):
    """The history entry is written right after the run finishes."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        entries = [e for e in store.read("history") if e["run_id"] == run_id]
        if entries:
            return entries[0]
        time.sleep(0.05)
    raise AssertionError(f"no history entry appeared for {run_id}")


# ----------------------------------------------------------------- cancel_run


def test_cancel_run_refuses_unknown_and_finished_runs(new_run):
    assert cancel_run("nope") is False, "there is nothing to cancel for an unknown run"

    run_id = new_run("r1")
    runner.active_runs[run_id]["status"] = "completed"
    assert cancel_run(run_id) is False, "a finished run cannot be cancelled"

    runner.active_runs[run_id]["status"] = "failed"
    assert cancel_run(run_id) is False


def test_a_cancel_that_arrives_before_the_script_starts_still_kills_it(new_run, hang_script):
    # Covers the race where cancel is requested between the run being
    # registered and the script process being handed to the runner.
    run_id = new_run("r1")
    assert cancel_run(run_id) is True

    started = time.time()
    list(run_script(str(hang_script), [], run_id))
    elapsed = time.time() - started

    assert elapsed < 10, "the script must be killed, not slept out"
    assert runner.active_runs[run_id]["returncode"] != 0


# -------------------------------------------------------------- API behaviour


def test_cancelling_a_profile_run_records_it_as_cancelled(store, hang_script):
    store.seed("profiles", [
        {"id": "p1", "name": "Hang", "script_path": str(hang_script),
         "args": [], "custom_args": []},
    ])
    body, status, error = runs.handle_run_profile({"profile_id": "p1"})
    assert error is None and status == 200
    run_id = body["run_id"]

    wait_for_output(run_id, "start")
    result, status, error = runs.handle_cancel_run(run_id)
    assert error is None and status == 200 and result == {"ok": True}

    info = wait_terminal(run_id)
    assert info["status"] == "cancelled", "a stopped run is cancelled, not failed"
    assert info["cancelled"] is True, "poll must tell the client the run was cancelled"
    assert any("Cancelled by user" in line for line in info["output"]), info["output"]

    entry = wait_for_history(store, run_id)
    assert entry["status"] == "cancelled", "history must record the cancellation"


def test_cancelling_a_workflow_run_stops_before_remaining_steps(store, hang_script, quick_script):
    store.seed("profiles", [
        {"id": "p1", "name": "Hang", "script_path": str(hang_script),
         "args": [], "custom_args": []},
        {"id": "p2", "name": "Quick", "script_path": str(quick_script),
         "args": [], "custom_args": []},
    ])
    store.seed("workflows", [
        {"id": "w1", "name": "Chain", "steps": [
            {"type": "sequential", "profile_id": "p1"},
            {"type": "sequential", "profile_id": "p2"},
        ]},
    ])
    body, _, _ = runs.handle_run_workflow({"workflow_id": "w1"})
    run_id = body["run_id"]

    wait_for_output(run_id, "start")
    _, status, error = runs.handle_cancel_run(run_id)
    assert error is None and status == 200

    info = wait_terminal(run_id)
    assert info["status"] == "cancelled"
    assert "2. Quick" not in info["steps"], "remaining steps must not run"
    assert info["steps"]["1. Hang"]["status"] == "cancelled", \
        "the step killed mid-run is cancelled, not failed"
    assert any("[CANCEL]" in line for line in info["workflow_log"]), info["workflow_log"]

    entry = wait_for_history(store, run_id)
    assert entry["status"] == "cancelled"


def test_cancel_api_rejects_unknown_and_finished_runs(store, tmp_path):
    result, status, error = runs.handle_cancel_run("missing_run")
    assert status == 404 and error, "an unknown run cannot be cancelled"

    quick = tmp_path / "quick.py"
    quick.write_text("print('done')\n")
    store.seed("profiles", [
        {"id": "p1", "name": "Quick", "script_path": str(quick),
         "args": [], "custom_args": []},
    ])
    body, _, _ = runs.handle_run_profile({"profile_id": "p1"})
    info = wait_terminal(body["run_id"])
    assert info["status"] == "completed"

    result, status, error = runs.handle_cancel_run(body["run_id"])
    assert status == 404 and error, "a finished run cannot be cancelled"


def test_cancelled_runs_show_up_in_the_status_filter(store, hang_script):
    store.seed("profiles", [
        {"id": "p1", "name": "Hang", "script_path": str(hang_script),
         "args": [], "custom_args": []},
    ])
    body, _, _ = runs.handle_run_profile({"profile_id": "p1"})
    wait_for_output(body["run_id"], "start")
    runs.handle_cancel_run(body["run_id"])
    wait_terminal(body["run_id"])
    wait_for_history(store, body["run_id"])

    from launcher.api.history import handle_list
    page = handle_list(1, 15, "profile", status="cancelled")
    assert page["total"] == 1, "the history filter must offer cancelled runs"
    assert page["entries"][0]["status"] == "cancelled"


# ------------------------------------------------------------------ UI wiring


def run_modal_src():
    return (COMPONENTS / "RunModal.js").read_text()


def test_run_modal_has_a_stop_button_that_confirms_before_cancelling():
    src = run_modal_src()
    assert "import { pollRun, fetchHistoryRun, cancelRun } from '../api.js';" in src, \
        "RunModal does not import the cancel API"
    assert "const [pendingCancel, setPendingCancel] = useState(false);" in src, \
        "the confirm dialog must be driven by modal state"
    assert re.search(
        r"\$\{\(status === 'running' \|\| status === 'starting'\) \? html`[\s\S]*?setPendingCancel\(true\)[\s\S]*?>\s*Stop\s*<",
        src,
    ), "a Stop button must be offered only while the run is still in progress"
    assert re.search(
        r"<\$\{ConfirmModal\} isOpen=\$\{pendingCancel\}[\s\S]*?onConfirm=\$\{confirmCancel\}[\s\S]*?confirmLabel=\"Stop\"",
        src,
    ), "stopping must ask for confirmation, like other destructive actions"
    assert "await cancelRun(runId);" in src, "confirming must call the cancel API"


def test_run_modal_shows_cancelled_runs_as_cancelled():
    src = run_modal_src()
    assert "cancelled: 'Cancelled'" in src, "the status badge must label cancelled runs"
    assert "cancelled: 'bg-amber-400'" in src, \
        "cancelled runs get amber, distinct from failed (red) and completed (green)"
    assert "t.status === 'cancelled' ? 'bg-amber-400'" in src, \
        "a step killed mid-run must be visible as cancelled on its tab"


def test_api_layer_exposes_the_cancel_endpoint():
    src = (Path(__file__).resolve().parent.parent / "static" / "js" / "api.js").read_text()
    assert "export async function cancelRun(runId)" in src, \
        "api.js must export the cancel helper"
    assert "'/api/runs/' + runId + '/cancel'" in src, \
        "the cancel request must target the run cancel endpoint"


def test_cancelled_status_is_filterable_and_colorized():
    filters_src = (COMPONENTS / "ListFilters.js").read_text()
    assert '<option value="cancelled">Cancelled</option>' in filters_src, \
        "the history status filter must include cancelled"

    utils_src = (Path(__file__).resolve().parent.parent / "static" / "js" / "utils.js").read_text()
    assert "status === 'cancelled'" in utils_src, \
        "history rows must color cancelled statuses distinctly"
    assert "line.startsWith('[CANCEL')" in utils_src, \
        "workflow log cancel lines must be highlighted in the output viewer"


def test_confirm_modal_lets_callers_rename_the_busy_label():
    src = (COMPONENTS / "ConfirmModal.js").read_text()
    assert "busyLabel = 'Deleting...'" in src, \
        "the busy label must stay backwards compatible for delete confirmations"
    assert "${busy ? busyLabel : confirmLabel}" in src, \
        "the confirm button must show the caller's busy label while working"
