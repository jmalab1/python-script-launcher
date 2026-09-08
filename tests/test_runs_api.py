import json
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

    (tmp_path / "profiles.json").write_text(json.dumps([
        {"id": "p1", "name": "Simple", "script_path": str(pass_script), "args": [], "custom_args": []},
        {"id": "p2", "name": "Args", "script_path": str(echo_script), "args": ["static"], "custom_args": [
            {"name": "--flag", "type": "text", "value": "v1"},
            {"name": "--cb", "type": "checkbox", "value": "true"},
            {"name": "--off", "type": "checkbox", "value": "false"},
        ]},
        {"id": "p3", "name": "Ghost", "script_path": str(tmp_path / "nope.py"), "args": [], "custom_args": []},
    ]))
    (tmp_path / "workflows.json").write_text(json.dumps([
        {"id": "w1", "name": "Chain", "steps": [{"type": "sequential", "profile_id": "p1"}]},
    ]))
    return {"pass": pass_script, "echo": echo_script}


def wait_done(run_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = runs.handle_poll(run_id)
        if info and info["status"] in ("completed", "failed"):
            return info
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish in time")


def last_history(store):
    return storage.load_json(store["history"])[-1]


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
