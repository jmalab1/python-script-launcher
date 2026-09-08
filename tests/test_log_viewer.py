import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPONENTS = ROOT / "static" / "js" / "components"
JS = ROOT / "static" / "js"


def read(path):
    return path.read_text()


def test_logs_panel_is_registered_as_a_valid_panel():
    state = read(JS / "state.js")
    assert re.search(r"export const PANELS = \[[^\]]*'logs'", state), "PANELS must include 'logs'"
    for signal in ("logData", "logOffset"):
        assert f"export const {signal}" in state, f"missing {signal} signal"


def test_sidebar_offers_logs_in_desktop_nav_and_mobile_drawer():
    src = read(COMPONENTS / "Sidebar.js")
    assert src.count("showPanel('logs')") == 3, "desktop nav, mobile drawer, and mobile header must all link to logs"
    assert src.count("Logs\n                </button>") == 2, "desktop nav and drawer need a Logs button"
    assert ">Logs</button>" in src, "mobile header quick-switch needs a Logs button"


def test_app_renders_logs_panel_and_polls_for_new_lines():
    src = read(JS / "app.js")
    assert "import { LogViewer } from './components/LogViewer.js'" in src
    assert "currentPanel.value === 'logs'" in src
    assert "loadLogs()" in src
    assert "setInterval(pollLogs, 2000)" in src


def test_logs_api_calls_hit_the_log_endpoints():
    src = read(JS / "api.js")
    assert "api('GET', '/api/logs?lines='" in src, "initial load must tail the log"
    assert "api('GET', '/api/logs?after=' + logOffset.value)" in src, "polling must send the resume offset"
    assert "data.reset" in src, "a reset response must replace, not append"
    assert ".slice(-" in src, "the client buffer must be capped"


def test_log_viewer_renders_lines_verbatim_and_filters():
    src = read(COMPONENTS / "LogViewer.js")
    assert "esc(" not in src, "log lines are Preact text nodes; esc() would display &quot; literally"
    assert "${line ||" in src, "log lines must render as raw text so quotes and arrows display verbatim"
    assert "scrollHeight" in src, "following must scroll to the bottom"
    assert "onScroll" in src and "setFollow" in src, "scrolling away from the bottom must pause follow"
    assert "levelFilter" in src, "must offer a level filter"
    assert "search" in src, "must offer a text filter"
    assert "whitespace-pre-wrap" in src, "long lines must wrap"


def test_esc_keeps_double_quotes_readable():
    src = read(JS / "utils.js")
    assert "&quot;" not in src, "quotes must not be turned into &quot; entities"


def test_server_route_serves_the_logs_api():
    src = (ROOT / "launcher" / "server.py").read_text()
    assert 'path == "/api/logs"' in src
    assert "logs.handle_list" in src


def test_server_mirrors_logs_to_a_rotating_data_server_log():
    src = (ROOT / "launcher" / "server.py").read_text()
    assert "def setup_file_logging()" in src
    assert "setup_file_logging()" in src.split("def main()")[1], "main() must install the file handler"
    assert "RotatingFileHandler" in src, "the log file must be rotated"
    assert "TimestampedRotatingFileHandler" in src, "rotated backups must be datetime-stamped"
    assert "getFilesToDelete" in src, "timestamped backups must be pruned explicitly"
    assert "addHandler(handler)" in src
