import time
from pathlib import Path

import pytest

import launcher.api.runs as runs
import launcher.runner as runner
from launcher.runner import parse_timeout, run_script

COMPONENTS = Path(__file__).resolve().parent.parent / "static" / "js" / "components"


# ----------------------------------------------------------------- parse_timeout


def test_parse_timeout_accepts_numbers_and_numeric_strings():
    assert parse_timeout(30) == 30.0
    assert parse_timeout("30") == 30.0
    assert parse_timeout("2.5") == 2.5


def test_parse_timeout_missing_or_invalid_means_no_limit():
    assert parse_timeout(None) is None
    assert parse_timeout("") is None
    assert parse_timeout("abc") is None
    assert parse_timeout(0) is None
    assert parse_timeout(-1) is None


# ------------------------------------------------------------------- run_script


@pytest.fixture
def hang_script(tmp_path):
    script = tmp_path / "hang.py"
    script.write_text("import time\nprint('start', flush=True)\ntime.sleep(30)\n")
    return script


def test_run_script_kills_the_process_after_the_timeout(new_run, hang_script):
    run_id = new_run("r1")
    started = time.time()
    lines = list(run_script(str(hang_script), [], run_id, timeout=0.5))
    elapsed = time.time() - started

    assert any("Timed out after 0.5s and was killed" in line for line in lines)
    entry = runner.active_runs[run_id]
    assert entry["returncode"] != 0, "a killed script must count as a failure"
    assert entry["timed_out"] is True, "the run-level flag lets poll/history report the timeout"
    assert elapsed < 10, "the 30s sleep must not be waited out"


def test_run_script_ignores_a_timeout_passed_as_a_string(new_run, hang_script):
    run_id = new_run("r1")
    lines = list(run_script(str(hang_script), [], run_id, timeout="0.5"))
    assert any("Timed out after 0.5s" in line for line in lines)


def test_run_script_still_completes_normally_below_the_timeout(new_run, tmp_path):
    ok_script = tmp_path / "ok.py"
    ok_script.write_text("print('ok')\n")
    run_id = new_run("r1")
    lines = list(run_script(str(ok_script), [], run_id, timeout=10))
    assert lines == ["ok\n"]
    assert runner.active_runs[run_id]["returncode"] == 0
    assert runner.active_runs[run_id]["status"] == "running", \
        "run_script finishes the process but leaves the status to the caller"


# ------------------------------------------------------------------ API layer


def wait_done(run_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = runs.handle_poll(run_id)
        if info and info["status"] in ("completed", "failed"):
            return info
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish in time")


def test_profile_run_times_out_and_is_marked_failed(store, hang_script):
    store.seed("profiles", [
        {"id": "p1", "name": "Hang", "script_path": str(hang_script),
         "args": [], "custom_args": [], "timeout": 0.5},
    ])
    body, status, error = runs.handle_run_profile({"profile_id": "p1"})
    assert error is None and status == 200

    info = wait_done(body["run_id"])
    assert info["status"] == "failed"
    assert info["timed_out"] is True, "poll must tell the client the run hit its timeout"
    assert any("Timed out after 0.5s" in line for line in info["output"]), info["output"]

    # save_history runs right after the status flips, so poll for the entry.
    deadline = time.time() + 5
    entries = []
    while time.time() < deadline:
        entries = [e for e in store.read("history") if e["run_id"] == body["run_id"]]
        if entries:
            break
        time.sleep(0.05)
    entry = entries[0]
    assert entry["status"] == "failed"
    assert entry["timed_out"] is True, "history must record the timeout"


def test_profile_without_timeout_setting_runs_without_a_limit(store, hang_script, monkeypatch):
    # A profile with no timeout must still run (no watchdog, no early kill).
    store.seed("profiles", [
        {"id": "p1", "name": "Hang", "script_path": str(hang_script),
         "args": [], "custom_args": []},
    ])
    body, status, error = runs.handle_run_profile({"profile_id": "p1"})
    assert error is None
    with pytest.raises(AssertionError):
        wait_done(body["run_id"], timeout=1)
    assert runs.handle_poll(body["run_id"])["output"] == ["start\n"], \
        "the script is still running, not killed"


def test_workflow_step_times_out_and_fails_the_workflow(store, hang_script):
    store.seed("profiles", [
        {"id": "p1", "name": "Hang", "script_path": str(hang_script),
         "args": [], "custom_args": [], "timeout": 0.5},
    ])
    store.seed("workflows", [
        {"id": "w1", "name": "Bad", "steps": [{"type": "sequential", "profile_id": "p1"}]},
    ])
    body, _, _ = runs.handle_run_workflow({"workflow_id": "w1"})

    info = wait_done(body["run_id"])
    assert info["status"] == "failed"
    assert info["timed_out"] is True, "a timed-out step must flag the whole run"
    step = info["steps"]["1. Hang"]
    assert step["status"] == "failed"
    assert any("Timed out after 0.5s" in line for line in step["output"]), step["output"]

    deadline = time.time() + 5
    entries = []
    while time.time() < deadline:
        entries = [e for e in store.read("history") if e["run_id"] == body["run_id"]]
        if entries:
            break
        time.sleep(0.05)
    assert entries[0]["timed_out"] is True, "history must record the workflow timeout"


# --------------------------------------------------------------- Profile modal

def test_profile_modal_offers_a_timeout_field():
    src = (COMPONENTS / "ProfileModal.js").read_text()
    assert "Timeout (seconds)" in src, "the timeout input label is missing"
    assert "onInput=${e => setTimeout(e.target.value)}" in src, \
        "the timeout input is not wired to state"
    assert (
        "profile.timeout === undefined || profile.timeout === null ? '' : String(profile.timeout)"
        in src
    ), "an existing profile's timeout must load into the input"
    assert "positive number of seconds" in src, \
        "non-positive or junk timeouts must be rejected with an inline error"
    assert "profileData.timeout = parsedTimeout" in src, \
        "a valid timeout must be saved on the profile"
    assert 'placeholder="No limit"' in src, \
        "an empty timeout means no limit and should say so"


def test_profile_modal_clearing_the_timeout_saves_no_timeout_value():
    src = (COMPONENTS / "ProfileModal.js").read_text()
    assert "if (parsedTimeout !== null) profileData.timeout = parsedTimeout;" in src, \
        "a blank timeout must be omitted rather than saved as 0 or ''"
