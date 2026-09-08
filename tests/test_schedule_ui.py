import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPONENTS = ROOT / "static" / "js" / "components"
JS = ROOT / "static" / "js"


def test_schedule_modal_exists_and_is_exported():
    src = (COMPONENTS / "ScheduleModal.js").read_text()
    assert "export function ScheduleModal(" in src, "ScheduleModal is not exported"


def test_schedule_modal_offers_presets_and_custom_cron():
    src = (COMPONENTS / "ScheduleModal.js").read_text()
    assert "Presets" in src and "Custom cron" in src, "mode switch missing"
    assert "presetToCron" in src, "preset builder does not compile to cron"
    assert "*/${n} * * * *" in src, "every-N-minutes preset missing"
    assert "0 */${n} * * *" in src, "every-N-hours preset missing"
    assert "${m} ${h} */${n} * *" in src, "every-N-days preset missing"
    assert "${m} ${h} * * ${days}" in src, "weekly preset missing"
    assert "${m} ${h} ${clampN(monthlyDay, 'days')} * *" in src, "monthly preset missing"
    assert "UNIT_MAX" in src, "repeat unit bounds missing"
    assert 'type="number"' in src, "repeat count must be a free number input"
    assert 'max=${UNIT_MAX[repeatUnit]}' in src, "repeat number input is not clamped to the unit"


def test_schedule_modal_previews_upcoming_runs_and_validates_target():
    src = (COMPONENTS / "ScheduleModal.js").read_text()
    assert "previewCron(" in src, "cron preview not requested"
    assert "Next runs" in src, "preview list not rendered"
    assert "Pick a profile or workflow to schedule." in src, "missing target guard"
    assert "setError(res.error)" in src, "backend errors are not surfaced inline"


def test_schedules_list_shows_state_and_uses_confirm_modal_for_delete():
    src = (COMPONENTS / "SchedulesList.js").read_text()
    assert "export function SchedulesList(" in src
    assert "import { ConfirmModal } from './ConfirmModal.js';" in src
    assert "toggleSchedule" in src, "enable/disable missing"
    assert "runScheduleNow" in src, "run-now missing"
    assert "deleteSchedule" in src, "delete missing"
    assert "formatRelative" in src, "next-run countdown missing"
    assert "Target missing" in src and "Target in trash" in src, "blocked-target state missing"


def test_app_registers_the_schedules_panel_and_modal():
    app = (JS / "app.js").read_text()
    assert "import { SchedulesList } from './components/SchedulesList.js';" in app
    assert "import { ScheduleModal } from './components/ScheduleModal.js';" in app
    assert "currentPanel.value === 'schedules'" in app, "panel not gated on route"
    assert 'id="panel-schedules"' in app, "panel markup missing"
    assert "<${ScheduleModal}" in app, "ScheduleModal not rendered"
    assert re.search(r"setInterval\(\(\) => loadSchedules\(\)\.catch\(\(\) => \{\}\), 5000\)", app), "panel polling missing"
    assert "loadSchedules()" in app.split("async function init")[1], "schedules not loaded on init"


def test_state_and_api_wire_up_schedules():
    state = (JS / "state.js").read_text()
    assert "'schedules'" in state, "PANELS is missing 'schedules'"
    assert "export const schedules = signal([]);" in state
    api = (JS / "api.js").read_text()
    for fn in ("loadSchedules", "saveSchedule", "toggleSchedule", "runScheduleNow", "deleteSchedule", "previewCron"):
        assert f"export async function {fn}(" in api, f"api.js missing {fn}"


def test_sidebar_links_schedules_in_desktop_header_and_drawer():
    src = (COMPONENTS / "Sidebar.js").read_text()
    assert src.count("showPanel('schedules')") >= 3, \
        "desktop nav, mobile header and mobile drawer must all link Schedules"


def test_history_table_flags_scheduled_runs():
    src = (COMPONENTS / "HistoryTable.js").read_text()
    assert "e.trigger === 'scheduled'" in src, "trigger check missing"
    assert "Scheduled" in src, "badge text missing"


def test_profile_and_workflow_cards_show_schedule_badge():
    card = (COMPONENTS / "ProfileCard.js").read_text()
    assert "schedules.value.some" in card, "ProfileCard ignores schedules"
    assert "target_type === 'profile'" in card
    assert "Scheduled" in card, "ProfileCard badge missing"
    wcard = (COMPONENTS / "WorkflowCard.js").read_text()
    assert "schedules.value.some" in wcard, "WorkflowCard ignores schedules"
    assert "target_type === 'workflow'" in wcard
    assert "Scheduled" in wcard, "WorkflowCard badge missing"
