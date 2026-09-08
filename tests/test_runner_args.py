from launcher.runner import DEFAULT_DATE_FORMAT, build_custom_args, format_date_value


def test_format_date_value_defaults_to_iso():
    assert DEFAULT_DATE_FORMAT == "%Y-%m-%d"
    assert format_date_value("2026-09-07") == "2026-09-07"


def test_format_date_value_applies_custom_strftime_format():
    assert format_date_value("2026-09-07", "%d/%m/%Y") == "07/09/2026"
    assert format_date_value("2026-09-07", "%d.%m.%y") == "07.09.26"
    assert format_date_value("2026-09-07", "%B %d, %Y") == "September 07, 2026"


def test_format_date_value_falls_back_on_unparseable_input():
    assert format_date_value("not-a-date", "%d/%m/%Y") == "not-a-date"
    assert format_date_value("2026-13-40", "%d/%m/%Y") == "2026-13-40"
    assert format_date_value("", "%d/%m/%Y") == ""


def test_build_custom_args_text_checkbox_and_empty_values():
    cas = [
        {"name": "--flag", "type": "text", "value": "v1"},
        {"name": "--cb", "type": "checkbox", "value": "true"},
        {"name": "--off", "type": "checkbox", "value": "false"},
        {"name": "--skip", "type": "text", "value": ""},
        {"name": "", "type": "text", "value": "ignored"},
    ]
    assert build_custom_args(cas) == ["--flag", "v1", "--cb"]


def test_build_custom_args_overrides_take_precedence_over_stored_value():
    cas = [{"name": "--flag", "type": "text", "value": "v1"}, {"name": "--cb", "type": "checkbox", "value": "false"}]
    assert build_custom_args(cas, {"--flag": "v2", "--cb": "true"}) == ["--flag", "v2", "--cb"]


def test_build_custom_args_falls_back_to_default_when_no_value():
    cas = [{"name": "--d", "type": "date", "default": "2026-01-02", "format": "%Y"}]
    assert build_custom_args(cas) == ["--d", "2026"]


def test_build_custom_args_date_uses_default_and_configured_formats():
    cas = [
        {"name": "--iso", "type": "date", "value": "2026-09-07"},
        {"name": "--eu", "type": "date", "value": "2026-09-07", "format": "%d/%m/%Y"},
    ]
    assert build_custom_args(cas) == ["--iso", "2026-09-07", "--eu", "07/09/2026"]


def test_build_custom_args_date_override_is_formatted_too():
    cas = [{"name": "--date", "type": "date", "value": "2026-09-07", "format": "%d-%m-%Y"}]
    assert build_custom_args(cas, {"--date": "2026-01-02"}) == ["--date", "02-01-2026"]


def test_build_custom_args_date_invalid_value_passes_through_untouched():
    cas = [{"name": "--d", "type": "date", "value": "junk", "format": "%d/%m/%Y"}]
    assert build_custom_args(cas) == ["--d", "junk"]


def test_build_custom_args_enum_only_passed_when_selected():
    cas = [
        {"name": "--level", "type": "enum", "options": "debug, info, warn", "value": "warn"},
        {"name": "--unset", "type": "enum", "options": "a,b", "value": ""},
        {"name": "--defaulted", "type": "enum", "options": "x,y", "default": "y"},
    ]
    assert build_custom_args(cas) == ["--level", "warn", "--defaulted", "y"]


def test_build_custom_args_enum_empty_override_is_omitted():
    cas = [{"name": "--level", "type": "enum", "options": "debug,info,warn", "value": "warn"}]
    assert build_custom_args(cas, {"--level": ""}) == []
