import time

import pytest

import launcher.storage as storage
import launcher.api.runs as runs


@pytest.fixture
def runs_env(store, tmp_path):
    pass_script = tmp_path / "pass.py"
    pass_script.write_text("print('ok')\n")
    echo_script = tmp_path / "echo.py"
    echo_script.write_text("import sys\nprint(' '.join(sys.argv[1:]))\n")
    slow_script = tmp_path / "slow.py"
    slow_script.write_text("import time\nprint('start', flush=True)\ntime.sleep(1.5)\nprint('done')\n")

    store.seed("profiles", [
        {"id": "p1", "name": "Simple", "script_path": str(pass_script), "args": [], "custom_args": []},
        {"id": "p2", "name": "Args", "script_path": str(echo_script), "args": ["static"], "custom_args": [
            {"name": "--flag", "type": "text", "value": "v1"},
            {"name": "--cb", "type": "checkbox", "value": "true"},
            {"name": "--off", "type": "checkbox", "value": "false"},
        ]},
        {"id": "p3", "name": "Ghost", "script_path": str(tmp_path / "nope.py"), "args": [], "custom_args": []},
        {"id": "p4", "name": "Slow", "script_path": str(slow_script), "args": [], "custom_args": []},
        {"id": "p5", "name": "Dates", "script_path": str(echo_script), "args": [], "custom_args": [
            {"name": "--date", "type": "date", "value": "2026-09-07"},
            {"name": "--fmt", "type": "date", "value": "2026-09-07", "format": "%d.%m.%Y"},
        ]},
        {"id": "p6", "name": "Enum", "script_path": str(echo_script), "args": [], "custom_args": [
            {"name": "--level", "type": "enum", "options": "debug,info,warn", "value": "info"},
            {"name": "--unset", "type": "enum", "options": "a,b", "value": ""},
        ]},
    ])
    store.seed("workflows", [
        {"id": "w1", "name": "Chain", "steps": [{"type": "sequential", "profile_id": "p1"}]},
        {"id": "w2", "name": "Long", "steps": [{"type": "sequential", "profile_id": "p4"}]},
    ])
    return {"pass": pass_script, "echo": echo_script, "slow": slow_script}


def wait_done(run_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = runs.handle_poll(run_id)
        if info and info["status"] in ("completed", "failed"):
            return info
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish in time")


def last_history(store):
    return store.read("history")[-1]


def test_polling_unknown_run_ids_returns_nothing(store):
    assert runs.handle_poll("nope") is None
    assert runs.handle_poll_all() == {}


def test_poll_endpoints_expose_output_log_status_and_steps(store):
    runs.active_runs["r1"] = {
        "output": ["a\n"], "workflow_log": ["log"], "status": "completed",
        "returncode": 0, "steps": {"S": {}}, "current_step": "S",
    }
    try:
        polled = runs.handle_poll("r1")
        assert polled == {
            "output": ["a\n"], "workflow_log": ["log"], "status": "completed",
            "returncode": 0, "steps": {"S": {}}, "current_step": "S",
        }
        assert runs.handle_poll_all()["r1"] == polled
    finally:
        runs.active_runs.clear()


def test_run_profile_rejects_unknown_profiles_and_missing_scripts(store, runs_env):
    assert runs.handle_run_profile({"profile_id": "ghost"}, None) == (None, 404, {"error": "Profile not found"})
    body, status, error = runs.handle_run_profile({"profile_id": "p3"}, None)
    assert body is None and status == 400 and "Script not found" in error["error"]


def test_run_profile_executes_the_script_and_saves_history(store, runs_env):
    body, status, error = runs.handle_run_profile({"profile_id": "p1"}, None)
    assert error is None and status == 200 and body["run_id"].startswith("prof_")
    info = wait_done(body["run_id"])
    assert info["status"] == "completed" and info["returncode"] == 0
    assert info["output"] == ["ok\n"]
    entry = last_history(store)
    assert entry["run_id"] == body["run_id"] and entry["type"] == "profile" and entry["status"] == "completed"


def test_run_profile_applies_static_custom_and_overridden_args(store, runs_env):
    data = {"profile_id": "p2", "args": ["extra"], "arg_values": {"--flag": "v2"}}
    body, status, error = runs.handle_run_profile(data, None)
    assert error is None
    info = wait_done(body["run_id"])
    assert info["output"] == ["static --flag v2 --cb extra\n"], info["output"]


def test_run_profile_formats_date_custom_args(store, runs_env):
    body, status, error = runs.handle_run_profile({"profile_id": "p5"}, None)
    assert error is None
    info = wait_done(body["run_id"])
    assert info["output"] == ["--date 2026-09-07 --fmt 07.09.2026\n"], info["output"]


def test_run_profile_formats_overridden_date_values(store, runs_env):
    data = {"profile_id": "p5", "arg_values": {"--date": "2026-01-02"}}
    body, status, error = runs.handle_run_profile(data, None)
    assert error is None
    info = wait_done(body["run_id"])
    assert info["output"] == ["--date 2026-01-02 --fmt 07.09.2026\n"], info["output"]


def test_run_profile_omits_unselected_enum_args(store, runs_env):
    body, status, error = runs.handle_run_profile({"profile_id": "p6"}, None)
    assert error is None
    info = wait_done(body["run_id"])
    assert info["output"] == ["--level info\n"], info["output"]


def test_run_profile_omits_enum_args_cleared_by_override(store, runs_env):
    data = {"profile_id": "p6", "arg_values": {"--level": ""}}
    body, status, error = runs.handle_run_profile(data, None)
    assert error is None
    info = wait_done(body["run_id"])
    assert info["output"] == ["\n"], info["output"]


def test_run_workflow_rejects_unknown_workflow_ids(store, runs_env):
    assert runs.handle_run_workflow({"workflow_id": "ghost"}) == (None, 404, {"error": "Workflow not found"})


def test_run_workflow_executes_steps_and_saves_history(store, runs_env):
    body, status, error = runs.handle_run_workflow({"workflow_id": "w1"})
    assert error is None and status == 200 and body["run_id"].startswith("wf_")
    info = wait_done(body["run_id"])
    assert info["status"] == "completed"
    assert info["steps"]["1. Simple"]["status"] == "completed"
    entry = last_history(store)
    assert entry["run_id"] == body["run_id"] and entry["type"] == "workflow"


def test_run_workflow_is_in_history_while_still_running_and_updates_in_place(store, runs_env):
    body, status, error = runs.handle_run_workflow({"workflow_id": "w2"})
    assert error is None
    rid = body["run_id"]

    # The entry must show up while the workflow is still in progress, so the
    # run survives the run modal being closed.
    deadline = time.time() + 5
    while time.time() < deadline:
        entries = [e for e in store.read("history") if e["run_id"] == rid]
        if entries:
            break
        time.sleep(0.02)
    assert entries, "no history entry was created for the in-progress workflow"
    assert entries[0]["status"] == "running"
    entry_id = entries[0]["id"]

    info = wait_done(rid)
    assert info["status"] == "completed"
    entries = [e for e in store.read("history") if e["run_id"] == rid]
    assert len(entries) == 1, "finishing the run must not append a second history entry"
    assert entries[0]["id"] == entry_id, "the existing entry should be updated, not replaced"
    assert entries[0]["status"] == "completed"
    assert "[DONE] Step 1 (Slow) completed successfully" in entries[0]["output_preview"]
