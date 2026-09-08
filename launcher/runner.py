import os
import sys
import subprocess
import threading
from .storage import load_json, save_json, save_history
from .config import PROFILES_FILE

active_runs = {}
run_counter = 0
run_lock = threading.Lock()

_POPEN_KWARGS = {}
if os.name == "nt":
    _POPEN_KWARGS["creationflags"] = subprocess.CREATE_NO_WINDOW

_CHILD_ENV = {
    **os.environ,
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUNBUFFERED": "1",
}


def run_script(script_path, args, run_id, result=None):
    cmd = [sys.executable, script_path] + args
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=_CHILD_ENV,
            **_POPEN_KWARGS,
        )
        with run_lock:
            active_runs[run_id]["process"] = proc

        for line in iter(proc.stdout.readline, ""):
            with run_lock:
                active_runs[run_id]["output"].append(line)
            yield line

        proc.wait()
        with run_lock:
            active_runs[run_id]["returncode"] = proc.returncode
            if result is not None:
                result["returncode"] = proc.returncode
    except Exception as e:
        with run_lock:
            active_runs[run_id]["output"].append(f"ERROR: {e}\n")
            active_runs[run_id]["returncode"] = -1
            if result is not None:
                result["returncode"] = -1


def _next_step_name(run_id, step_name):
    n = active_runs[run_id].get("step_count", 0) + 1
    active_runs[run_id]["step_count"] = n
    return n, f"{n}. {step_name}"


def _resolve_profile(profile_map, entry):
    snapshot = entry.get("profile")
    if snapshot:
        return snapshot
    return profile_map.get(entry.get("profile_id"))


def execute_workflow(workflow, run_id, started_at):
    profiles = load_json(PROFILES_FILE)
    profile_map = {p["id"]: p for p in profiles}

    steps = workflow.get("steps", [])
    continue_on_error = workflow.get("continue_on_error", False)

    with run_lock:
        active_runs[run_id]["workflow_log"] = [f"Starting workflow: {workflow.get('name', 'Unnamed')}"]
        active_runs[run_id]["status"] = "running"

    for step in steps:
        step_type = step.get("type", "sequential")

        if step_type == "parallel":
            group_profiles = step.get("profiles", [])
            if not group_profiles:
                continue

            with run_lock:
                step_names = []
                for p in group_profiles:
                    prof = _resolve_profile(profile_map, p) or {}
                    step_names.append(prof.get("name") or p.get("profile_id", "?"))
                active_runs[run_id]["workflow_log"].append(f"[PARALLEL] Running {len(group_profiles)} steps: {', '.join(step_names)}")
            threads = []
            for profile_entry in group_profiles:
                profile = _resolve_profile(profile_map, profile_entry)
                if not profile:
                    with run_lock:
                        active_runs[run_id]["workflow_log"].append(f"[SKIP] Profile not found: {profile_entry['profile_id']}")
                        if not continue_on_error:
                            active_runs[run_id]["failed"] = True
                    if not continue_on_error:
                        break
                    continue

                t = threading.Thread(
                    target=_run_step,
                    args=(profile, profile_entry.get("args", []), run_id, continue_on_error, profile_entry.get("arg_values", {})),
                )
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            with run_lock:
                if not continue_on_error and active_runs[run_id].get("failed"):
                    break
        else:
            profile = _resolve_profile(profile_map, step)
            if not profile:
                with run_lock:
                    active_runs[run_id]["workflow_log"].append(f"[SKIP] Profile not found: {step.get('profile_id')}")
                if not continue_on_error:
                    with run_lock:
                        active_runs[run_id]["status"] = "failed"
                    return
                continue

            _run_step(profile, step.get("args", []), run_id, continue_on_error, step.get("arg_values", {}))
            with run_lock:
                if not continue_on_error and active_runs[run_id].get("failed"):
                    break

    with run_lock:
        status = "failed" if active_runs[run_id].get("failed") else "completed"
        active_runs[run_id]["status"] = status
        active_runs[run_id]["workflow_log"].append(f"Workflow {status}")
    save_history(run_id, workflow.get("name", "Unnamed"), "workflow", status, None, active_runs[run_id]["workflow_log"], started_at, workflow_log=active_runs[run_id]["workflow_log"], steps=active_runs[run_id].get("steps", {}))


def _run_step(profile, extra_args, run_id, continue_on_error, arg_overrides=None):
    script_path = profile.get("script_path", "")
    step_name = profile.get("name", "Unnamed")

    with run_lock:
        n, display_name = _next_step_name(run_id, step_name)

    if not os.path.isfile(script_path):
        with run_lock:
            steps = active_runs[run_id].setdefault("steps", {})
            steps[display_name] = {"output": [], "status": "failed", "returncode": -1, "step": n}
            active_runs[run_id]["workflow_log"].append(f"[SKIP] Step {n} ({step_name}): script not found: {script_path}")
            active_runs[run_id]["failed"] = True
        return

    overrides = arg_overrides or {}
    custom_args = profile.get("custom_args", [])
    built_args = []
    for ca in custom_args:
        flag = ca.get("name", "")
        if not flag:
            continue
        val = overrides.get(flag, ca.get("value", ca.get("default", "")))
        if ca.get("type") == "checkbox":
            if val == "true":
                built_args.append(flag)
        else:
            if val:
                built_args.append(flag)
                built_args.append(str(val))

    args = built_args + list(extra_args)

    with run_lock:
        steps = active_runs[run_id].setdefault("steps", {})
        steps[display_name] = {"output": [], "status": "running", "returncode": None, "step": n}
        active_runs[run_id]["workflow_log"].append(f"[RUN] Step {n}: {step_name}")
        active_runs[run_id]["current_step"] = display_name

    step_result = {"returncode": None}
    for line in run_script(script_path, args, run_id, result=step_result):
        with run_lock:
            steps[display_name]["output"].append(line)

    with run_lock:
        rc = step_result["returncode"] or 0
        steps[display_name]["returncode"] = rc
        if rc != 0:
            steps[display_name]["status"] = "failed"
            active_runs[run_id]["failed"] = True
            active_runs[run_id]["workflow_log"].append(f"[FAIL] Step {n} ({step_name}) exited with code {rc}")
            if not continue_on_error:
                active_runs[run_id]["workflow_log"].append("[ABORT] Workflow stopped due to error.")
        else:
            steps[display_name]["status"] = "completed"
            active_runs[run_id]["workflow_log"].append(f"[DONE] Step {n} ({step_name}) completed successfully")
