#!/usr/bin/env python3
"""Generate a screencast demo of the launcher UI with Playwright.

Boots the real server (via tests/e2e/server_main.py) on a free port with a
throwaway data directory, seeds it with tagged profiles/workflows/schedules
built from the example scripts, then drives the browser through a guided tour
while recording video.

The finished recording is written to demo/launcher_demo.webm by default:

    python3 scripts/dev/make_screencast.py
    python3 scripts/dev/make_screencast.py --output demo/tour.webm --headed

Requires the dev dependencies (pytest-playwright) and Chromium:
    pip install -r requirements-dev.txt
    python3 -m playwright install chromium

This is a dev tool only -- the app itself never imports it.
"""

import argparse
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVER_MAIN = ROOT / "tests" / "e2e" / "server_main.py"
EXAMPLE_SCRIPTS = ROOT / "scripts" / "testing"


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _api(base_url, method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        base_url + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _seed(base_url):
    """Seed the demo server with profiles, a workflow, and a schedule.

    Profiles and workflows carry `tags` arrays referencing the global tag
    list that _seed_browser_tags injects into the browser's localStorage.
    """
    def script(name):
        return str(EXAMPLE_SCRIPTS / name)

    report = _api(base_url, "POST", "/api/profiles", {
        "id": "profile_demo_report",
        "name": "Daily Report",
        "script_path": script("generate_report.py"),
        "args": [],
        "tags": ["tag_reports"],
        "custom_args": [
            {"name": "--format", "label": "Format", "type": "text",
             "default": "pdf", "value": "pdf"},
        ],
    })
    pipeline = _api(base_url, "POST", "/api/profiles", {
        "id": "profile_demo_pipeline",
        "name": "Data Pipeline",
        "script_path": script("process_data.py"),
        "args": [],
        "tags": ["tag_data", "tag_reports"],
        "custom_args": [
            {"name": "--input", "label": "Input file", "type": "text",
             "default": "data.csv", "value": "data.csv"},
            {"name": "--clean", "label": "Clean first", "type": "checkbox",
             "default": "", "value": "true"},
        ],
    })
    fetch = _api(base_url, "POST", "/api/profiles", {
        "id": "profile_demo_fetch",
        "name": "Fetch Data",
        "script_path": script("fetch_data.py"),
        "args": [],
        "tags": ["tag_data"],
        "custom_args": [
            {"name": "--rows", "label": "Rows", "type": "text",
             "default": "50", "value": "50"},
        ],
    })
    backup = _api(base_url, "POST", "/api/profiles", {
        "id": "profile_demo_backup",
        "name": "Nightly Backup",
        "script_path": script("backup.py"),
        "args": ["--compress"],
        "tags": ["tag_ops"],
        "custom_args": [],
    })
    email = _api(base_url, "POST", "/api/profiles", {
        "id": "profile_demo_email",
        "name": "Email Report",
        "script_path": script("send_email.py"),
        "args": [],
        "tags": ["tag_reports"],
        "custom_args": [
            {"name": "--to", "label": "Recipient", "type": "text",
             "default": "team@example.com", "value": "team@example.com"},
        ],
    })

    _api(base_url, "POST", "/api/workflows", {
        "id": "workflow_demo_nightly",
        "name": "Nightly Pipeline",
        "steps": [
            {"type": "sequential", "profile_id": report["id"]},
            {"type": "parallel", "profiles": [
                {"profile_id": fetch["id"]},
                {"profile_id": backup["id"]},
            ]},
            {"type": "sequential", "profile_id": email["id"]},
        ],
        "extra_args": [],
        "continue_on_error": False,
        "tags": ["tag_ops", "tag_data"],
    })

    _api(base_url, "POST", "/api/schedules", {
        "name": "Every 6 hours",
        "target_type": "profile",
        "target_id": backup["id"],
        "cron": "0 */6 * * *",
        "enabled": True,
    })
    _api(base_url, "POST", "/api/schedules", {
        "name": "Daily at 09:00",
        "target_type": "workflow",
        "target_id": "workflow_demo_nightly",
        "cron": "0 9 * * *",
        "enabled": True,
    })

    # Pre-run a couple of profiles so History and Audit have realistic rows.
    _api(base_url, "POST", "/api/run/profile", {"profile_id": report["id"]})
    _api(base_url, "POST", "/api/run/profile", {"profile_id": backup["id"]})
    time.sleep(2.5)

    return {
        "report": report,
        "pipeline": pipeline,
        "fetch": fetch,
        "backup": backup,
        "email": email,
    }


def _seed_browser_tags(context):
    """Create the global tag list in the browser's localStorage.

    Tags live client-side (the server only stores the tag ids on items), so
    the demo injects them before any page script runs. The ids match the
    `tags` arrays used in _seed.
    """
    context.add_init_script(
        "localStorage.setItem('tags', JSON.stringify(["
        "{ id: 'tag_reports', name: 'Reports' },"
        "{ id: 'tag_data', name: 'Data' },"
        "{ id: 'tag_ops', name: 'Ops' },"
        "]));"
    )


def _attach_gif_sampler(page, shot_dir, interval_ms=300):
    """Sample periodic screenshots during the tour by slicing its waits.

    The tour drives everything through wait_for_timeout, so wrapping it (same
    thread -- Playwright's sync API cannot be touched from a worker thread)
    turns every pause into a series of shorter waits with a screenshot after
    each. Frame durations reflect real elapsed time so the GIF pacing matches
    the tour.
    """
    shot_dir.mkdir(parents=True, exist_ok=True)
    state = {"n": 0}
    orig_wait = page.wait_for_timeout

    def sampled_wait(ms):
        remaining = ms
        while remaining > 0:
            step = min(interval_ms, remaining)
            orig_wait(step)
            remaining -= step
            state["n"] += 1
            page.screenshot(path=str(shot_dir / f"f{state['n']:04d}.png"))

    page.wait_for_timeout = sampled_wait
    return state


def _build_gif(shot_dir, gif_path, width):
    """Assemble the sampled PNG frames into an optimized animated GIF."""
    try:
        from PIL import Image
    except ImportError:
        sys.exit(
            "Pillow is required for --gif - run: pip install -r requirements-dev.txt"
        )

    frames = sorted(shot_dir.glob("f*.png"))
    if not frames:
        raise RuntimeError("no frames were captured for the GIF")
    scale = width / Image.open(frames[0]).width
    size = (width, round(Image.open(frames[0]).height * scale))

    durations = []
    total = 0.0
    for i, frame in enumerate(frames):
        real = frame.stat().st_mtime - (frames[i - 1].stat().st_mtime if i else frame.stat().st_mtime)
        durations.append(max(40, round((real if i else 0.3) * 1000)))
        total += durations[-1]

    images = []
    for frame in frames:
        img = Image.open(frame).convert("RGB").resize(size, Image.LANCZOS)
        images.append(img.quantize(colors=256, method=Image.MEDIANCUT, dither=Image.Dither.NONE))

    images[0].save(
        gif_path,
        save_all=True,
        append_images=images[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    return len(images), total / 1000


def _tour(page, base_url, pause):
    """Drive the browser through the demo tour while the video records."""

    def nav(name):
        page.get_by_role("button", name=name).first.click()

    # 1. Profiles panel with seeded cards.
    page.goto(base_url)
    page.get_by_role("heading", name="Profiles", exact=True).wait_for()
    page.wait_for_timeout(pause * 1.5)

    # 2. Run the Daily Report profile and watch live output stream in.
    card = page.locator("#panel-profiles h3", has_text="Daily Report").locator(
        "xpath=ancestor::div[contains(@class, 'group')][1]")
    card.get_by_role("button", name="Run").click()
    modal = page.locator("div.fixed.inset-0.z-50")
    modal.get_by_role("heading", name="Profile Run").wait_for()
    page.wait_for_timeout(pause * 2)
    modal.get_by_role("button", name="Close").click()
    modal.wait_for(state="hidden")
    page.wait_for_timeout(pause)

    # 3. Scroll the profile-cards column to reveal the remaining cards.
    page.mouse.move(430, 400)
    page.mouse.wheel(0, 400)
    page.wait_for_timeout(pause)
    page.mouse.wheel(0, 300)
    page.wait_for_timeout(pause)
    page.mouse.wheel(0, -700)
    page.wait_for_timeout(pause)

    # 4. Tags: filter the list down to one tag, then back to all.
    page.get_by_role("button", name="Data 2").click()
    page.get_by_role("heading", name="Profiles", exact=True).wait_for()
    page.wait_for_timeout(pause * 1.5)
    page.get_by_role("button", name="Data 2").click()
    page.wait_for_timeout(pause)

    # 5. Assign an extra tag while editing: Fetch Data also joins Reports.
    fcard = page.locator("#panel-profiles h3", has_text="Fetch Data").locator(
        "xpath=ancestor::div[contains(@class, 'group')][1]")
    fcard.get_by_role("button", name="Edit").click()
    modal.get_by_role("heading", name="Edit Profile").wait_for()
    page.wait_for_timeout(pause)
    modal.get_by_role("button", name="Reports", exact=True).click()
    page.wait_for_timeout(pause)
    modal.get_by_role("button", name="Save Profile").click()
    modal.wait_for(state="hidden")
    page.wait_for_timeout(pause)

    # 6. Tag manager: one global list shared by profiles and workflows.
    page.get_by_role("button", name="Tags").first.click()
    modal.get_by_role("heading", name="Manage Tags").wait_for()
    page.wait_for_timeout(pause * 1.5)
    modal.get_by_role("button", name="Done").click()
    modal.wait_for(state="hidden")
    page.wait_for_timeout(pause)

    # 7. Workflows panel; run the chained workflow (same global tags apply).
    nav("Workflows")
    page.get_by_role("heading", name="Workflows", exact=True).wait_for()
    page.wait_for_timeout(pause)
    wcard = page.locator("#panel-workflows h3", has_text="Nightly Pipeline").locator(
        "xpath=ancestor::div[contains(@class, 'group')][1]")
    wcard.get_by_role("button", name="Run").click()
    modal.get_by_role("heading", name="Workflow Run").wait_for()
    modal.get_by_text("Workflow completed").wait_for(timeout=20000)
    page.wait_for_timeout(pause * 2)
    modal.get_by_role("button", name="Close").click()
    modal.wait_for(state="hidden")
    page.wait_for_timeout(pause)

    # 8. Schedules panel and the live cron preview in the editor.
    nav("Schedules")
    page.get_by_role("heading", name="Schedules", exact=True).wait_for()
    page.wait_for_timeout(pause)
    nav("New Schedule")
    modal.get_by_role("heading", name="New Schedule").wait_for()
    page.wait_for_timeout(pause)
    number_input = modal.locator("input[type='number']").first
    number_input.fill("15")
    page.wait_for_timeout(pause)
    number_input.fill("45")
    page.wait_for_timeout(pause)
    modal.get_by_role("button", name="Cancel").click()
    modal.wait_for(state="hidden")
    page.wait_for_timeout(pause)

    # 9. Audit trail.
    nav("Audit")
    page.get_by_role("heading", name="Audit", exact=True).wait_for()
    page.wait_for_timeout(pause * 1.5)

    # 10. Server logs with live tailing.
    nav("Logs")
    page.get_by_role("heading", name="Server Logs", exact=True).wait_for()
    page.wait_for_timeout(pause * 2)

    # 11. Theme toggle: light, then back to dark.
    page.get_by_role("button", name="Light Mode").click()
    page.wait_for_timeout(pause)
    page.get_by_role("button", name="Dark Mode").click()
    page.wait_for_timeout(pause)

    # 12. Back to Profiles for the closing shot.
    nav("Profiles")
    page.get_by_role("heading", name="Profiles", exact=True).wait_for()
    page.wait_for_timeout(pause * 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", default="demo/launcher_demo.webm",
                        help="Where to write the .webm video")
    parser.add_argument("--gif", metavar="PATH", default=None,
                        help="Also write an animated GIF (e.g. demo/launcher_demo.gif)")
    parser.add_argument("--gif-width", type=int, default=800,
                        help="Width of the generated GIF (default: 800)")
    parser.add_argument("--headed", action="store_true",
                        help="Watch the browser while recording")
    parser.add_argument("--pause", type=float, default=1.0,
                        help="Seconds to linger on each step")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Playwright is not installed - run: pip install -r requirements-dev.txt")

    output_path = (ROOT / args.output).resolve() if not Path(args.output).is_absolute() \
        else Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data_dir = Path(tempfile.mkdtemp(prefix="launcher-demo-"))
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    log_path = data_dir / "server.log"

    proc = subprocess.Popen(
        [sys.executable, str(SERVER_MAIN), str(data_dir), str(port)],
        cwd=str(ROOT),
        stdout=log_path.open("w"),
        stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.time() + 15
        while True:
            try:
                _api(base_url, "GET", "/api/profiles")
                break
            except (urllib.error.URLError, ConnectionError, OSError):
                if time.time() > deadline:
                    raise RuntimeError(f"demo server did not start:\n{log_path.read_text()}")
                time.sleep(0.1)

        seeded = _seed(base_url)
        print(f"Seeded {len(seeded)} profiles on {base_url}")

        video_dir = data_dir / "video"
        video_dir.mkdir()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not args.headed)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                record_video_dir=str(video_dir),
                record_video_size={"width": 1280, "height": 800},
            )
            _seed_browser_tags(context)
            page = context.new_page()
            sampler = None
            if args.gif:
                sampler = _attach_gif_sampler(
                    page, data_dir / "gif_frames", interval_ms=300)
            try:
                _tour(page, base_url, int(args.pause * 1000))
            finally:
                video = page.video
                context.close()
                video_file = video.path()
                browser.close()
            shutil.move(str(video_file), str(output_path))
            print(f"Screencast written to {output_path}")
            if args.gif:
                gif_path = Path(args.gif)
                if not gif_path.is_absolute():
                    gif_path = ROOT / gif_path
                gif_path.parent.mkdir(parents=True, exist_ok=True)
                n_frames, seconds = _build_gif(
                    data_dir / "gif_frames", str(gif_path), args.gif_width)
                print(f"Animated GIF written to {gif_path} "
                      f"({n_frames} frames, {seconds:.1f}s)")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        shutil.rmtree(data_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
