import re
from pathlib import Path

COMPONENTS = Path(__file__).resolve().parent.parent / "static" / "js" / "components"


def test_profile_modal_offers_date_type_with_format_and_default_inputs():
    src = (COMPONENTS / "ProfileModal.js").read_text()
    assert "<option value=\"date\" selected=${ca.type === 'date'}>Date</option>" in src, \
        "type select has no Date option"
    assert re.search(r"type=\$\{ca\.type === 'date' \? 'date' : 'text'\}", src), \
        "default input is not a date picker for date fields"
    assert "updateCustomArg(i, 'format'" in src, "no format input for date fields"
    assert 'placeholder="Format (%Y-%m-%d)"' in src, "format input lacks a placeholder"


def test_profile_modal_persists_format_for_date_fields_on_save():
    src = (COMPONENTS / "ProfileModal.js").read_text()
    assert "if (built.type === 'date') built.format = (ca.format || '').trim();" in src, \
        "handleSave drops the date format"


def test_profile_modal_shows_date_format_instructions():
    src = (COMPONENTS / "ProfileModal.js").read_text()
    assert "customArgs.some(ca => ca.type === 'date')" in src, \
        "instructions are not gated on the presence of a date field"
    assert "strftime-style tokens" in src, "instructions do not explain the format syntax"
    for token in ("%Y", "%y", "%m", "%d", "%B", "%b"):
        assert f"<span class=\"font-mono\">{token}</span>" in src, f"token {token} is not documented"
    assert "%d/%m/%Y</span> → 07/09/2026" in src, "instructions lack a worked example"
    assert "Leave blank for <span class=\"font-mono\">%Y-%m-%d</span>" in src, \
        "instructions do not mention the default format"


def test_profile_card_renders_a_date_picker_for_date_fields():
    src = (COMPONENTS / "ProfileCard.js").read_text()
    assert "if (c.type === 'date') return html`" in src, "card has no date branch"
    assert re.search(r'<input type="date" id=\$\{`arg-\$\{p\.id\}-\$\{i\}`\}', src), \
        "date field is not rendered as a date picker wired to the arg input id"
    assert "value=${c.value || c.default || ''}" in src, "date input does not show stored value"


def test_workflow_modal_allows_date_overrides_per_step():
    src = (COMPONENTS / "WorkflowModal.js").read_text()
    assert "if (ca.type === 'date') {" in src, "workflow override fields have no date branch"
    assert re.search(r'<input type="date" value=\$\{eff\}\s*\n\s*onChange=\$\{e => onSet\(ca\.name, e\.target\.value\)\}', src), \
        "date override does not write back through onSet"
