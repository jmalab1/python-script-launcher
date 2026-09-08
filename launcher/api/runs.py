import os
import time
import threading
from ..storage import load_json, save_history, update_history
from ..config import COL_PROFILES, COL_WORKFLOWS
from ..runner import (
    run_script, execute_workflow, active_runs, run_lock, cancel_run,
    build_custom_args, build_command, prune_active_runs, parse_timeout,
)

# Run ids are unique per process: millisecond start time plus a
# monotonically increasing counter. Lives here (not in runner) so the
# global statement mutates the same counter that is read.
run_counter = 0


def handle_poll_all():
    prune_active_runs()
    with run_lock:
            runs = {
                k: _polled_entry(v)
                for k, v in active_runs.items()
            }
    return runs


def _polled_entry(entry):
    """One run's poll view: the fields the run modal renders."""
    return {
        "output": entry["output"],
        "workflow_log": entry.get("workflow_log", []),
        "status": entry.get("status", "running"),
        "returncode": entry.get("returncode"),
        "steps": entry.get("steps", {}),
        "current_step": entry.get("current_step"),
        "command": entry.get("command"),
        "timed_out": bool(entry.get("timed_out")),
        "cancelled": bool(entry.get("cancelled")),
    }


def handle_poll(run_id):
    with run_lock:
        run_data = active_runs.get(run_id)
    if run_data:
        return _polled_entry(run_data)
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

    prune_active_runs()
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

    def record_history(status, returncode, output, timed_out):
        save_history(
            run_id, profile_name, "profile", status, returncode, output,
            started_at, command=command, trigger=trigger,
            schedule_id=schedule_id, schedule_name=schedule_name,
            timed_out=timed_out,
        )

    # Record the run up front (status: running), the same way workflow runs
    # are recorded, so it is visible in history while it runs and is not
    # lost entirely if the server dies before the script finishes.
    record_history("running", None, [], False)

    def do_run():
        timeout = parse_timeout(profile.get("timeout"))
        for line in run_script(profile["script_path"], full_args, run_id, timeout=timeout):
            pass
        with run_lock:
            # A cancelled run was stopped on purpose, so it is not failed
            # even though its killed script exits non-zero.
            if active_runs[run_id].get("cancelled"):
                status = "cancelled"
            elif active_runs[run_id].get("returncode", 0) != 0:
                status = "failed"
            else:
                status = "completed"
            active_runs[run_id]["status"] = status
            active_runs[run_id]["finished_at"] = time.time()
            returncode = active_runs[run_id].get("returncode")
            output_copy = list(active_runs[run_id]["output"])
            timed_out = bool(active_runs[run_id].get("timed_out"))
        updated = update_history(
            run_id, status=status, returncode=returncode, output=output_copy,
            timed_out=timed_out,
        )
        if not updated:
            # The up-front entry was deleted while the run was in progress
            # (e.g. the user cleared history), so write a fresh one rather
            # than losing the result.
            record_history(status, returncode, output_copy, timed_out)

    threading.Thread(target=do_run, daemon=True).start()
    return {"run_id": run_id}, None


def handle_run_profile(data):
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

    prune_active_runs()
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


def handle_cancel_run(run_id):
    """Stop a running run. Returns (result, status, error) like run handlers."""
    if not cancel_run(run_id):
        return None, 404, {"error": "Run not found or already finished"}
    return {"ok": True}, 200, None
