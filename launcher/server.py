import http.server
import json
import logging
import mimetypes
import os
import re
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import PORT, DATA_DIR, INDEX_FILE, STATIC_DIR, log_file
from .config import LOG_MAX_BYTES, LOG_BACKUP_COUNT

from .api import profiles, workflows, runs, history, filesystem, audit, logs
from . import compress

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("launcher")


class TimestampedRotatingFileHandler(RotatingFileHandler):
    """Size-based rotation whose backups carry the rollover datetime.

    Backups are named <log>.YYYY-MM-DD_HH-MM-SS instead of <log>.1, .2, ...
    so it is obvious when each one was written. RotatingFileHandler's
    default pruning only recognizes numeric suffixes, so getFilesToDelete
    is overridden to prune the oldest timestamped backups.
    """

    SUFFIX_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(?:-\d+)?$")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.namer = self._timestamped_name

    def _timestamped_name(self, default_name):
        stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        candidate = f"{self.baseFilename}.{stamp}"
        n = 1
        while os.path.exists(candidate):
            candidate = f"{self.baseFilename}.{stamp}-{n}"
            n += 1
        return candidate

    def getFilesToDelete(self):
        dir_name, base_name = os.path.split(self.baseFilename)
        names = []
        for name in os.listdir(dir_name):
            if name.startswith(base_name + "."):
                suffix = name[len(base_name) + 1:]
                if self.SUFFIX_PATTERN.match(suffix):
                    names.append(name)
        names.sort()
        excess = len(names) - self.backupCount
        if excess <= 0:
            return []
        return [os.path.join(dir_name, name) for name in names[:excess]]

    def doRollover(self):
        super().doRollover()
        # Unlike the numeric-shift scheme, timestamped names accumulate,
        # so pruning has to happen explicitly after each rollover.
        for path in self.getFilesToDelete():
            os.remove(path)


def setup_file_logging():
    """Mirror log output into a rotating data/server.log.

    The Makefile redirect only covers Unix dev runs; this gives every
    launch path (Windows start.bat, plain python launcher.py, e2e
    harness) a portable log file that the /api/logs endpoint can serve.
    Rotation keeps the file from growing without bound.
    """
    if getattr(setup_file_logging, "_done", False):
        return
    setup_file_logging._done = True
    try:
        log_file().parent.mkdir(parents=True, exist_ok=True)
        handler = TimestampedRotatingFileHandler(
            log_file(),
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logging.getLogger().addHandler(handler)
    except OSError as e:
        log.warning("Could not open log file %s: %s", log_file(), e)


class LauncherHandler(http.server.SimpleHTTPRequestHandler):

    protocol_version = "HTTP/1.1"
    disable_nagle_algorithm = True

    def log_message(self, fmt, *args):
        log.info(fmt, *args)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        try:
            if path == "/" or path == "/index.html":
                content = INDEX_FILE.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                content = self._maybe_gzip("text/html", content, cache_path=INDEX_FILE)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            elif path == "/api/browse":
                dir_path = query.get("path", [str(Path.home())])[0]
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

            elif path == "/api/audit":
                page = int(query.get("page", ["1"])[0])
                per_page = int(query.get("per_page", ["20"])[0])
                action_filter = query.get("action", [None])[0]
                entity_filter = query.get("entity", [None])[0]
                self._json_response(audit.handle_list(page, per_page, action_filter, entity_filter))

            elif path.startswith("/api/audit/"):
                entry_id = path.split("/")[-1]
                entry = audit.handle_detail(entry_id)
                if entry:
                    self._json_response(entry)
                else:
                    self._json_response({"error": "Not found"}, 404)

            elif path == "/api/runs":
                self._json_response(runs.handle_poll_all())

            elif path == "/api/logs":
                lines = query.get("lines", ["500"])[0]
                after = query.get("after", [None])[0]
                self._json_response(logs.handle_list(lines=lines, after=after))

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
        static_dir = STATIC_DIR.resolve()
        rel = urllib.parse.unquote(path[len("/static/"):])
        file_path = (static_dir / rel).resolve()
        try:
            if not file_path.is_relative_to(static_dir):
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
        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        content = self._maybe_gzip(content_type, content, cache_path=file_path)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

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

            elif path == "/api/profiles/reorder":
                result = profiles.handle_reorder(data)
                self._json_response(result)

            elif path.startswith("/api/profiles/") and path.endswith("/duplicate"):
                profile_id = path[len("/api/profiles/"):-len("/duplicate")]
                result = profiles.handle_duplicate(profile_id)
                if result:
                    self._json_response(result)
                else:
                    self._json_response({"error": "Not found"}, 404)

            elif path.startswith("/api/profiles/") and path.endswith("/restore"):
                profile_id = path[len("/api/profiles/"):-len("/restore")]
                result = profiles.handle_restore(profile_id)
                if result:
                    self._json_response(result)
                else:
                    self._json_response({"error": "Not found"}, 404)

            elif path == "/api/workflows":
                result = workflows.handle_create(data)
                self._json_response(result)

            elif path == "/api/workflows/reorder":
                result = workflows.handle_reorder(data)
                self._json_response(result)

            elif path.startswith("/api/workflows/") and path.endswith("/duplicate"):
                workflow_id = path[len("/api/workflows/"):-len("/duplicate")]
                result = workflows.handle_duplicate(workflow_id)
                if result:
                    self._json_response(result)
                else:
                    self._json_response({"error": "Not found"}, 404)

            elif path.startswith("/api/workflows/") and path.endswith("/restore"):
                workflow_id = path[len("/api/workflows/"):-len("/restore")]
                result = workflows.handle_restore(workflow_id)
                if result:
                    self._json_response(result)
                else:
                    self._json_response({"error": "Not found"}, 404)

            elif path == "/api/history/bulk":
                ids = data.get("ids", [])
                result = history.handle_bulk_delete(ids)
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
            if path.startswith("/api/profiles/") and path.endswith("/permanent"):
                profile_id = path[len("/api/profiles/"):-len("/permanent")]
                result = profiles.handle_permanent_delete(profile_id)
                self._json_response(result)

            elif path.startswith("/api/profiles/"):
                profile_id = path.split("/")[-1]
                result = profiles.handle_delete(profile_id)
                self._json_response(result)

            elif path.startswith("/api/workflows/") and path.endswith("/permanent"):
                workflow_id = path[len("/api/workflows/"):-len("/permanent")]
                result = workflows.handle_permanent_delete(workflow_id)
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

    def _maybe_gzip(self, content_type, body, cache_path=None):
        """gzip `body` when the client accepts it; sets Content-Encoding."""
        if (compress.wants_gzip(self.headers.get("Accept-Encoding"))
                and compress.should_compress(content_type, len(body))):
            body = compress.gzip_static(cache_path, body) if cache_path else compress.gzip_bytes(body)
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        return body

    def _json_response(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        body = self._maybe_gzip("application/json", body)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    DATA_DIR.mkdir(exist_ok=True)
    setup_file_logging()
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), LauncherHandler)
    except OSError as e:
        log.error("Could not start server on port %s: %s", PORT, e)
        log.error("Is another instance of the launcher already running?")
        if os.name == "nt":
            input("Press Enter to exit...")
        sys.exit(1)
    log.info("Python Web Launcher running at http://127.0.0.1:%s", PORT)
    log.info("Press Ctrl+C to stop.")
    if os.name == "nt":
        threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down.")
        server.shutdown()
