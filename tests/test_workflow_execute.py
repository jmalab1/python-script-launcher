import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import launcher.storage as storage
import launcher.runner as runner

tmp = Path(tempfile.mkdtemp())
pass_script = tmp / "pass.py"
pass_script.write_text("print('ok')\n")
fail_script = tmp / "fail.py"
fail_script.write_text("print('bad')\nimport sys\nsys.exit(3)\n")
echo_script = tmp / "echo.py"
echo_script.write_text("import sys\nprint(' '.join(sys.argv[1:]))\n")

(tmp / "profiles.json").write_text(json.dumps([
    {"id": "p_pass", "name": "Pass", "script_path": str(pass_script), "args": [], "custom_args": []},
    {"id": "p_fail", "name": "Fail", "script_path": str(fail_script), "args": [], "custom_args": []},
    {"id": "p_echo", "name": "Echo", "script_path": str(echo_script), "args": ["static"], "custom_args": [
        {"name": "--flag", "type": "text", "value": "v1"},
        {"name": "--cb", "type": "checkbox", "value": "true"},
        {"name": "--off", "type": "checkbox", "value": "false"},
    ]},
]))
runner.PROFILES_FILE = tmp / "profiles.json"
storage.HISTORY_FILE = tmp / "history.json"


def new_run(run_id):
    runner.active_runs[run_id] = {
        "output": [], "workflow_log": [], "status": "running", "returncode": None, "failed": False,
    }
    return run_id


def last_history():
    return storage.load_json(storage.HISTORY_FILE)[-1]


try:
    # 1. _next_step_name numbers steps per run
    rid = new_run("wf_dn")
    named = [runner._next_step_name(rid, "Step") for _ in range(3)]
    assert named == [(1, "1. Step"), (2, "2. Step"), (3, "3. Step")], named
    print("PASS: _next_step_name numbers steps per run")

    # 2. run_script streams output and records the exit code
    rid = new_run("wf_rs")
    result = {}
    lines = list(runner.run_script(str(pass_script), [], rid, result=result))
    assert lines == ["ok\n"], lines
    assert result["returncode"] == 0
    assert runner.active_runs[rid]["returncode"] == 0
    print("PASS: run_script streams lines and captures the exit code")

    # 3. run_script reports failing scripts
    rid = new_run("wf_rs2")
    result = {}
    list(runner.run_script(str(fail_script), [], rid, result=result))
    assert result["returncode"] == 3
    print("PASS: run_script reports failing exit codes")

    # 4. run_script catches spawn errors
    orig_popen = runner.subprocess.Popen
    runner.subprocess.Popen = lambda *a, **k: (_ for _ in ()).throw(OSError("spawn failed"))
    try:
        rid = new_run("wf_rs3")
        result = {}
        assert list(runner.run_script("x.py", [], rid, result=result)) == []
        assert result["returncode"] == -1
        assert any("ERROR:" in line for line in runner.active_runs[rid]["output"])
    finally:
        runner.subprocess.Popen = orig_popen
    print("PASS: run_script turns spawn errors into ERROR output")

    # 5. workflow stops at the first failing step by default
    rid = new_run("wf_abort")
    workflow = {"name": "Abort", "continue_on_error": False, "steps": [
        {"type": "sequential", "profile_id": "p_pass"},
        {"type": "sequential", "profile_id": "p_fail"},
        {"type": "sequential", "profile_id": "p_pass"},
    ]}
    runner.execute_workflow(workflow, rid, time.time())
    run = runner.active_runs[rid]
    assert run["status"] == "failed"
    assert list(run["steps"].keys()) == ["1. Pass", "2. Fail"], list(run["steps"].keys())
    assert [s["step"] for s in run["steps"].values()] == [1, 2]
    assert any("[ABORT]" in line for line in run["workflow_log"])
    saved = last_history()
    assert saved["type"] == "workflow" and saved["status"] == "failed"
    assert list(saved["steps"].keys()) == ["1. Pass", "2. Fail"]
    print("PASS: workflow stops at first failing step by default")

    # 6. continue_on_error keeps going after a failure
    rid = new_run("wf_cont")
    workflow["continue_on_error"] = True
    runner.execute_workflow(workflow, rid, time.time())
    run = runner.active_runs[rid]
    assert run["status"] == "failed"
    assert list(run["steps"].keys()) == ["1. Pass", "2. Fail", "3. Pass"], list(run["steps"].keys())
    assert run["steps"]["3. Pass"]["status"] == "completed"
    print("PASS: continue_on_error runs steps after a failure")

    # 7. missing profile aborts by default, is skipped with continue_on_error
    rid = new_run("wf_miss_abort")
    runner.execute_workflow({"name": "M", "steps": [
        {"type": "sequential", "profile_id": "ghost"},
        {"type": "sequential", "profile_id": "p_pass"},
    ]}, rid, time.time())
    run = runner.active_runs[rid]
    assert run["status"] == "failed"
    assert any("[SKIP]" in line for line in run["workflow_log"])
    assert "steps" not in run
    rid = new_run("wf_miss_skip")
    runner.execute_workflow({"name": "M2", "continue_on_error": True, "steps": [
        {"type": "sequential", "profile_id": "ghost"},
        {"type": "sequential", "profile_id": "p_pass"},
    ]}, rid, time.time())
    run = runner.active_runs[rid]
    assert run["status"] == "completed"
    assert "1. Pass" in run["steps"]
    print("PASS: missing profiles abort by default, are skipped with continue_on_error")

    # 8. parallel groups run all profiles with per-step args
    rid = new_run("wf_par")
    runner.execute_workflow({"name": "P", "steps": [
        {"type": "parallel", "profiles": []},
        {"type": "parallel", "profiles": [
            {"profile_id": "p_pass"},
            {"profile_id": "p_echo", "args": ["extra"], "arg_values": {"--flag": "v2"}},
        ]},
    ]}, rid, time.time())
    run = runner.active_runs[rid]
    assert run["status"] == "completed"
    echo = next(s for k, s in run["steps"].items() if k.endswith("Echo"))
    passed = next(s for k, s in run["steps"].items() if k.endswith("Pass"))
    assert echo["output"] == ["--flag v2 --cb extra\n"], echo["output"]
    assert passed["status"] == "completed"
    assert sorted(k.split(". ")[1] for k in run["steps"]) == ["Echo", "Pass"]
    print("PASS: parallel groups run all profiles with per-step args")

    # 9. missing profile in a parallel group aborts the workflow
    rid = new_run("wf_par_miss")
    runner.execute_workflow({"name": "PM", "steps": [
        {"type": "parallel", "profiles": [{"profile_id": "ghost"}, {"profile_id": "p_pass"}]},
    ]}, rid, time.time())
    run = runner.active_runs[rid]
    assert run["status"] == "failed"
    assert any("[SKIP]" in line for line in run["workflow_log"])
    assert run.get("steps", {}) == {}
    print("PASS: missing profile in a parallel group aborts the workflow")

    # 10. steps run from their embedded profile snapshot, ignoring live profile edits
    rid = new_run("wf_snap")
    runner.execute_workflow({"name": "Snap", "steps": [
        {"type": "sequential", "profile_id": "p_gone",
         "profile": {"id": "p_gone", "name": "Snapshot", "script_path": str(echo_script), "args": [],
                     "custom_args": [{"name": "--flag", "type": "text", "value": "snap"}]}},
    ]}, rid, time.time())
    run = runner.active_runs[rid]
    assert run["status"] == "completed", run["workflow_log"]
    assert "1. Snapshot" in run["steps"]
    assert run["steps"]["1. Snapshot"]["output"] == ["--flag snap\n"], run["steps"]["1. Snapshot"]["output"]
    print("PASS: embedded profile snapshot is used at run time")

    # 11. arg_values still override snapshots; parallel groups use snapshot names
    rid = new_run("wf_snap2")
    runner.execute_workflow({"name": "Snap2", "steps": [
        {"type": "sequential", "profile_id": "p_gone",
         "profile": {"id": "p_gone", "name": "Snapshot", "script_path": str(echo_script), "args": [],
                     "custom_args": [{"name": "--flag", "type": "text", "value": "snap"}]},
         "arg_values": {"--flag": "over"}},
        {"type": "parallel", "profiles": [
            {"profile_id": "ghost",
             "profile": {"id": "ghost", "name": "SnapPar", "script_path": str(pass_script), "args": [], "custom_args": []}},
        ]},
    ]}, rid, time.time())
    run = runner.active_runs[rid]
    assert run["status"] == "completed", run["workflow_log"]
    assert run["steps"]["1. Snapshot"]["output"] == ["--flag over\n"], run["steps"]["1. Snapshot"]["output"]
    assert any("SnapPar" in line for line in run["workflow_log"])
    assert not any("[SKIP]" in line for line in run["workflow_log"])
    print("PASS: arg_values override snapshots and parallel groups use snapshot names")
finally:
    runner.active_runs.clear()
    shutil.rmtree(tmp, ignore_errors=True)

print("\nALL TESTS PASSED")
