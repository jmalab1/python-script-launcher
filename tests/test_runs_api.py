import sys
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
            "command": None, "timed_out": False, "cancelled": False,
        }
        assert runs.handle_poll_all()["r1"] == polled
    finally:
        runs.active_runs.clear()


def test_poll_exposes_a_timed_out_flag(store):
    runs.active_runs["r1"] = {"output": [], "status": "failed", "returncode": -9, "timed_out": True}
    try:
        assert runs.handle_poll("r1")["timed_out"] is True
        assert runs.handle_poll_all()["r1"]["timed_out"] is True
    finally:
        runs.active_runs.clear()


def test_run_profile_rejects_unknown_profiles_and_missing_scripts(store, runs_env):
    assert runs.handle_run_profile({"profile_id": "ghost"}) == (None, 404, {"error": "Profile not found"})
    body, status, error = runs.handle_run_profile({"profile_id": "p3"})
    assert body is None and status == 400 and "Script not found" in error["error"]


def test_run_profile_executes_the_script_and_saves_history(store, runs_env):
    body, status, error = runs.handle_run_profile({"profile_id": "p1"})
    assert error is None and status == 200 and body["run_id"].startswith("prof_")
    info = wait_done(body["run_id"])
    assert info["status"] == "completed" and info["returncode"] == 0
    assert info["output"] == ["ok\n"]
    entry = last_history(store)
    assert entry["run_id"] == body["run_id"] and entry["type"] == "profile" and entry["status"] == "completed"


def entries_for_run(store, run_id):
    return [e for e in store.read("history") if e["run_id"] == run_id]


def wait_for_history_entry(store, run_id, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        entries = entries_for_run(store, run_id)
        if entries:
            return entries[0]
        time.sleep(0.02)
    raise AssertionError(f"no history entry appeared for {run_id}")


def test_profile_runs_show_up_in_history_while_still_running(store, runs_env):
    body, _, _ = runs.handle_run_profile({"profile_id": "p4"})
    entry = wait_for_history_entry(store, body["run_id"])
    assert entry["status"] == "running", \
        "a profile run must be visible in history before it finishes"

    info = wait_done(body["run_id"])
    assert info["status"] == "completed"
    entries = entries_for_run(store, body["run_id"])
    assert len(entries) == 1, "the finish must update the existing entry, not add a second one"
    assert entries[0]["status"] == "completed"
    assert entries[0]["output"] == ["start\n", "done\n"]


def test_profile_run_survives_history_being_cleared_mid_run(store, runs_env):
    from launcher.api.history import handle_clear

    body, _, _ = runs.handle_run_profile({"profile_id": "p4"})
    wait_for_history_entry(store, body["run_id"])
    handle_clear()

    info = wait_done(body["run_id"])
    assert info["status"] == "completed"
    entries = entries_for_run(store, body["run_id"])
    assert len(entries) == 1 and entries[0]["status"] == "completed", \
        "clearing history mid-run must not lose the finished run's result"


def test_run_profile_applies_static_custom_and_overridden_args(store, runs_env):
    data = {"profile_id": "p2", "args": ["extra"], "arg_values": {"--flag": "v2"}}
    body, status, error = runs.handle_run_profile(data)
    assert error is None
    info = wait_done(body["run_id"])
    assert info["output"] == ["static --flag v2 --cb extra\n"], info["output"]


def test_profile_history_records_the_command_that_ran(store, runs_env):
    data = {"profile_id": "p2", "args": ["extra"], "arg_values": {"--flag": "v2"}}
    body, status, error = runs.handle_run_profile(data)
    assert error is None
    wait_done(body["run_id"])
    entry = last_history(store)
    assert entry["command"] == [
        sys.executable, str(runs_env["echo"]), "static", "--flag", "v2", "--cb", "extra",
    ], entry["command"]


def test_profile_run_poll_includes_the_command(store, runs_env):
    body, _, _ = runs.handle_run_profile({"profile_id": "p2", "args": ["extra"], "arg_values": {"--flag": "v2"}})
    info = wait_done(body["run_id"])
    assert info["command"] == [
        sys.executable, str(runs_env["echo"]), "static", "--flag", "v2", "--cb", "extra",
    ], info["command"]


def test_run_profile_formats_date_custom_args(store, runs_env):
    body, status, error = runs.handle_run_profile({"profile_id": "p5"})
    assert error is None
    info = wait_done(body["run_id"])
    assert info["output"] == ["--date 2026-09-07 --fmt 07.09.2026\n"], info["output"]


def test_run_profile_formats_overridden_date_values(store, runs_env):
    data = {"profile_id": "p5", "arg_values": {"--date": "2026-01-02"}}
    body, status, error = runs.handle_run_profile(data)
    assert error is None
    info = wait_done(body["run_id"])
    assert info["output"] == ["--date 2026-01-02 --fmt 07.09.2026\n"], info["output"]


def test_run_profile_omits_unselected_enum_args(store, runs_env):
    body, status, error = runs.handle_run_profile({"profile_id": "p6"})
    assert error is None
    info = wait_done(body["run_id"])
    assert info["output"] == ["--level info\n"], info["output"]


def test_run_profile_omits_enum_args_cleared_by_override(store, runs_env):
    data = {"profile_id": "p6", "arg_values": {"--level": ""}}
    body, status, error = runs.handle_run_profile(data)
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


# ------------------------------------------------------------------ run counter


def test_run_ids_use_a_monotonic_counter(store, runs_env):
    first, _, _ = runs.handle_run_profile({"profile_id": "p1"})
    second, _, _ = runs.handle_run_profile({"profile_id": "p1"})
    wait_done(first["run_id"])
    wait_done(second["run_id"])
    n1 = int(first["run_id"].rsplit("_", 1)[1])
    n2 = int(second["run_id"].rsplit("_", 1)[1])
    assert n2 == n1 + 1, (first["run_id"], second["run_id"])


def test_runner_no_longer_exports_a_run_counter_that_runs_shadows():
    """Regression: `from ..runner import run_counter` bound the value at
    import time, so `global run_counter` in runs.py mutated a copy."""
    import launcher.runner as runner

    assert not hasattr(runner, "run_counter"), \
        "runner.run_counter would silently shadow runs.run_counter"


# ------------------------------------------------------------- active_runs pruning


@pytest.fixture
def clean_active_runs():
    import launcher.runner as runner

    runner.active_runs.clear()
    yield runner
    runner.active_runs.clear()


def test_prune_drops_expired_runs_and_caps_finished_ones(clean_active_runs):
    runner = clean_active_runs
    now = time.time()
    runner.active_runs["expired"] = {"output": [], "status": "completed", "finished_at": now - 3600}
    runner.active_runs["recent"] = {"output": [], "status": "failed", "finished_at": now - 1}
    runner.active_runs["running"] = {"output": [], "status": "running"}
    for i in range(60):
        runner.active_runs[f"old_{i}"] = {"output": [], "status": "completed", "finished_at": now - 10 - i}

    runner.prune_active_runs()

    assert "expired" not in runner.active_runs, "runs past the TTL must be pruned"
    assert "recent" in runner.active_runs
    assert "running" in runner.active_runs, "running runs are never pruned"
    finished = [k for k, v in runner.active_runs.items() if v.get("status") in ("completed", "failed")]
    assert len(finished) == runner.MAX_FINISHED_RUNS, "finished runs are capped"


def test_prune_keeps_entries_missing_a_finish_stamp_for_one_ttl_window(clean_active_runs):
    runner = clean_active_runs
    runner.active_runs["nostamp"] = {"output": [], "status": "completed"}
    runner.prune_active_runs()
    assert "nostamp" in runner.active_runs


def test_prune_drops_expired_cancelled_runs(clean_active_runs):
    runner = clean_active_runs
    runner.active_runs["cancelled"] = {
        "output": [], "status": "cancelled", "cancelled": True,
        "finished_at": time.time() - 3600,
    }
    runner.prune_active_runs()
    assert "cancelled" not in runner.active_runs, \
        "a cancelled run is finished and must age out like completed and failed runs"


def test_starting_a_run_keeps_active_runs_bounded(store, runs_env, clean_active_runs):
    runner = clean_active_runs
    now = time.time()
    for i in range(60):
        runner.active_runs[f"old_{i}"] = {"output": [], "status": "completed", "finished_at": now - i}

    body, _, _ = runs.handle_run_profile({"profile_id": "p1"})
    info = wait_done(body["run_id"])
    assert info["status"] == "completed"

    finished = [v for v in runner.active_runs.values() if v.get("status") in ("completed", "failed")]
    assert len(finished) <= runner.MAX_FINISHED_RUNS + 1


def test_pruned_runs_stop_being_pollable(store, runs_env, clean_active_runs, monkeypatch):
    runner = clean_active_runs
    body, _, _ = runs.handle_run_profile({"profile_id": "p1"})
    wait_done(body["run_id"])
    assert runs.handle_poll(body["run_id"]) is not None

    monkeypatch.setattr(runner, "FINISHED_RUN_TTL_SECONDS", 0)
    runner.prune_active_runs()
    assert runs.handle_poll(body["run_id"]) is None, \
        "pruned runs fall back to history on the client"
