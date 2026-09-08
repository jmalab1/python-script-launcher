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


# --- Native browser dialogs ---

def test_no_component_uses_native_alert_or_confirm():
    """Native alert()/confirm() block the whole page and can't be styled.

    Modals must surface errors inline (ErrorBanner) and route yes/no
    choices through the ConfirmModal component instead.
    """
    offenders = []
    for path in sorted(JS.rglob("*.js")):
        if "vendor" in path.parts:
            continue
        if re.search(r"\b(alert|confirm)\(", path.read_text()):
            offenders.append(path.relative_to(JS).as_posix())
    assert not offenders, f"native alert()/confirm() found in: {offenders}"


def test_error_banner_exists_and_is_inline():
    src = read(COMPONENTS / "ErrorBanner.js")
    assert "export function ErrorBanner(" in src, "ErrorBanner is not exported"
    assert 'role="alert"' in src, "the banner should be announced to screen readers"


def test_modals_surface_errors_inline_via_error_banner():
    for name in ("ProfileModal.js", "WorkflowModal.js", "ScheduleModal.js", "RunModal.js", "TagManager.js"):
        src = read(COMPONENTS / name)
        assert "<${ErrorBanner}" in src, f"{name} does not render ErrorBanner"
        assert "setError(" in src, f"{name} has no inline error state"
