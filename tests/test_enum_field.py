import re
from pathlib import Path

COMPONENTS = Path(__file__).resolve().parent.parent / "static" / "js" / "components"


def test_profile_modal_offers_enum_type_with_options_input():
    src = (COMPONENTS / "ProfileModal.js").read_text()
    assert "<option value=\"enum\" selected=${ca.type === 'enum'}>Enum</option>" in src, \
        "type select has no Enum option"
    assert "updateCustomArg(i, 'options'" in src, "no options input for enum fields"
    assert 'placeholder="Options (comma-separated)"' in src, "options input lacks a placeholder"


def test_profile_modal_persists_options_for_enum_fields_on_save():
    src = (COMPONENTS / "ProfileModal.js").read_text()
    assert "if (built.type === 'enum') built.options = (ca.options || '').trim();" in src, \
        "handleSave drops the enum options"


def test_profile_modal_explains_enum_and_empty_selection_rule():
    src = (COMPONENTS / "ProfileModal.js").read_text()
    assert "customArgs.some(ca => ca.type === 'enum')" in src, \
        "instructions are not gated on the presence of an enum field"
    assert "comma-separated choices for the dropdown" in src, "instructions do not explain comma separation"
    assert "only passed to the script when a value is selected" in src, \
        "instructions do not mention the empty-selection rule"


def test_profile_card_renders_enum_fields_as_dropdowns_with_empty_default():
    src = (COMPONENTS / "ProfileCard.js").read_text()
    assert "if (c.type === 'enum') {" in src, "card has no enum branch"
    assert re.search(r"<select id=\$\{`arg-\$\{p\.id\}-\$\{i\}`\}", src), \
        "enum field is not rendered as a select wired to the arg input id"
    assert "String(c.options || '').split(',')" in src, "enum options are not parsed from comma separation"
    assert "<option value=\"\" selected=${cur === ''}>-- select --</option>" in src, \
        "enum dropdown lacks an empty unselected option"


def test_workflow_modal_allows_enum_overrides_per_step():
    src = (COMPONENTS / "WorkflowModal.js").read_text()
    assert "if (ca.type === 'enum') {" in src, "workflow override fields have no enum branch"
    assert "String(ca.options || '').split(',')" in src, "enum options are not parsed from comma separation"
    assert re.search(r"<select onChange=\$\{e => onSet\(ca\.name, e\.target\.value\)\}", src), \
        "enum override does not write back through onSet"
