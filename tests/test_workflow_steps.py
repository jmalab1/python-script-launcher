import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import launcher.runner as runner

tmp = Path(tempfile.mkdtemp())
pass_script = tmp / "pass.py"
pass_script.write_text("print('ok')\n")
fail_script = tmp / "fail.py"
fail_script.write_text("print('bad')\nimport sys\nsys.exit(3)\n")


def new_run(run_id):
    runner.active_runs[run_id] = {
        "output": [],
        "workflow_log": [],
        "status": "running",
        "returncode": None,
        "failed": False,
    }
    return run_id


profile = {"name": "Test", "script_path": str(pass_script), "args": [], "custom_args": []}

# 1. sequential duplicate steps: both executions must survive in history
rid = new_run("wf_seq_1")
runner._run_step(profile, [], rid, False, {})
runner._run_step(profile, [], rid, False, {})
steps = runner.active_runs[rid]["steps"]
assert list(steps.keys()) == ["Test", "Test (2)"], list(steps.keys())
assert all(s["status"] == "completed" for s in steps.values()), steps
assert all(s["output"] for s in steps.values()), steps
print("PASS: sequential duplicate steps keep separate outputs")

# 2. parallel duplicate steps: same profile twice in one parallel group
rid = new_run("wf_par_1")
t1 = threading.Thread(target=runner._run_step, args=(profile, [], rid, False, {}))
t2 = threading.Thread(target=runner._run_step, args=(profile, [], rid, False, {}))
t1.start()
t2.start()
t1.join()
t2.join()
steps = runner.active_runs[rid]["steps"]
assert sorted(steps.keys()) == ["Test", "Test (2)"], list(steps.keys())
assert all(s["status"] == "completed" for s in steps.values()), steps
assert all(s["returncode"] == 0 for s in steps.values()), steps
print("PASS: parallel duplicate steps get unique tabs and correct rc")

# 3. per-step returncode: parallel pass+fail must not share rc
rid = new_run("wf_rc_1")
fail_profile = {"name": "Failing", "script_path": str(fail_script), "args": [], "custom_args": []}
t1 = threading.Thread(target=runner._run_step, args=(profile, [], rid, False, {}))
t2 = threading.Thread(target=runner._run_step, args=(fail_profile, [], rid, False, {}))
t1.start()
t2.start()
t1.join()
t2.join()
steps = runner.active_runs[rid]["steps"]
assert steps["Test"]["returncode"] == 0 and steps["Test"]["status"] == "completed", steps["Test"]
assert steps["Failing"]["returncode"] == 3 and steps["Failing"]["status"] == "failed", steps["Failing"]
print("PASS: parallel steps report their own returncode")

for rid in ("wf_seq_1", "wf_par_1", "wf_rc_1"):
    del runner.active_runs[rid]

print("\nALL TESTS PASSED")
