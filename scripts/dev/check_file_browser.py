#!/usr/bin/env python3
"""Quick manual check: the profile editor's Browse button opens the
in-app file explorer and can pick a script. Not part of the test suite
(it mirrors what a user would click through); run after UI changes:
    python3 scripts/dev/check_file_browser.py
"""

import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_DIR = ROOT / "scripts" / "testing"

def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    data_dir = Path(tempfile.mkdtemp(prefix="browser-check-"))
    port = free_port()
    env = {"LAUNCHER_DATA_DIR": str(data_dir), "PATH": "/usr/bin:/bin"}
    log = data_dir / "server.log"
    proc = subprocess.Popen(
        [str(ROOT / "dist" / "launchctl"), "-port", str(port), "-foreground"],
        stdout=log.open("w"), stderr=subprocess.STDOUT, env=env,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(50):
            try:
                urllib.request.urlopen(f"{base}/api/profiles", timeout=2)
                break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(base)

            page.get_by_role("button", name="New Profile").click()
            page.get_by_role("button", name="Browse").click()
            page.get_by_role("heading", name="Select Python Script").wait_for(timeout=5000)

            # Navigate Home -> dev -> python-web-launcher -> scripts ->
            # testing, waiting for each listing to load (the cwd badge
            # updates when the new directory arrives).
            def descend(name):
                cwd_before = page.locator("span.font-mono").first.inner_text()
                page.locator("li button", has_text=name).first.dblclick()
                locator = page.locator("span.font-mono", has_text=name.rstrip("/"))
                for attempt in range(50):  # up to ~5s
                    try:
                        if page.locator("span.font-mono").first.inner_text() != cwd_before:
                            break
                    except TypeError:
                        pass
                    time.sleep(0.1)

            descend("dev")
            descend("python-web-launcher")
            descend("scripts")
            descend("testing")
            page.locator("li button", has_text="test_script.py").first.wait_for(timeout=5000)
            page.locator("li button", has_text="test_script.py").first.click()
            page.wait_for_timeout(200)
            # One click selects the row; Use the Select button.
            btn = page.get_by_role("button", name="Select", exact=True)
            btn.wait_for(timeout=3000)
            disabled = btn.is_disabled()
            assert not disabled, "Select button should be enabled after picking a script"
            btn.click()

            # The readonly "No file selected" field shows the picked path.
            got = page.locator('input[placeholder="No file selected"]').first.input_value()
            assert str(SCRIPT_DIR / "test_script.py") in str(got), f"path not filled: {got!r}"


            browser.close()
        print("file picker OK: browsed to scripts/testing and selected test_script.py")
    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
