#!/usr/bin/env python3
"""Python Web Launcher - Run Python scripts via a local web UI."""

import http.server
import json
import os
import subprocess
import sys
import threading
import urllib.parse
from pathlib import Path

PORT = 8765
DATA_DIR = Path(__file__).parent / "data"
PROFILES_FILE = DATA_DIR / "profiles.json"
WORKFLOWS_FILE = DATA_DIR / "workflows.json"
HISTORY_FILE = DATA_DIR / "history.json"

# Store active processes and their output
active_runs = {}
run_counter = 0
run_lock = threading.Lock()


def load_json(path):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return []


def save_json(path, data):
    DATA_DIR.mkdir(exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def save_history(run_id, name, run_type, status, returncode, output, started_at):
    """Save a completed run to history."""
    import time
    entry = {
        "run_id": run_id,
        "name": name,
        "type": run_type,
        "status": status,
        "returncode": returncode,
        "output_preview": "".join(output[-20:]) if output else "",
        "started_at": started_at,
        "timestamp": time.time(),
    }
    history = load_json(HISTORY_FILE)
    history.append(entry)
    save_json(HISTORY_FILE, history)


def browse_directory(path):
    """List contents of a directory, or return file info if path is a file."""
    path = Path(path).expanduser().resolve()
    if not path.exists():
        return {"error": f"Path does not exist: {path}"}
    if not path.is_dir():
        return {
            "path": str(path.parent),
            "selected_file": {"name": path.name, "path": str(path), "is_dir": False},
            "entries": [],
        }

    entries = []
    # Add parent directory link
    if path.parent != path:
        entries.append({"name": "..", "path": str(path.parent), "is_dir": True})

    try:
        for item in sorted(path.iterdir()):
            entries.append({
                "name": item.name,
                "path": str(item),
                "is_dir": item.is_dir(),
            })
    except PermissionError:
        return {"error": f"Permission denied: {path}"}

    return {"path": str(path), "entries": entries}


def open_file_dialog():
    """Open a native file dialog using zenity or kdialog."""
    import shutil

    if shutil.which("zenity"):
        try:
            result = subprocess.run(
                ["zenity", "--file-selection", "--title=Select Python Script", "--file-filter=Python files (*.py *.pyw)|*.py *.pyw", "--file-filter=All files (*.*)|*.*"],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0 and result.stdout.strip():
                return {"path": result.stdout.strip()}
            return {"path": None}
        except Exception as e:
            return {"error": str(e)}

    if shutil.which("kdialog"):
        try:
            result = subprocess.run(
                ["kdialog", "--getopenfilename", "--", "*.py *.pyw"],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0 and result.stdout.strip():
                return {"path": result.stdout.strip()}
            return {"path": None}
        except Exception as e:
            return {"error": str(e)}

    return {"error": "No file dialog available (install zenity or kdialog)"} 


def run_script(script_path, args, run_id):
    """Run a Python script and capture output."""
    cmd = [sys.executable, script_path] + args
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
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
    except Exception as e:
        with run_lock:
            active_runs[run_id]["output"].append(f"ERROR: {e}\n")
            active_runs[run_id]["returncode"] = -1


def execute_workflow(workflow, run_id, started_at):
    """Execute a workflow according to its configuration."""
    profiles = load_json(PROFILES_FILE)
    profile_map = {p["id"]: p for p in profiles}

    steps = workflow.get("steps", [])
    continue_on_error = workflow.get("continue_on_error", False)

    # Group steps by execution_group for parallel execution
    groups = []
    current_group = []
    current_mode = None

    for step in steps:
        mode = step.get("execution_mode", "sequential")
        if mode != current_mode and current_group:
            groups.append((current_mode, current_group))
            current_group = []
        current_mode = mode
        current_group.append(step)
    if current_group:
        groups.append((current_mode, current_group))

    with run_lock:
        active_runs[run_id]["status"] = "running"

    for mode, group in groups:
        if mode == "parallel":
            threads = []
            for step in group:
                profile = profile_map.get(step["profile_id"])
                if not profile:
                    with run_lock:
                        active_runs[run_id]["output"].append(
                            f"[SKIP] Profile not found: {step['profile_id']}\n"
                        )
                    if not continue_on_error:
                        break
                    continue

                t = threading.Thread(
                    target=_run_step,
                    args=(profile, step.get("args", []), run_id, continue_on_error),
                )
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            # Check if any parallel step failed
            with run_lock:
                if (
                    not continue_on_error
                    and active_runs[run_id].get("failed")
                ):
                    break
        else:
            for step in group:
                profile = profile_map.get(step["profile_id"])
                if not profile:
                    with run_lock:
                        active_runs[run_id]["output"].append(
                            f"[SKIP] Profile not found: {step['profile_id']}\n"
                        )
                    if not continue_on_error:
                        with run_lock:
                            active_runs[run_id]["status"] = "failed"
                        return
                    continue

                _run_step(profile, step.get("args", []), run_id, continue_on_error)
                with run_lock:
                    if (
                        not continue_on_error
                        and active_runs[run_id].get("failed")
                    ):
                        break

            with run_lock:
                if (
                    not continue_on_error
                    and active_runs[run_id].get("failed")
                ):
                    break

    with run_lock:
        status = "failed" if active_runs[run_id].get("failed") else "completed"
        active_runs[run_id]["status"] = status
    save_history(run_id, workflow.get("name", "Unnamed"), "workflow", status, None, active_runs[run_id]["output"], started_at)


def _run_step(profile, extra_args, run_id, continue_on_error):
    """Run a single step in a workflow."""
    script_path = profile.get("script_path", "")

    # Build args from custom_arg definitions using stored values
    custom_args = profile.get("custom_args", [])
    built_args = []
    for ca in custom_args:
        flag = ca.get("name", "")
        if not flag:
            continue
        val = ca.get("value", ca.get("default", ""))
        if ca.get("type") == "checkbox":
            if val == "true":
                built_args.append(flag)
        else:
            if val:
                built_args.append(flag)
                built_args.append(str(val))

    args = profile.get("args", []) + built_args + extra_args

    with run_lock:
        active_runs[run_id]["output"].append(
            f"\n{'='*60}\n"
            f"[RUN] {profile.get('name', 'Unnamed')} - {script_path}\n"
            f"{'='*60}\n"
        )

    for line in run_script(script_path, args, run_id):
        pass  # Output already captured

    with run_lock:
        rc = active_runs[run_id].get("returncode", 0)
        if rc != 0:
            active_runs[run_id]["failed"] = True
            active_runs[run_id]["output"].append(
                f"[FAIL] {profile.get('name')} exited with code {rc}\n"
            )
            if not continue_on_error:
                active_runs[run_id]["output"].append(
                    "[ABORT] Workflow stopped due to error.\n"
                )
        else:
            active_runs[run_id]["output"].append(
                f"[DONE] {profile.get('name')} completed successfully.\n"
            )


class LauncherHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            with open(Path(__file__).parent / "index.html", "rb") as f:
                self.wfile.write(f.read())

        elif path == "/api/browse":
            dir_path = query.get("path", [os.path.expanduser("~")])[0]
            result = browse_directory(dir_path)
            self._json_response(result)

        elif path == "/api/filedialog":
            result = open_file_dialog()
            self._json_response(result)

        elif path == "/api/profiles":
            self._json_response(load_json(PROFILES_FILE))

        elif path == "/api/workflows":
            self._json_response(load_json(WORKFLOWS_FILE))

        elif path == "/api/history":
            page = int(query.get("page", ["1"])[0])
            per_page = int(query.get("per_page", ["15"])[0])
            all_history = load_json(HISTORY_FILE)
            all_history.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            total = len(all_history)
            start = (page - 1) * per_page
            end = start + per_page
            self._json_response({
                "entries": all_history[start:end],
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": (total + per_page - 1) // per_page,
            })

        elif path == "/api/runs":
            with run_lock:
                runs = {
                    k: {
                        "output": v["output"],
                        "status": v.get("status", "running"),
                        "returncode": v.get("returncode"),
                    }
                    for k, v in active_runs.items()
                }
            self._json_response(runs)

        elif path.startswith("/api/runs/"):
            run_id = path.split("/")[-1]
            with run_lock:
                run_data = active_runs.get(run_id)
            if run_data:
                self._json_response({
                    "output": run_data["output"],
                    "status": run_data.get("status", "running"),
                    "returncode": run_data.get("returncode"),
                })
            else:
                self._json_response({"error": "Run not found"}, 404)

        elif path.startswith("/static/"):
            self._serve_static(path)

        else:
            self.send_error(404)

    def _serve_static(self, path):
        """Serve files from the static/ directory."""
        import mimetypes
        static_dir = Path(__file__).parent / "static"
        file_path = static_dir / path[len("/static/"):]
        # Resolve and ensure it's within static_dir (prevent path traversal)
        try:
            file_path = file_path.resolve()
            if not str(file_path).startswith(str(static_dir.resolve())):
                self.send_error(403)
                return
        except Exception:
            self.send_error(403)
            return
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404)
            return
        content_type, _ = mimetypes.guess_type(str(file_path))
        if content_type is None:
            content_type = "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "public, max-age=3600")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        with open(file_path, "rb") as f:
            self.wfile.write(f.read())

    def do_POST(self):
        global run_counter
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b"{}"
        data = json.loads(body)

        if path == "/api/profiles":
            profiles = load_json(PROFILES_FILE)
            profile = data
            if not profile.get("id"):
                import time
                profile["id"] = f"profile_{int(time.time() * 1000)}"
            # Update or add
            profiles = [p for p in profiles if p.get("id") != profile["id"]]
            profiles.append(profile)
            save_json(PROFILES_FILE, profiles)
            self._json_response(profile)

        elif path == "/api/workflows":
            workflows = load_json(WORKFLOWS_FILE)
            workflow = data
            if not workflow.get("id"):
                import time
                workflow["id"] = f"workflow_{int(time.time() * 1000)}"
            workflows = [w for w in workflows if w.get("id") != workflow["id"]]
            workflows.append(workflow)
            save_json(WORKFLOWS_FILE, workflows)
            self._json_response(workflow)

        elif path == "/api/run/profile":
            profile_id = data.get("profile_id")
            arg_values = data.get("arg_values", {})
            profiles = load_json(PROFILES_FILE)
            profile = next((p for p in profiles if p["id"] == profile_id), None)
            if not profile:
                self._json_response({"error": "Profile not found"}, 404)
                return

            # Build args from custom_arg definitions using provided values
            custom_args = profile.get("custom_args", [])
            built_args = []
            for ca in custom_args:
                flag = ca.get("name", "")
                if not flag:
                    continue
                val = arg_values.get(flag, ca.get("value", ca.get("default", "")))
                if ca.get("type") == "checkbox":
                    if val == "true":
                        built_args.append(flag)
                else:
                    if val:
                        built_args.append(flag)
                        built_args.append(str(val))
            # Also include any static args
            static_args = profile.get("args", [])

            import time as _time
            started_at = _time.time()

            with run_lock:
                run_counter += 1
                run_id = f"run_{run_counter}"
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
                save_history(run_id, profile_name, "profile", status, active_runs[run_id].get("returncode"), active_runs[run_id]["output"], started_at)

            threading.Thread(target=do_run, daemon=True).start()
            self._json_response({"run_id": run_id})

        elif path == "/api/run/workflow":
            workflow_id = data.get("workflow_id")
            workflows = load_json(WORKFLOWS_FILE)
            workflow = next((w for w in workflows if w["id"] == workflow_id), None)
            if not workflow:
                self._json_response({"error": "Workflow not found"}, 404)
                return

            import time as _time
            started_at = _time.time()

            with run_lock:
                run_counter += 1
                run_id = f"run_{run_counter}"
                active_runs[run_id] = {
                    "output": [],
                    "status": "starting",
                    "returncode": None,
                    "failed": False,
                }

            threading.Thread(
                target=execute_workflow, args=(workflow, run_id, started_at), daemon=True
            ).start()
            self._json_response({"run_id": run_id})

        else:
            self.send_error(404)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/profiles/"):
            profile_id = path.split("/")[-1]
            profiles = load_json(PROFILES_FILE)
            profiles = [p for p in profiles if p.get("id") != profile_id]
            save_json(PROFILES_FILE, profiles)
            self._json_response({"ok": True})

        elif path.startswith("/api/workflows/"):
            workflow_id = path.split("/")[-1]
            workflows = load_json(WORKFLOWS_FILE)
            workflows = [w for w in workflows if w.get("id") != workflow_id]
            save_json(WORKFLOWS_FILE, workflows)
            self._json_response({"ok": True})

        elif path == "/api/history":
            save_json(HISTORY_FILE, [])
            self._json_response({"ok": True})

        else:
            self.send_error(404)

    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())


def main():
    DATA_DIR.mkdir(exist_ok=True)
    server = http.server.HTTPServer(("127.0.0.1", PORT), LauncherHandler)
    print(f"Python Web Launcher running at http://127.0.0.1:{PORT}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
