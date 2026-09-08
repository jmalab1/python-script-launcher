import sys
import time

import pytest

import launcher.runner as runner
import launcher.storage as storage


@pytest.fixture
def runner_env(store, tmp_path):
    """Write helper scripts plus a profiles file and return their paths."""
    pass_script = tmp_path / "pass.py"
    pass_script.write_text("print('ok')\n")
    fail_script = tmp_path / "fail.py"
    fail_script.write_text("print('bad')\nimport sys\nsys.exit(3)\n")
    echo_script = tmp_path / "echo.py"
    echo_script.write_text("import sys\nprint(' '.join(sys.argv[1:]))\n")

    store.seed("profiles", [
        {"id": "p_pass", "name": "Pass", "script_path": str(pass_script), "args": [], "custom_args": []},
        {"id": "p_fail", "name": "Fail", "script_path": str(fail_script), "args": [], "custom_args": []},
        {"id": "p_echo", "name": "Echo", "script_path": str(echo_script), "args": ["static"], "custom_args": [
            {"name": "--flag", "type": "text", "value": "v1"},
            {"name": "--cb", "type": "checkbox", "value": "true"},
            {"name": "--off", "type": "checkbox", "value": "false"},
        ]},
    ])
    return {"pass": pass_script, "fail": fail_script, "echo": echo_script}


def last_history(store):
    return store.read("history")[-1]


def test_next_step_name_numbers_steps_per_run(new_run):
    rid = new_run("wf_dn")
    named = [runner._next_step_name(rid, "Step") for _ in range(3)]
    assert named == [(1, "1. Step"), (2, "2. Step"), (3, "3. Step")], named


def test_run_script_streams_lines_and_captures_exit_code(new_run, runner_env):
    rid = new_run("wf_rs")
    result = {}
    lines = list(runner.run_script(str(runner_env["pass"]), [], rid, result=result))
    assert lines == ["ok\n"], lines
    assert result["returncode"] == 0
    assert runner.active_runs[rid]["returncode"] == 0


def test_run_script_reports_failing_exit_codes(new_run, runner_env):
    rid = new_run("wf_rs2")
    result = {}
    list(runner.run_script(str(runner_env["fail"]), [], rid, result=result))
    assert result["returncode"] == 3


def test_run_script_turns_spawn_errors_into_error_output(new_run, monkeypatch):
    def boom(*a, **k):
        raise OSError("spawn failed")

    monkeypatch.setattr(runner.subprocess, "Popen", boom)
    rid = new_run("wf_rs3")
    result = {}
    assert list(runner.run_script("x.py", [], rid, result=result)) == []
    assert result["returncode"] == -1
    assert any("ERROR:" in line for line in runner.active_runs[rid]["output"])


def test_workflow_stops_at_first_failing_step_by_default(new_run, store, runner_env):
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
    saved = last_history(store)
    assert saved["type"] == "workflow" and saved["status"] == "failed"
    assert list(saved["steps"].keys()) == ["1. Pass", "2. Fail"]


def test_continue_on_error_runs_steps_after_a_failure(new_run, runner_env):
    rid = new_run("wf_cont")
    workflow = {"name": "Cont", "continue_on_error": True, "steps": [
        {"type": "sequential", "profile_id": "p_pass"},
        {"type": "sequential", "profile_id": "p_fail"},
        {"type": "sequential", "profile_id": "p_pass"},
    ]}
    runner.execute_workflow(workflow, rid, time.time())
    run = runner.active_runs[rid]
    assert run["status"] == "failed"
    assert list(run["steps"].keys()) == ["1. Pass", "2. Fail", "3. Pass"], list(run["steps"].keys())
    assert run["steps"]["3. Pass"]["status"] == "completed"


def test_missing_profiles_abort_by_default_but_are_skipped_with_continue_on_error(new_run, runner_env):
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


def test_parallel_groups_run_all_profiles_with_per_step_args(new_run, runner_env):
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


def test_missing_profile_in_a_parallel_group_aborts_the_workflow(new_run, runner_env):
    rid = new_run("wf_par_miss")
    runner.execute_workflow({"name": "PM", "steps": [
        {"type": "parallel", "profiles": [{"profile_id": "ghost"}, {"profile_id": "p_pass"}]},
    ]}, rid, time.time())
    run = runner.active_runs[rid]
    assert run["status"] == "failed"
    assert any("[SKIP]" in line for line in run["workflow_log"])
    assert run.get("steps", {}) == {}


def test_embedded_profile_snapshot_is_used_at_run_time(new_run, runner_env):
    rid = new_run("wf_snap")
    runner.execute_workflow({"name": "Snap", "steps": [
        {"type": "sequential", "profile_id": "p_gone",
         "profile": {"id": "p_gone", "name": "Snapshot", "script_path": str(runner_env["echo"]), "args": [],
                     "custom_args": [{"name": "--flag", "type": "text", "value": "snap"}]}},
    ]}, rid, time.time())
    run = runner.active_runs[rid]
    assert run["status"] == "completed", run["workflow_log"]
    assert "1. Snapshot" in run["steps"]
    assert run["steps"]["1. Snapshot"]["output"] == ["--flag snap\n"], run["steps"]["1. Snapshot"]["output"]


def test_workflow_creates_a_running_history_entry_then_finalizes_it_in_place(new_run, store, runner_env, monkeypatch):
    saved_statuses = []
    real_save_history = storage.save_history

    def spy_save_history(run_id, name, run_type, status, returncode, output, started_at, **kw):
        saved_statuses.append(status)
        return real_save_history(run_id, name, run_type, status, returncode, output, started_at, **kw)

    monkeypatch.setattr(runner, "save_history", spy_save_history)

    rid = new_run("wf_live")
    runner.execute_workflow({"name": "Live", "steps": [
        {"type": "sequential", "profile_id": "p_pass"},
    ]}, rid, time.time())

    assert saved_statuses == ["running"], "only the initial entry is saved; the finish updates it in place"
    entries = store.read("history")
    assert len(entries) == 1, "finished run must not duplicate its history entry"
    entry = entries[0]
    assert entry["run_id"] == rid and entry["type"] == "workflow" and entry["status"] == "completed"
    assert entry["workflow_log"][0] == "Starting workflow: Live"
    assert entry["workflow_log"][-1] == "Workflow completed"
    assert entry["steps"]["1. Pass"]["status"] == "completed"
    assert "[RUN] Step 1: Pass" in entry["output_preview"]


def test_workflow_history_entry_stays_addressable_after_finishing(new_run, store, runner_env):
    import launcher.api.history as history

    rid = new_run("wf_addr")
    runner.execute_workflow({"name": "Addr", "steps": [
        {"type": "sequential", "profile_id": "p_pass"},
    ]}, rid, time.time())
    detail = history.handle_detail(rid, "workflow")
    assert detail is not None and detail["status"] == "completed"
    listed = [e for e in history.handle_list(1, 50, "workflow")["entries"] if e["run_id"] == rid]
    assert len(listed) == 1 and listed[0]["duration"] is not None and listed[0]["duration"] >= 0


def test_workflow_aborting_on_a_missing_profile_still_finalizes_history(new_run, store, runner_env):
    rid = new_run("wf_miss_hist")
    runner.execute_workflow({"name": "M", "steps": [
        {"type": "sequential", "profile_id": "ghost"},
        {"type": "sequential", "profile_id": "p_pass"},
    ]}, rid, time.time())
    entries = store.read("history")
    assert len(entries) == 1
    entry = entries[0]
    assert entry["status"] == "failed"
    assert any("[SKIP]" in line for line in entry["workflow_log"])
    assert entry["steps"] == {}


def test_arg_values_override_snapshots_and_parallel_groups_use_snapshot_names(new_run, runner_env):
    rid = new_run("wf_snap2")
    runner.execute_workflow({"name": "Snap2", "steps": [
        {"type": "sequential", "profile_id": "p_gone",
         "profile": {"id": "p_gone", "name": "Snapshot", "script_path": str(runner_env["echo"]), "args": [],
                     "custom_args": [{"name": "--flag", "type": "text", "value": "snap"}]},
         "arg_values": {"--flag": "over"}},
        {"type": "parallel", "profiles": [
            {"profile_id": "ghost",
             "profile": {"id": "ghost", "name": "SnapPar", "script_path": str(runner_env["pass"]), "args": [],
                         "custom_args": []}},
        ]},
    ]}, rid, time.time())
    run = runner.active_runs[rid]
    assert run["status"] == "completed", run["workflow_log"]
    assert run["steps"]["1. Snapshot"]["output"] == ["--flag over\n"], run["steps"]["1. Snapshot"]["output"]
    assert any("SnapPar" in line for line in run["workflow_log"])
    assert not any("[SKIP]" in line for line in run["workflow_log"])


def test_build_command_returns_the_full_argv():
    cmd = runner.build_command("script.py", ["--flag", "v"])
    assert cmd == [sys.executable, "script.py", "--flag", "v"], cmd


def test_workflow_steps_record_the_command_that_ran(new_run, store, runner_env):
    rid = new_run("wf_cmd")
    runner.execute_workflow({"name": "Cmd", "steps": [
        {"type": "sequential", "profile_id": "p_echo", "args": ["extra"], "arg_values": {"--flag": "v2"}},
        {"type": "parallel", "profiles": [{"profile_id": "p_pass"}]},
    ]}, rid, time.time())

    step = runner.active_runs[rid]["steps"]["1. Echo"]
    assert step["command"] == [sys.executable, str(runner_env["echo"]), "--flag", "v2", "--cb", "extra"], step["command"]

    entry = last_history(store)
    assert entry["steps"]["1. Echo"]["command"] == [sys.executable, str(runner_env["echo"]), "--flag", "v2", "--cb", "extra"]
    assert entry["steps"]["2. Pass"]["command"] == [sys.executable, str(runner_env["pass"])]
