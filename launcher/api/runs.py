import os
import time
import threading
from ..storage import load_json, save_json, save_history
from ..config import COL_PROFILES, COL_WORKFLOWS
from ..runner import run_script, execute_workflow, active_runs, run_lock, run_counter, build_custom_args, build_command


def handle_poll_all():
    with run_lock:
        runs = {
            k: {
                "output": v["output"],
                "workflow_log": v.get("workflow_log", []),
                "status": v.get("status", "running"),
                "returncode": v.get("returncode"),
                "steps": v.get("steps", {}),
                "current_step": v.get("current_step"),
                "command": v.get("command"),
            }
            for k, v in active_runs.items()
        }
    return runs


def handle_poll(run_id):
    with run_lock:
        run_data = active_runs.get(run_id)
    if run_data:
        return {
            "output": run_data["output"],
            "workflow_log": run_data.get("workflow_log", []),
            "status": run_data.get("status", "running"),
            "returncode": run_data.get("returncode"),
            "steps": run_data.get("steps", {}),
            "current_step": run_data.get("current_step"),
            "command": run_data.get("command"),
        }
    return None


def start_profile_run(profile, arg_values=None, extra_args=None, trigger="manual", schedule=None):
    """Launch a profile run in a background thread.

    Shared by the web UI and the scheduler so both produce identical
    active_runs entries and history records. Returns ({"run_id": ...}, None)
    on success or (None, {"error": ...}) when the script is missing.
    """
    global run_counter
    if not os.path.isfile(profile.get("script_path", "")):
        return None, {"error": f"Script not found: {profile.get('script_path', '')}"}

    built_args = build_custom_args(profile.get("custom_args", []), arg_values)
    full_args = list(profile.get("args", [])) + built_args + list(extra_args or [])
    command = build_command(profile["script_path"], full_args)

    started_at = time.time()

    with run_lock:
        run_counter += 1
        run_id = f"prof_{int(started_at * 1000)}_{run_counter}"
        entry = {
            "output": [],
            "status": "running",
            "returncode": None,
            "failed": False,
            "command": command,
            "trigger": trigger,
        }
        if schedule:
            entry["schedule_id"] = schedule.get("id")
            entry["schedule_name"] = schedule.get("name")
        active_runs[run_id] = entry

    profile_name = profile.get("name", "Unnamed")
    schedule_id = schedule.get("id") if schedule else None
    schedule_name = schedule.get("name") if schedule else None

    def do_run():
        for line in run_script(profile["script_path"], full_args, run_id):
            pass
        with run_lock:
            status = "failed" if active_runs[run_id].get("returncode", 0) != 0 else "completed"
            active_runs[run_id]["status"] = status
            returncode = active_runs[run_id].get("returncode")
            output_copy = list(active_runs[run_id]["output"])
        save_history(
            run_id, profile_name, "profile", status, returncode, output_copy,
            started_at, command=command, trigger=trigger,
            schedule_id=schedule_id, schedule_name=schedule_name,
        )

    threading.Thread(target=do_run, daemon=True).start()
    return {"run_id": run_id}, None


def handle_run_profile(data, send_error=None):
    profile_id = data.get("profile_id")
    profiles = load_json(COL_PROFILES)
    profile = next((p for p in profiles if p["id"] == profile_id), None)
    if not profile:
        return None, 404, {"error": "Profile not found"}

    result, error = start_profile_run(
        profile, arg_values=data.get("arg_values"), extra_args=data.get("args"),
    )
    if error:
        return None, 400, error
    return result, 200, None


def start_workflow_run(workflow, trigger="manual", schedule=None):
    """Launch a workflow run in a background thread.

    Returns ({"run_id": ...}, None); the workflow is assumed to exist
    (callers resolve it from storage first).
    """
    global run_counter
    started_at = time.time()

    with run_lock:
        run_counter += 1
        run_id = f"wf_{int(started_at * 1000)}_{run_counter}"
        entry = {
            "output": [],
            "workflow_log": [],
            "status": "starting",
            "returncode": None,
            "failed": False,
            "trigger": trigger,
        }
        if schedule:
            entry["schedule_id"] = schedule.get("id")
            entry["schedule_name"] = schedule.get("name")
        active_runs[run_id] = entry

    threading.Thread(
        target=execute_workflow,
        args=(workflow, run_id, started_at, trigger, schedule),
        daemon=True,
    ).start()
    return {"run_id": run_id}, None


def handle_run_workflow(data):
    workflow_id = data.get("workflow_id")
    all_workflows = load_json(COL_WORKFLOWS)
    workflow = next((w for w in all_workflows if w["id"] == workflow_id), None)
    if not workflow:
        return None, 404, {"error": "Workflow not found"}

    result, error = start_workflow_run(workflow)
    if error:
        return None, 400, error
    return result, 200, None
