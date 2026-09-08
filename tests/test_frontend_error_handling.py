"""Source-inspection tests for frontend error handling.

api() used to parse every response body with res.json() unchecked, so a
server error page (HTML) or an empty body turned into a SyntaxError and
every failure was silent; init() had no catch, leaving the app stuck on
"Loading..." forever.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "static" / "js"
COMPONENTS = JS / "components"


def read(path):
    return path.read_text()


def test_api_surfaces_non_json_error_bodies():
    src = read(JS / "api.js")
    assert re.search(
        r"try\s*\{\s*return await res\.json\(\);\s*\}\s*catch\s*\(err\)\s*\{[^}]*"
        r"throw new Error\(",
        src,
        re.DOTALL,
    ), "api() must throw when the body is not JSON (e.g. a server error page)"
    assert "res.status" in src, "the thrown error should include the HTTP status"


def test_app_init_retries_instead_of_hanging_on_loading_forever():
    src = read(JS / "app.js")
    assert re.search(
        r"async function init\(\)\s*\{[\s\S]*?catch \(err\)\s*\{[\s\S]*?setTimeout\(init,",
        src,
    ), "init() must retry after a transient failure instead of never finishing"
    assert "cancelled" in src, "init retries must stop once the component unmounts"


def test_periodic_polls_swallow_transient_errors_so_the_timer_survives():
    src = read(JS / "app.js")
    for loader in ("loadProfileHistory", "loadWorkflowHistory", "loadSchedules", "pollLogs"):
        assert re.search(rf"setInterval\(\(\) => {loader}\(\)\.catch\(\(\) => \{{\}}\)", src), \
            f"{loader} polling must guard against fetch failures"


def test_run_modal_keeps_polling_through_transient_errors():
    src = read(COMPONENTS / "RunModal.js")
    assert re.search(
        r"try\s*\{\s*data = await pollRun\(rid\);\s*\}\s*catch \(err\)\s*\{\s*"
        r"return; // transient fetch failure — keep polling",
        src,
    ), "a failed poll must not kill the polling timer"
    assert re.search(
        r"try\s*\{\s*hist = await fetchHistoryRun\(rid, rType\);\s*\}\s*catch \(err\)\s*\{[^}]*"
        r"setOutput\(\['Could not load run data\.'\]\);",
        src,
        re.DOTALL,
    ), "history fetch failures must render an error message, not throw unhandled"
