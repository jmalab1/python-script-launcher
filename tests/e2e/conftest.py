"""Fixtures for the Playwright end-to-end tests.

The session-scoped `launcher_server` fixture boots the real server as a
subprocess (via server_main.py) on a free port with a throwaway data dir,
then seeds profiles and a workflow through the HTTP API. Browser fixtures
(`page`, fresh context per test) come from the pytest-playwright plugin.

The whole e2e directory is skipped gracefully when playwright/Chromium are
not installed, so `python3 -m pytest tests/` still passes everywhere.
"""

import json
import os
import shlex
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

E2E_DIR = Path(__file__).resolve().parent
ROOT = E2E_DIR.parents[1]

GREETING_SCRIPT = """\
import time

print("Hello, E2E!")
print("Starting work...")
time.sleep(1.0)
print("Done!")
"""

FAILING_SCRIPT = """\
import sys

print("about to fail")
print("boom: expected failure", file=sys.stderr)
sys.exit(3)
"""


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _api(base_url, method, path, payload=None):
    """Tiny JSON API client used to seed data and poll readiness."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        base_url + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


@pytest.fixture(scope="session", autouse=True)
def _require_chromium():
    """Skip the e2e suite when playwright or its Chromium build is missing."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        if not Path(p.chromium.executable_path).exists():
            pytest.skip(
                "Chromium is not installed - run: python3 -m playwright install chromium"
            )


@pytest.fixture(scope="session")
def launcher_server(tmp_path_factory):
    """Run the launcher server on a free port with an isolated data dir."""
    data_dir = tmp_path_factory.mktemp("e2e-data")
    scripts_dir = data_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "greet.py").write_text(GREETING_SCRIPT)
    (scripts_dir / "fail.py").write_text(FAILING_SCRIPT)

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    log_path = data_dir / "server.log"

    # LAUNCHER_SERVER_CMD lets the suite run a specific server command;
    # by default the compiled Go server is used (built on demand),
    # since data is passed through LAUNCHER_DATA_DIR.
    server_cmd = os.environ.get("LAUNCHER_SERVER_CMD")
    if server_cmd:
        argv = shlex.split(server_cmd) + [str(port)]
    else:
        binary = ROOT / "dist" / "launchctl"
        if not binary.exists():
            subprocess.run(["make", "go-build"], cwd=str(ROOT), check=True)
        argv = [str(binary), "-port", str(port), "-foreground"]
    server_env = {**os.environ, "LAUNCHER_DATA_DIR": str(data_dir)}

    with log_path.open("w") as log_file:
        proc = subprocess.Popen(
            argv,
            cwd=str(ROOT),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=server_env,
        )
        try:
            deadline = time.time() + 15
            while True:
                try:
                    _api(base_url, "GET", "/api/profiles")
                    break
                except (urllib.error.URLError, ConnectionError, OSError):
                    if time.time() > deadline:
                        log = log_path.read_text() if log_path.exists() else ""
                        raise RuntimeError(f"e2e server did not start.\n{log}")
                    time.sleep(0.1)

            greeting = _api(base_url, "POST", "/api/profiles", {
                "id": "profile_e2e_greet",
                "name": "E2E Greeting",
                "script_path": str(scripts_dir / "greet.py"),
                "args": [],
                "custom_args": [],
            })
            _api(base_url, "POST", "/api/profiles", {
                "id": "profile_e2e_fail",
                "name": "E2E Failing",
                "script_path": str(scripts_dir / "fail.py"),
                "args": [],
                "custom_args": [],
            })
            workflow = _api(base_url, "POST", "/api/workflows", {
                "id": "workflow_e2e",
                "name": "E2E Chain",
                "steps": [{"type": "sequential", "profile_id": greeting["id"]}],
                "extra_args": [],
                "continue_on_error": False,
            })
            yield {
                "base_url": base_url,
                "data_dir": data_dir,
                "greeting_profile": greeting,
                "workflow": workflow,
                "api": lambda method, path, payload=None: _api(base_url, method, path, payload),
            }
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
