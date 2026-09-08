"""Source-inspection tests for the screencast demo generator.

scripts/make_screencast.py is a dev tool (like the e2e tests) rather than app
code, so these tests inspect its source instead of running the full recording,
which would be slow and need a display-free browser launch on every test run.
They pin down the properties that keep the demo safe and complete: isolated
data dir, real server boot, video recording, and full panel coverage.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "make_screencast.py"


def _source():
    return SCRIPT.read_text()


def _tree():
    return ast.parse(_source())


def test_screencast_script_exists_and_parses():
    assert SCRIPT.exists(), "scripts/make_screencast.py is missing"
    _tree()  # raises SyntaxError on malformed source


def test_screencast_never_touches_the_real_data_store():
    src = _source()
    assert "tempfile.mkdtemp" in src, "demo must use a throwaway data directory"
    assert "launcher.config" not in src, "demo must not patch the real config"
    assert 'ROOT / "data"' not in src, "demo must not reference the real data dir"


def test_screencast_boots_the_real_server_via_the_e2e_entrypoint():
    src = _source()
    assert "server_main.py" in src, "demo must boot the real stdlib server"
    assert 'tests" / "e2e' in src, "demo must reuse the e2e server entrypoint"


def test_screencast_seeds_data_through_the_http_api():
    src = _source()
    for endpoint in ("/api/profiles", "/api/workflows", "/api/schedules"):
        assert f'"{endpoint}"' in src, f"demo seeding must POST {endpoint}"


def test_screencast_records_a_video():
    src = _source()
    assert "record_video_dir=" in src, "demo must enable video recording"
    assert "record_video_size=" in src, "demo must pin the video resolution"
    assert ".webm" in src, "demo must write a .webm file"


def test_screencast_tours_every_panel_and_the_theme_toggle():
    src = _source()
    for panel in ("Profiles", "Workflows", "Schedules", "Audit", "Logs"):
        assert f'nav("{panel}")' in src, f"tour must visit the {panel} panel"
    assert '"Light Mode"' in src and '"Dark Mode"' in src, \
        "tour must demonstrate the theme toggle"


def test_screencast_is_wired_into_the_makefile():
    makefile = (ROOT / "Makefile").read_text()
    assert "demo:" in makefile, "Makefile has no demo target"
    assert "make_screencast.py" in makefile, "demo target does not run the generator"


def test_gif_mode_is_optional_and_lazy():
    src = _source()
    assert '"--gif"' in src, "generator must expose an --gif option"
    tree = _tree()
    build_gif = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_build_gif"
    )
    inner = ast.get_source_segment(src, build_gif)
    assert "from PIL import Image" in inner, "Pillow import must be lazy (inside _build_gif)"
    assert "Pillow is required" in inner, "missing Pillow must fail with an install hint"


def test_gif_frames_are_sampled_on_the_tour_thread():
    src = _source()
    tree = _tree()
    sampler = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_attach_gif_sampler"
    )
    inner = ast.get_source_segment(src, sampler)
    assert "page.screenshot" in inner, "sampler must capture frames"
    assert "wait_for_timeout" in inner, "sampler must hook the tour's waits"


def test_pillow_is_tracked_as_a_dev_dependency():
    dev = (ROOT / "requirements-dev.txt").read_text()
    assert "pillow" in dev.lower(), "requirements-dev.txt must track Pillow for --gif"
