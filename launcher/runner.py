import os
import sys
import subprocess
import threading
import time
from datetime import datetime

from .storage import load_json, save_json, save_history, update_history
from .config import COL_PROFILES

DEFAULT_DATE_FORMAT = "%Y-%m-%d"

active_runs = {}
run_lock = threading.Lock()

# Finished runs are kept pollable for a grace period (the run modal falls
# back to history for anything older), and their total count is capped so
# active_runs cannot grow without bound over a long-lived server.
FINISHED_RUN_TTL_SECONDS = 600
MAX_FINISHED_RUNS = 50

_POPEN_KWARGS = {}
if os.name == "nt":
    _POPEN_KWARGS["creationflags"] = subprocess.CREATE_NO_WINDOW

_CHILD_ENV = {
    **os.environ,
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUNBUFFERED": "1",
}


def build_command(script_path, args):
    """Return the full argv used to launch a script, for history/logging."""
    return [sys.executable, script_path] + list(args)


def parse_timeout(value):
    """Turn a profile's timeout setting into seconds, or None to disable.

    Accepts numbers or numeric strings (e.g. 30 or "30"). Anything that
    is missing, unparseable, or not positive means "no time limit".
    """
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return seconds if seconds > 0 else None


def run_script(script_path, args, run_id, result=None, timeout=None):
    """Run a script, yielding its output line by line.

    With a positive `timeout` (seconds), a watchdog thread kills the
    script if it is still running after that long. The killed run is
    reported as failed with a "Timed out" line in its output.
    """
    cmd = build_command(script_path, args)
    done = threading.Event()
    seconds = parse_timeout(timeout)
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
            # A list, not a single slot: parallel workflow steps share the
            # run id, so cancelling must be able to reach every live script.
            active_runs[run_id].setdefault("processes", []).append(proc)
            # A cancel that arrived before this process was registered
            # would otherwise be missed, so honour it here too.
            if active_runs[run_id].get("cancelled") and proc.poll() is None:
                try:
                    proc.kill()
                except OSError:
                    pass

        def kill_after_timeout():
            # done.wait returns True when the script finishes first,
            # False when the timeout elapses and we must kill it.
            if done.wait(seconds):
                return
            with run_lock:
                entry = active_runs.get(run_id)
                if entry is not None and proc in entry.get("processes", []):
                    # Per-script marker; run_script turns it into the
                    # run-entry "timed_out" flag once it reports the kill.
                    entry["_step_timed_out"] = True
            try:
                if proc.poll() is None:
                    proc.kill()
            except OSError:
                pass

        if seconds:
            threading.Thread(target=kill_after_timeout, daemon=True).start()

        for line in iter(proc.stdout.readline, ""):
            with run_lock:
                active_runs[run_id]["output"].append(line)
            yield line

        done.set()
        proc.wait()
        with run_lock:
            active_runs[run_id]["returncode"] = proc.returncode
            # Keep the run-level flag (used by poll and history) in sync:
            # it stays True for the rest of the run once any script hit
            # its timeout.
            timed_out = active_runs[run_id].pop("_step_timed_out", False)
            if timed_out:
                active_runs[run_id]["timed_out"] = True
            if result is not None:
                result["returncode"] = proc.returncode
        if timed_out:
            message = f"ERROR: Timed out after {seconds:g}s and was killed.\n"
            with run_lock:
                active_runs[run_id]["output"].append(message)
            yield message
    except Exception as e:
        with run_lock:
            active_runs[run_id]["output"].append(f"ERROR: {e}\n")
            active_runs[run_id]["returncode"] = -1
            if result is not None:
                result["returncode"] = -1
    finally:
        done.set()


CANCEL_MESSAGE = "Cancelled by user.\n"


def _is_cancelled(run_id):
    """True if a cancel was requested for this run."""
    with run_lock:
        entry = active_runs.get(run_id)
        return bool(entry and entry.get("cancelled"))


def cancel_run(run_id):
    """Kill a running run's script processes and mark the run cancelled.

    Returns True when the run was still in progress; False when the run
    is unknown (already pruned) or already finished, so there is nothing
    to cancel. The finished run is recorded as "cancelled" — not
    "failed" — by the same finish path that records normal completions.
    """
    with run_lock:
        entry = active_runs.get(run_id)
        if entry is None or entry.get("status") in ("completed", "failed", "cancelled"):
            return False
        entry["cancelled"] = True
        for proc in entry.get("processes", []):
            try:
                if proc.poll() is None:
                    proc.kill()
            except OSError:
                pass
        entry["output"].append(CANCEL_MESSAGE)
        if isinstance(entry.get("workflow_log"), list):
            entry["workflow_log"].append("[CANCEL] Run cancelled by user")
    return True


def _next_step_name(run_id, step_name):
    n = active_runs[run_id].get("step_count", 0) + 1
    active_runs[run_id]["step_count"] = n
    return n, f"{n}. {step_name}"


def format_date_value(value, fmt=None):
    fmt = fmt or DEFAULT_DATE_FORMAT
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime(fmt)
    except ValueError:
        return value


def build_custom_args(custom_args, arg_values=None):
    overrides = arg_values or {}
    built = []
    for ca in custom_args or []:
        flag = ca.get("name", "")
        if not flag:
            continue
        val = overrides.get(flag, ca.get("value", ca.get("default", "")))
        if ca.get("type") == "checkbox":
            if val == "true":
                built.append(flag)
        else:
            if val:
                out = str(val)
                if ca.get("type") == "date":
                    out = format_date_value(out, ca.get("format"))
                built.append(flag)
                built.append(out)
    return built


def _resolve_profile(profile_map, entry):
    snapshot = entry.get("profile")
    if snapshot:
        return snapshot
    return profile_map.get(entry.get("profile_id"))


def execute_workflow(workflow, run_id, started_at, trigger="manual", schedule=None):
    profiles = load_json(COL_PROFILES)
    profile_map = {p["id"]: p for p in profiles}

    steps = workflow.get("steps", [])
    continue_on_error = workflow.get("continue_on_error", False)

    with run_lock:
        workflow_log = [f"Starting workflow: {workflow.get('name', 'Unnamed')}"]
        active_runs[run_id]["workflow_log"] = workflow_log
        active_runs[run_id]["status"] = "running"

    # Record the run up front so it stays visible in history (status: running)
    # even if the run modal is closed before it finishes.
    save_history(
        run_id, workflow.get("name", "Unnamed"), "workflow", "running", None,
        list(workflow_log), started_at, workflow_log=list(workflow_log), steps={},
        trigger=trigger,
        schedule_id=schedule.get("id") if schedule else None,
        schedule_name=schedule.get("name") if schedule else None,
    )

    for step in steps:
        if _is_cancelled(run_id):
            break
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
                if active_runs[run_id].get("cancelled"):
                    break
                if not continue_on_error and active_runs[run_id].get("failed"):
                    break
        else:
            profile = _resolve_profile(profile_map, step)
            if not profile:
                with run_lock:
                    active_runs[run_id]["workflow_log"].append(f"[SKIP] Profile not found: {step.get('profile_id')}")
                    if not continue_on_error:
                        active_runs[run_id]["failed"] = True
                if not continue_on_error:
                    break
                continue

            _run_step(profile, step.get("args", []), run_id, continue_on_error, step.get("arg_values", {}))
            with run_lock:
                if active_runs[run_id].get("cancelled"):
                    break
                if not continue_on_error and active_runs[run_id].get("failed"):
                    break

    with run_lock:
        # A cancelled run is stopped on purpose, so it must not be
        # reported as failed even though its last step exited non-zero.
        if active_runs[run_id].get("cancelled"):
            status = "cancelled"
        elif active_runs[run_id].get("failed"):
            status = "failed"
        else:
            status = "completed"
        active_runs[run_id]["status"] = status
        active_runs[run_id]["finished_at"] = time.time()
        active_runs[run_id]["workflow_log"].append(f"Workflow {status}")
        final_log = list(active_runs[run_id]["workflow_log"])
        final_steps = active_runs[run_id].get("steps", {})
        timed_out = bool(active_runs[run_id].get("timed_out"))
    update_history(
        run_id, status=status, output=final_log,
        workflow_log=final_log, steps=final_steps,
        timed_out=timed_out,
    )


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
            # Mirror the missing-profile behavior: with continue_on_error the
            # step is skipped and the run can still complete.
            if not continue_on_error:
                active_runs[run_id]["failed"] = True
        return

    overrides = arg_overrides or {}
    built_args = build_custom_args(profile.get("custom_args", []), overrides)

    args = built_args + list(extra_args)
    cmd = build_command(script_path, args)

    with run_lock:
        steps = active_runs[run_id].setdefault("steps", {})
        steps[display_name] = {
            "output": [], "status": "running", "returncode": None, "step": n,
            "command": cmd,
        }
        active_runs[run_id]["workflow_log"].append(f"[RUN] Step {n}: {step_name}")
        active_runs[run_id]["current_step"] = display_name

    step_result = {"returncode": None}
    timeout = parse_timeout(profile.get("timeout"))
    for line in run_script(script_path, args, run_id, result=step_result, timeout=timeout):
        with run_lock:
            steps[display_name]["output"].append(line)

    with run_lock:
        rc = step_result["returncode"]
        if rc is None:
            rc = 0
        steps[display_name]["returncode"] = rc
        if rc == 0:
            steps[display_name]["status"] = "completed"
            active_runs[run_id]["workflow_log"].append(f"[DONE] Step {n} ({step_name}) completed successfully")
        elif active_runs[run_id].get("cancelled"):
            # The process was killed by a cancel request, not by its own
            # failure, so the step is recorded as cancelled.
            steps[display_name]["status"] = "cancelled"
            active_runs[run_id]["workflow_log"].append(f"[CANCEL] Step {n} ({step_name}) was stopped")
        else:
            steps[display_name]["status"] = "failed"
            active_runs[run_id]["failed"] = True
            active_runs[run_id]["workflow_log"].append(f"[FAIL] Step {n} ({step_name}) exited with code {rc}")
            if not continue_on_error:
                active_runs[run_id]["workflow_log"].append("[ABORT] Workflow stopped due to error.")


def prune_active_runs():
    """Drop finished runs so active_runs cannot grow without bound.

    Running runs are always kept. Finished runs stay pollable for
    FINISHED_RUN_TTL_SECONDS, and at most MAX_FINISHED_RUNS finished runs
    are retained; older ones remain available through run history.
    """
    with run_lock:
        _prune_active_runs_locked()


def _prune_active_runs_locked():
    now = time.time()
    finished = []
    for run_id, entry in active_runs.items():
        if entry.get("status") in ("completed", "failed"):
            # Entries without a finish stamp (injected tests, older data)
            # get the full grace period instead of being dropped immediately.
            finished.append((run_id, entry.get("finished_at") or now))
    finished.sort(key=lambda item: item[1])
    expired = [run_id for run_id, finished_at in finished if finished_at <= now - FINISHED_RUN_TTL_SECONDS]
    expired_set = set(expired)
    for run_id in expired:
        del active_runs[run_id]
    remaining = [(run_id, ts) for run_id, ts in finished if run_id not in expired_set]
    excess = len(remaining) - MAX_FINISHED_RUNS
    if excess > 0:
        for run_id, _ts in remaining[:excess]:
            del active_runs[run_id]
