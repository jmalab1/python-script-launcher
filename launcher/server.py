import http.server
import json
import logging
import mimetypes
import traceback
import urllib.parse
from pathlib import Path

from .config import PORT, DATA_DIR, INDEX_FILE, STATIC_DIR
from .api import profiles, workflows, runs, history, filesystem

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("launcher")


class LauncherHandler(http.server.SimpleHTTPRequestHandler):

    def log_message(self, fmt, *args):
        log.info(fmt, *args)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        try:
            if path == "/" or path == "/index.html":
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                with open(INDEX_FILE, "rb") as f:
                    self.wfile.write(f.read())

            elif path == "/api/browse":
                dir_path = query.get("path", [Path.home().expanduser("~")])[0]
                result = filesystem.browse_directory(dir_path)
                self._json_response(result)

            elif path == "/api/filedialog":
                result = filesystem.open_file_dialog()
                self._json_response(result)

            elif path == "/api/script_exists":
                script_path = query.get("path", [""])[0]
                result = filesystem.script_exists(script_path)
                self._json_response(result)

            elif path == "/api/profiles":
                self._json_response(profiles.handle_list())

            elif path == "/api/workflows":
                self._json_response(workflows.handle_list())

            elif path == "/api/history":
                page = int(query.get("page", ["1"])[0])
                per_page = int(query.get("per_page", ["15"])[0])
                type_filter = query.get("type", [None])[0]
                self._json_response(history.handle_list(page, per_page, type_filter))

            elif path.startswith("/api/history/"):
                run_id = path.split("/")[-1]
                type_filter = query.get("type", [None])[0]
                entry = history.handle_detail(run_id, type_filter)
                if entry:
                    self._json_response(entry)
                else:
                    self._json_response({"error": "Not found"}, 404)

            elif path == "/api/runs":
                self._json_response(runs.handle_poll_all())

            elif path.startswith("/api/runs/"):
                run_id = path.split("/")[-1]
                result = runs.handle_poll(run_id)
                if result:
                    self._json_response(result)
                else:
                    self._json_response({"error": "Run not found"}, 404)

            elif path.startswith("/static/"):
                self._serve_static(path)

            else:
                self.send_error(404)

        except Exception:
            log.exception("Error handling GET %s", path)
            try:
                self.send_error(500)
            except Exception:
                pass

    def _serve_static(self, path):
        static_dir = STATIC_DIR
        file_path = static_dir / path[len("/static/"):]
        try:
            file_path = file_path.resolve()
            if not str(file_path).startswith(str(static_dir.resolve())):
                log.warning("Path traversal attempt blocked: %s", path)
                self.send_error(403)
                return
        except Exception:
            log.exception("Error resolving static path: %s", path)
            self.send_error(403)
            return
        if not file_path.exists() or not file_path.is_file():
            log.debug("Static file not found: %s", file_path)
            self.send_error(404)
            return
        content_type, _ = mimetypes.guess_type(str(file_path))
        if content_type is None:
            content_type = "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        with open(file_path, "rb") as f:
            self.wfile.write(f.read())

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length else b"{}"
            data = json.loads(body)

            if path == "/api/profiles":
                result = profiles.handle_create(data)
                self._json_response(result)

            elif path == "/api/workflows":
                result = workflows.handle_create(data)
                self._json_response(result)

            elif path == "/api/run/profile":
                result, status, error = runs.handle_run_profile(data, self.send_error)
                if error:
                    self._json_response(error, status)
                else:
                    self._json_response(result)

            elif path == "/api/run/workflow":
                result, status, error = runs.handle_run_workflow(data)
                if error:
                    self._json_response(error, status)
                else:
                    self._json_response(result)

            else:
                self.send_error(404)

        except json.JSONDecodeError:
            log.warning("Invalid JSON in POST %s", path)
            self._json_response({"error": "Invalid JSON"}, 400)
        except Exception:
            log.exception("Error handling POST %s", path)
            try:
                self.send_error(500)
            except Exception:
                pass

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            if path.startswith("/api/profiles/"):
                profile_id = path.split("/")[-1]
                result = profiles.handle_delete(profile_id)
                self._json_response(result)

            elif path.startswith("/api/workflows/"):
                workflow_id = path.split("/")[-1]
                result = workflows.handle_delete(workflow_id)
                self._json_response(result)

            elif path == "/api/history":
                result = history.handle_clear()
                self._json_response(result)

            elif path.startswith("/api/history/"):
                run_id = path.split("/")[-1]
                result = history.handle_delete(run_id)
                self._json_response(result)

            else:
                self.send_error(404)

        except Exception:
            log.exception("Error handling DELETE %s", path)
            try:
                self.send_error(500)
            except Exception:
                pass

    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())


def main():
    DATA_DIR.mkdir(exist_ok=True)
    server = http.server.HTTPServer(("127.0.0.1", PORT), LauncherHandler)
    log.info("Python Web Launcher running at http://127.0.0.1:%s", PORT)
    log.info("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down.")
        server.shutdown()
