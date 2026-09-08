"""Tests for the HTTP handler plumbing that used to hide bugs.

Uses a bare LauncherHandler (no socket) fed with stub streams so GET
routing, static containment, and query validation are testable directly.
"""

import email.message
import io
import json
import re
from pathlib import Path

from launcher.config import STATIC_DIR
from launcher.server import LauncherHandler, _is_within


def make_handler(path, method="GET", body=None):
    handler = LauncherHandler.__new__(LauncherHandler)
    handler.path = path
    handler.command = method
    handler.request_version = "HTTP/1.1"
    handler.requestline = path
    handler.headers = email.message.Message()
    handler.headers["Accept-Encoding"] = "identity"
    handler.rfile = io.BytesIO(body or b"")
    handler.wfile = io.BytesIO()
    if body:
        handler.headers["Content-Length"] = str(len(body))
    return handler


def response(handler):
    raw = handler.wfile.getvalue()
    head, _, body_bytes = raw.partition(b"\r\n\r\n")
    status = int(head.split(b"\r\n")[0].decode().split()[1])
    try:
        payload = json.loads(body_bytes.decode()) if body_bytes else None
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = body_bytes.decode(errors="replace")
    return status, payload


# ------------------------------------------------------------------ _is_within


def test_is_within_accepts_paths_inside_the_directory():
    assert _is_within(STATIC_DIR / "js" / "api.js", STATIC_DIR) is True
    assert _is_within(STATIC_DIR, STATIC_DIR) is True


def test_is_within_rejects_paths_outside_the_directory(tmp_path):
    assert _is_within(STATIC_DIR.parent, STATIC_DIR) is False
    assert _is_within(tmp_path / "elsewhere" / "x.js", STATIC_DIR) is False


# ------------------------------------------------------------------- routing


def test_index_is_served_from_the_root():
    handler = make_handler("/")
    handler.do_GET()
    status, payload = response(handler)
    assert status == 200
    assert "<html" in payload.lower()


def test_static_serves_files_inside_the_static_dir():
    handler = make_handler("/static/js/api.js")
    handler.do_GET()
    status, payload = response(handler)
    assert status == 200
    assert "async function api(" in payload


def test_static_blocks_path_traversal():
    handler = make_handler("/static/../launcher.py")
    handler.do_GET()
    status, _ = response(handler)
    assert status == 403


def test_history_api_rejects_non_integer_pagination():
    handler = make_handler("/api/history?page=abc&per_page=15")
    handler.do_GET()
    status, payload = response(handler)
    assert status == 400
    assert "must be integers" in payload["error"]


def test_audit_api_rejects_non_integer_pagination():
    handler = make_handler("/api/audit?page=abc")
    handler.do_GET()
    status, payload = response(handler)
    assert status == 400
    assert "must be integers" in payload["error"]


def test_run_profile_handler_no_longer_takes_send_error():
    import inspect

    import launcher.api.runs as runs

    params = list(inspect.signature(runs.handle_run_profile).parameters)
    assert params == ["data"], f"handle_run_profile params: {params}"


# ------------------------------------------------------- main-thread dialog loop


def test_main_serves_http_on_a_worker_thread_and_pumps_dialogs():
    src = (Path(__file__).resolve().parent.parent / "launcher" / "server.py").read_text()
    assert re.search(r"threading\.Thread\(\s*target=server\.serve_forever", src), \
        "serve_forever must run off the main thread so dialogs can be serviced"
    assert "filesystem.pump_dialogs" in src, \
        "the main thread must service queued Tk dialogs"
    assert "daemon=True" in src
