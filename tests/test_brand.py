from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(path):
    return Path(path).read_text()


def test_browser_title_is_tiller():
    src = read(ROOT / "index.html")
    assert "<title>Tiller</title>" in src
    assert "Python Web Launcher" not in src


def test_sidebar_brand_reads_tiller_everywhere():
    src = read(ROOT / "static" / "js" / "components" / "Sidebar.js")
    assert src.count(">Tiller</span>") == 3, "desktop nav, mobile header, and mobile drawer all show the brand"
    assert ">Launcher</span>" not in src


def test_logs_panel_copy_names_tiller():
    src = read(ROOT / "static" / "js" / "app.js")
    assert "Tiller's own log file" in src


def test_server_startup_log_names_tiller():
    src = read(ROOT / "launcher" / "server.py")
    assert 'log.info("Tiller running at http://127.0.0.1:%s", PORT)' in src
    assert "another instance of Tiller already running?" in src


def test_entry_point_docstring_names_tiller():
    src = read(ROOT / "launcher.py")
    assert '"""Tiller - Run Python scripts via a local web UI."""' in src


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
