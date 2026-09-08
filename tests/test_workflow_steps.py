import threading

import launcher.runner as runner


def test_sequential_duplicate_steps_keep_separate_outputs_and_step_numbers(new_run, tmp_path):
    pass_script = tmp_path / "pass.py"
    pass_script.write_text("print('ok')\n")
    profile = {"name": "Test", "script_path": str(pass_script), "args": [], "custom_args": []}

    rid = new_run("wf_seq_1")
    runner._run_step(profile, [], rid, False, {})
    runner._run_step(profile, [], rid, False, {})
    steps = runner.active_runs[rid]["steps"]
    assert list(steps.keys()) == ["1. Test", "2. Test"], list(steps.keys())
    assert all(s["status"] == "completed" for s in steps.values()), steps
    assert all(s["output"] for s in steps.values()), steps
    assert [s["step"] for s in steps.values()] == [1, 2], steps


def test_parallel_duplicate_steps_get_unique_numbered_tabs_and_correct_rc(new_run, tmp_path):
    pass_script = tmp_path / "pass.py"
    pass_script.write_text("print('ok')\n")
    profile = {"name": "Test", "script_path": str(pass_script), "args": [], "custom_args": []}

    rid = new_run("wf_par_1")
    t1 = threading.Thread(target=runner._run_step, args=(profile, [], rid, False, {}))
    t2 = threading.Thread(target=runner._run_step, args=(profile, [], rid, False, {}))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    steps = runner.active_runs[rid]["steps"]
    assert sorted(steps.keys()) == ["1. Test", "2. Test"], list(steps.keys())
    assert all(s["status"] == "completed" for s in steps.values()), steps
    assert all(s["returncode"] == 0 for s in steps.values()), steps


def test_parallel_steps_report_their_own_returncode(new_run, tmp_path):
    pass_script = tmp_path / "pass.py"
    pass_script.write_text("print('ok')\n")
    fail_script = tmp_path / "fail.py"
    fail_script.write_text("print('bad')\nimport sys\nsys.exit(3)\n")
    profile = {"name": "Test", "script_path": str(pass_script), "args": [], "custom_args": []}
    fail_profile = {"name": "Failing", "script_path": str(fail_script), "args": [], "custom_args": []}

    rid = new_run("wf_rc_1")
    t1 = threading.Thread(target=runner._run_step, args=(profile, [], rid, False, {}))
    t2 = threading.Thread(target=runner._run_step, args=(fail_profile, [], rid, False, {}))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    steps = runner.active_runs[rid]["steps"]
    assert steps["1. Test"]["returncode"] == 0 and steps["1. Test"]["status"] == "completed", steps["1. Test"]
    assert steps["2. Failing"]["returncode"] == 3 and steps["2. Failing"]["status"] == "failed", steps["2. Failing"]
