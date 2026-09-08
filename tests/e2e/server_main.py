#!/usr/bin/env python3
"""Standalone server entry point for the Playwright e2e tests.

Boots the real launcher web server against an isolated data directory and
port (both passed as argv) so e2e tests never touch the project's real
`data/` store. `launcher.config` is patched *before* importing any other
launcher module, so every module-level path constant (storage DB, history,
audit, ...) picks up the test values.

Deliberately bypasses server.main(): it auto-opens a browser on Windows and
prompts interactively on port conflicts, neither of which a test run wants.
Instead the same request handler is served directly.
"""
import http.server
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    data_dir = Path(sys.argv[1])
    port = int(sys.argv[2])

    sys.path.insert(0, str(ROOT))
    import launcher.config as config

    config.DATA_DIR = data_dir
    config.DB_PATH = data_dir / "launcher.db"
    config.PORT = port

    from launcher.server import LauncherHandler, setup_file_logging

    setup_file_logging()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), LauncherHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
