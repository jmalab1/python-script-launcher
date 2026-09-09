"""The script-exists cache used to pin a stale "missing" badge for the
whole browser session: once a path was checked, checkAllScripts skipped
it forever, so a script restored on disk stayed flagged until a reload."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "static" / "js" / "api.js"


def test_check_all_scripts_revalidates_every_path():
    src = JS.read_text()
    start = src.index("export async function checkAllScripts")
    end = src.index("export async function saveProfile")
    body = src[start:end]
    assert "scriptStatusCache.value[path] !== undefined" not in body, \
        "checkAllScripts must re-fetch every path so a stale 'missing' badge can heal"
    assert "/api/script_exists" in body, "checkAllScripts must query the server"


def test_single_check_script_exists_revalidates_too():
    src = JS.read_text()
    start = src.index("export async function checkScriptExists")
    end = src.index("export async function checkAllScripts")
    body = src[start:end]
    assert "scriptStatusCache.value[path] !== undefined" not in body, \
        "checkScriptExists must not serve a possibly stale cached value"
