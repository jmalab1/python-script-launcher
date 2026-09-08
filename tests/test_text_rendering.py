"""Guard against HTML-escaping preact text children.

Preact renders string children as DOM text nodes, which the browser shows
verbatim and which cannot inject HTML. Wrapping values in an esc() helper
before interpolation therefore double-escapes them: a profile named
"A & B" would display as "A &amp; B" and script output like "a < b" as
"a &lt; b". These tests keep every component on raw interpolation.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "static" / "js"


def js_sources():
    return [p for p in sorted(JS.rglob("*.js")) if "vendor" not in p.parts]


def test_no_component_html_escapes_its_output():
    offenders = [str(p.relative_to(JS)) for p in js_sources() if "esc(" in p.read_text()]
    assert not offenders, (
        f"{offenders} still call esc(): preact text nodes are already safe, "
        "and esc() would display &amp;/&lt; literally"
    )


def test_utils_js_no_longer_defines_an_esc_helper():
    src = (JS / "utils.js").read_text()
    assert "export function esc(" not in src, (
        "utils.js must not offer an esc() helper that invites double-escaping"
    )
    assert "preact renders string children as text nodes" in src, \
        "keep the comment that explains why values are interpolated raw"


def test_run_modal_renders_script_output_verbatim():
    src = (JS / "components" / "RunModal.js").read_text()
    # Every output line, colored or not, goes through raw interpolation.
    assert "return cls ? html`<div class=${cls}>${s}</div>` : s;" in src, \
        "script output lines must be interpolated raw so < and & display as typed"


def test_names_and_paths_render_without_escaping():
    for component, snippet in (
        ("ProfileCard.js", "${p.name}"),
        ("WorkflowCard.js", "${w.name}"),
        ("SchedulesList.js", "${s.name || s.target_name || 'Schedule'}"),
        ("HistoryTable.js", "${e.name}"),
        ("AuditTable.js", "${e.name}"),
    ):
        src = (JS / "components" / component).read_text()
        assert snippet in src, f"{component} must render the name as raw text"
