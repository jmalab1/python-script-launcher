import re
from pathlib import Path

COMPONENTS = Path(__file__).resolve().parent.parent / "static" / "js" / "components"


def test_profile_card_checkbox_restores_checked_state_from_stored_value():
    src = (COMPONENTS / "ProfileCard.js").read_text()
    assert "checked=${c.value === 'true'}" in src, \
        "checkbox must restore its checked state from the stored value"


def test_profile_card_checkbox_value_is_saved_as_string():
    src = (COMPONENTS / "ProfileCard.js").read_text()
    assert "ca.type === 'checkbox' ? (el.checked ? 'true' : 'false') : el.value" in src, \
        "handleArgChange must convert checkbox state to 'true'/'false' string"


def test_profile_card_checkbox_reads_value_on_run():
    src = (COMPONENTS / "ProfileCard.js").read_text()
    assert "ca.type === 'checkbox' ? (el.checked ? 'true' : 'false') : el.value" in src, \
        "checkbox value must be read from el.checked during run"
