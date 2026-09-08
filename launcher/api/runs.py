import os
import time
import threading
from ..storage import load_json, save_json, save_history
from ..config import PROFILES_FILE, HISTORY_FILE
from ..runner import run_script, execute_workflow, active_runs, run_lock, run_counter, build_custom_args


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
        }
    return None


def handle_run_profile(data, send_error):
    global run_counter
    profile_id = data.get("profile_id")
    arg_values = data.get("arg_values", {})
    profiles = load_json(PROFILES_FILE)
    profile = next((p for p in profiles if p["id"] == profile_id), None)
    if not profile:
        return None, 404, {"error": "Profile not found"}

    if not os.path.isfile(profile.get("script_path", "")):
        return None, 400, {"error": f"Script not found: {profile.get('script_path', '')}"}

    built_args = build_custom_args(profile.get("custom_args", []), arg_values)
    static_args = profile.get("args", [])

    started_at = time.time()

    with run_lock:
        run_counter += 1
        run_id = f"prof_{int(started_at * 1000)}_{run_counter}"
        active_runs[run_id] = {
            "output": [],
            "status": "running",
            "returncode": None,
            "failed": False,
        }

    profile_name = profile.get("name", "Unnamed")

    def do_run():
        for line in run_script(
            profile["script_path"], static_args + built_args + data.get("args", []), run_id
        ):
            pass
        with run_lock:
            status = "failed" if active_runs[run_id].get("returncode", 0) != 0 else "completed"
            active_runs[run_id]["status"] = status
            output_copy = list(active_runs[run_id]["output"])
        save_history(run_id, profile_name, "profile", status, active_runs[run_id].get("returncode"), output_copy, started_at)

    threading.Thread(target=do_run, daemon=True).start()
    return {"run_id": run_id}, 200, None


def handle_run_workflow(data):
    global run_counter
    workflow_id = data.get("workflow_id")
    workflows = load_json(PROFILES_FILE)
    from ..config import WORKFLOWS_FILE
    all_workflows = load_json(WORKFLOWS_FILE)
    workflow = next((w for w in all_workflows if w["id"] == workflow_id), None)
    if not workflow:
        return None, 404, {"error": "Workflow not found"}

    started_at = time.time()

    with run_lock:
        run_counter += 1
        run_id = f"wf_{int(started_at * 1000)}_{run_counter}"
        active_runs[run_id] = {
            "output": [],
            "workflow_log": [],
            "status": "starting",
            "returncode": None,
            "failed": False,
        }

    threading.Thread(
        target=execute_workflow, args=(workflow, run_id, started_at), daemon=True
    ).start()
    return {"run_id": run_id}, 200, None
