from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(path):
    return Path(path).read_text()


def test_browser_title_is_launch_control():
    src = read(ROOT / "index.html")
    assert "<title>Launch Control</title>" in src
    assert "Python Web Launcher" not in src


def test_sidebar_brand_reads_launch_control_everywhere():
    src = read(ROOT / "static" / "js" / "components" / "Sidebar.js")
    assert src.count(">Launch Control</span>") == 3, "desktop nav, mobile header, and mobile drawer all show the brand"
    assert ">Launcher</span>" not in src


def test_logs_panel_copy_names_launch_control():
    src = read(ROOT / "static" / "js" / "app.js")
    assert "Launch Control's own log file" in src


def test_server_startup_log_names_launch_control():
    src = read(ROOT / "launcher" / "server.py")
    assert 'log.info("Launch Control running at http://127.0.0.1:%s", PORT)' in src
    assert "another instance of Launch Control already running?" in src


def test_entry_point_docstring_names_launch_control():
    src = read(ROOT / "launcher.py")
    assert '"""Launch Control - Run Python scripts via a local web UI."""' in src


def test_no_stale_brand_string_in_brand_files():
    paths = [
        ROOT / "index.html",
        ROOT / "launcher.py",
        ROOT / "launcher" / "server.py",
        ROOT / "static" / "js" / "app.js",
        ROOT / "static" / "js" / "components" / "Sidebar.js",
    ]
    for path in paths:
        assert "Python Web Launcher" not in path.read_text(), f"stale brand string in {path.name}"


def test_theme_boot_script_defaults_to_dark_without_dead_branches():
    """The old boot script forced dark even when the system preferred
    light, and its matchMedia branch could never change the outcome."""
    src = read(ROOT / "index.html")
    assert "matchMedia" not in src, "the dead system-preference branch should be gone"
    assert "t==='light'){document.documentElement.classList.remove('dark');}" in src, \
        "a stored light theme must remove the dark class"
    assert "else{document.documentElement.classList.add('dark');}" in src, \
        "anything else stays dark, matching the app default"
