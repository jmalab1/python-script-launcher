import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import launcher.config as config
import launcher.storage as storage
import launcher.runner as runner
import launcher.api.runs as runs

tmp = Path(tempfile.mkdtemp())
pass_script = tmp / "pass.py"
pass_script.write_text("print('ok')\n")
echo_script = tmp / "echo.py"
echo_script.write_text("import sys\nprint(' '.join(sys.argv[1:]))\n")

(tmp / "profiles.json").write_text(json.dumps([
    {"id": "p1", "name": "Simple", "script_path": str(pass_script), "args": [], "custom_args": []},
    {"id": "p2", "name": "Args", "script_path": str(echo_script), "args": ["static"], "custom_args": [
        {"name": "--flag", "type": "text", "value": "v1"},
        {"name": "--cb", "type": "checkbox", "value": "true"},
        {"name": "--off", "type": "checkbox", "value": "false"},
    ]},
    {"id": "p3", "name": "Ghost", "script_path": str(tmp / "nope.py"), "args": [], "custom_args": []},
]))
(tmp / "workflows.json").write_text(json.dumps([
    {"id": "w1", "name": "Chain", "steps": [{"type": "sequential", "profile_id": "p1"}]},
]))
runs.PROFILES_FILE = tmp / "profiles.json"
runner.PROFILES_FILE = tmp / "profiles.json"
storage.HISTORY_FILE = tmp / "history.json"
config.WORKFLOWS_FILE = tmp / "workflows.json"


def wait_done(run_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = runs.handle_poll(run_id)
        if info and info["status"] in ("completed", "failed"):
            return info
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish in time")


def last_history():
    return storage.load_json(storage.HISTORY_FILE)[-1]


try:
    # 1. polling unknown runs
    assert runs.handle_poll("nope") is None
    assert runs.handle_poll_all() == {}
    print("PASS: polling unknown run ids returns nothing")

    # 2. poll payload shape
    runs.active_runs["r1"] = {
        "output": ["a\n"], "workflow_log": ["log"], "status": "completed",
        "returncode": 0, "steps": {"S": {}}, "current_step": "S",
    }
    polled = runs.handle_poll("r1")
    assert polled == {
        "output": ["a\n"], "workflow_log": ["log"], "status": "completed",
        "returncode": 0, "steps": {"S": {}}, "current_step": "S",
    }
    assert runs.handle_poll_all()["r1"] == polled
    print("PASS: poll endpoints expose output, log, status and steps")

    # 3. run profile rejects unknown profiles and missing scripts
    assert runs.handle_run_profile({"profile_id": "ghost"}, None) == (None, 404, {"error": "Profile not found"})
    body, status, error = runs.handle_run_profile({"profile_id": "p3"}, None)
    assert body is None and status == 400 and "Script not found" in error["error"]
    print("PASS: run profile rejects unknown profiles and missing scripts")

    # 4. run profile executes and records history
    body, status, error = runs.handle_run_profile({"profile_id": "p1"}, None)
    assert error is None and status == 200 and body["run_id"].startswith("prof_")
    info = wait_done(body["run_id"])
    assert info["status"] == "completed" and info["returncode"] == 0
    assert info["output"] == ["ok\n"]
    entry = last_history()
    assert entry["run_id"] == body["run_id"] and entry["type"] == "profile" and entry["status"] == "completed"
    print("PASS: run profile executes the script and saves history")

    # 5. run profile builds static, custom and overridden args
    data = {"profile_id": "p2", "args": ["extra"], "arg_values": {"--flag": "v2"}}
    body, status, error = runs.handle_run_profile(data, None)
    assert error is None
    info = wait_done(body["run_id"])
    assert info["output"] == ["static --flag v2 --cb extra\n"], info["output"]
    print("PASS: run profile applies static, custom and overridden args")

    # 6. run workflow rejects unknown ids
    assert runs.handle_run_workflow({"workflow_id": "ghost"}) == (None, 404, {"error": "Workflow not found"})
    print("PASS: run workflow rejects unknown workflow ids")

    # 7. run workflow executes and records history
    body, status, error = runs.handle_run_workflow({"workflow_id": "w1"})
    assert error is None and status == 200 and body["run_id"].startswith("wf_")
    info = wait_done(body["run_id"])
    assert info["status"] == "completed"
    assert info["steps"]["1. Simple"]["status"] == "completed"
    entry = last_history()
    assert entry["run_id"] == body["run_id"] and entry["type"] == "workflow"
    print("PASS: run workflow executes steps and saves history")
finally:
    runs.active_runs.clear()
    shutil.rmtree(tmp, ignore_errors=True)

print("\nALL TESTS PASSED")
