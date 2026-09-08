"""End-to-end UI tests driven by Playwright.

These exercise the real app — the stdlib HTTP server plus the vanilla JS
frontend — against the isolated server booted by the `launcher_server`
fixture in this directory's conftest. Requires pytest-playwright and
Chromium (`python3 -m playwright install chromium`).
"""

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

pytestmark = pytest.mark.e2e

GREETING = "E2E Greeting"
FAILING = "E2E Failing"
DISPOSABLE = "E2E Disposable"
WORKFLOW = "E2E Chain"


def _card(page, panel_id, name):
    """Locate a profile/workflow card root by its title heading.

    Card roots carry a Tailwind `group` marker class; picking the nearest
    ancestor with that class from the <h3> keeps the locator unambiguous.
    """
    heading = page.locator(f"#{panel_id} h3", has_text=name)
    return heading.locator("xpath=ancestor::div[contains(@class, 'group')][1]")


def _modal(page):
    """The top-level modal overlay (all modals render into one z-50 layer)."""
    return page.locator("div.fixed.inset-0.z-50")


def test_profiles_panel_renders_seeded_cards(page, launcher_server):
    page.goto(launcher_server["base_url"])

    greeting_card = _card(page, "panel-profiles", GREETING)
    expect(greeting_card.get_by_role("heading", name=GREETING)).to_be_visible()
    expect(greeting_card.get_by_text("greet.py")).to_be_visible()

    failing_card = _card(page, "panel-profiles", FAILING)
    expect(failing_card.get_by_role("heading", name=FAILING)).to_be_visible()


def test_sidebar_navigation_between_panels(page, launcher_server):
    base_url = launcher_server["base_url"]
    page.goto(base_url)
    expect(page.get_by_role("heading", name="Profiles", exact=True)).to_be_visible()

    page.get_by_role("button", name="Workflows").click()
    expect(page.get_by_role("heading", name="Workflows", exact=True)).to_be_visible()
    assert page.url.endswith("#/workflows")

    page.get_by_role("button", name="Schedules").click()
    expect(page.get_by_role("heading", name="Schedules", exact=True)).to_be_visible()
    assert page.url.endswith("#/schedules")

    page.get_by_role("button", name="Audit").click()
    expect(page.get_by_role("heading", name="Audit", exact=True)).to_be_visible()
    assert page.url.endswith("#/audit")

    page.get_by_role("button", name="Profiles").click()
    expect(page.get_by_role("heading", name="Profiles", exact=True)).to_be_visible()


def test_run_profile_shows_live_output_and_completed_status(page, launcher_server):
    page.goto(launcher_server["base_url"])

    card = _card(page, "panel-profiles", GREETING)
    card.get_by_role("button", name="Run").click()

    modal = _modal(page)
    expect(modal.get_by_role("heading", name="Profile Run")).to_be_visible()
    expect(modal.get_by_text("Hello, E2E!")).to_be_visible()
    expect(modal.get_by_text("Completed", exact=True)).to_be_visible(timeout=15000)

    modal.get_by_role("button", name="Close").click()
    expect(modal).to_be_hidden()


def test_profile_run_is_recorded_in_history(page, launcher_server):
    page.goto(launcher_server["base_url"])

    card = _card(page, "panel-profiles", GREETING)
    card.get_by_role("button", name="Run").click()
    modal = _modal(page)
    expect(modal.get_by_text("Completed", exact=True)).to_be_visible(timeout=15000)
    modal.get_by_role("button", name="Close").click()

    # The profiles panel polls history every 3s; wait for the new row.
    row = page.locator("#panel-profiles tbody tr", has_text=GREETING).filter(
        has_text="completed"
    ).first
    expect(row).to_be_visible(timeout=10000)


def test_failing_profile_reports_failed_status_and_error_output(page, launcher_server):
    page.goto(launcher_server["base_url"])

    card = _card(page, "panel-profiles", FAILING)
    card.get_by_role("button", name="Run").click()

    modal = _modal(page)
    expect(modal.get_by_role("heading", name="Profile Run")).to_be_visible()
    expect(modal.get_by_text("boom: expected failure")).to_be_visible(timeout=10000)
    expect(modal.get_by_text("Failed", exact=True)).to_be_visible(timeout=10000)


def test_run_workflow_shows_step_log_and_completion(page, launcher_server):
    page.goto(launcher_server["base_url"])

    page.get_by_role("button", name="Workflows").click()
    card = _card(page, "panel-workflows", WORKFLOW)
    expect(card.get_by_role("heading", name=WORKFLOW)).to_be_visible()
    card.get_by_role("button", name="Run").click()

    modal = _modal(page)
    expect(modal.get_by_role("heading", name="Workflow Run")).to_be_visible()
    expect(modal.get_by_text("[RUN] Step 1: E2E Greeting")).to_be_visible(timeout=10000)
    expect(modal.get_by_text("Workflow completed")).to_be_visible(timeout=15000)


def test_new_profile_modal_alerts_when_required_fields_missing(page, launcher_server):
    page.goto(launcher_server["base_url"])

    page.get_by_role("button", name="New Profile").click()
    modal = _modal(page)
    expect(modal.get_by_role("heading", name="New Profile")).to_be_visible()

    page.get_by_placeholder("e.g. Data Pipeline").fill("E2E Typed")
    # A synchronous alert() blocks the click action, so a dialog handler
    # must be registered up front rather than awaited around the click.
    alerts = []
    page.on("dialog", lambda dialog: (alerts.append(dialog.message), dialog.dismiss()))
    modal.get_by_role("button", name="Save Profile").click()

    assert alerts == ["Name and script path are required."]

    expect(modal.get_by_role("heading", name="New Profile")).to_be_visible()
    modal.get_by_role("button", name="Cancel").click()
    expect(modal).to_be_hidden()


def test_profile_delete_routes_through_confirm_modal(page, launcher_server):
    api = launcher_server["api"]
    api("POST", "/api/profiles", {
        "id": "profile_e2e_disposable",
        "name": DISPOSABLE,
        "script_path": str(launcher_server["data_dir"] / "scripts" / "greet.py"),
        "args": [],
        "custom_args": [],
    })

    page.goto(launcher_server["base_url"])
    card = _card(page, "panel-profiles", DISPOSABLE)
    expect(card).to_be_visible()

    card.get_by_role("button", name="Delete", exact=True).click()

    modal = _modal(page)
    expect(modal.get_by_role("heading", name="Delete profile")).to_be_visible()
    modal.get_by_role("button", name="Delete", exact=True).click()

    expect(modal).to_be_hidden()
    expect(card).to_be_hidden()

    trashed = api("GET", "/api/profiles")
    disposable = next(p for p in trashed if p["id"] == "profile_e2e_disposable")
    assert disposable["group"] == "__trash__"


def test_audit_panel_lists_seeded_changes(page, launcher_server):
    page.goto(launcher_server["base_url"])

    page.get_by_role("button", name="Audit").click()
    expect(page.get_by_role("heading", name="Audit", exact=True)).to_be_visible()

    profile_row = page.locator("#panel-audit tbody tr", has_text=GREETING).first
    expect(profile_row).to_be_visible()
    expect(profile_row.filter(has_text="Created")).to_be_visible()

    workflow_row = page.locator("#panel-audit tbody tr", has_text=WORKFLOW).first
    expect(workflow_row).to_be_visible()


def test_logs_panel_shows_live_server_log(page, launcher_server):
    page.goto(launcher_server["base_url"])

    page.get_by_role("button", name="Logs").click()
    expect(page.get_by_role("heading", name="Server Logs", exact=True)).to_be_visible()

    # Page load and API polling generate request lines in the server's own log.
    line = page.locator("#panel-logs .font-mono > div", has_text="GET").first
    expect(line).to_be_visible(timeout=10000)


def test_theme_toggle_updates_root_class_and_persists(page, launcher_server):
    page.goto(launcher_server["base_url"])
    expect(page.get_by_role("heading", name="Profiles", exact=True)).to_be_visible()
    assert page.evaluate("document.documentElement.classList.contains('dark')") is True

    page.get_by_role("button", name="Light Mode").click()
    expect(page.get_by_role("button", name="Dark Mode")).to_be_visible()
    assert page.evaluate("document.documentElement.classList.contains('dark')") is False
    assert page.evaluate("localStorage.getItem('theme')") == "light"

    page.get_by_role("button", name="Dark Mode").click()
    expect(page.get_by_role("button", name="Light Mode")).to_be_visible()
    assert page.evaluate("document.documentElement.classList.contains('dark')") is True
    assert page.evaluate("localStorage.getItem('theme')") == "dark"


def test_schedules_panel_shows_schedule_and_card_badge(page, launcher_server):
    created = launcher_server["api"]("POST", "/api/schedules", {
        "name": "Hourly greeting",
        "target_type": "profile",
        "target_id": "profile_e2e_greet",
        "cron": "0 * * * *",
        "enabled": True,
    })
    try:
        page.goto(launcher_server["base_url"])

        page.get_by_role("button", name="Schedules").click()
        panel = page.locator("#panel-schedules")
        expect(panel.get_by_role("heading", name="Hourly greeting")).to_be_visible()
        expect(panel.get_by_text("Every hour", exact=True)).to_be_visible()
        expect(panel.get_by_text("Next:")).to_be_visible()

        # The profile card advertises its schedule back on the Profiles panel.
        page.get_by_role("button", name="Profiles").click()
        card = _card(page, "panel-profiles", GREETING)
        expect(card.get_by_text("Scheduled")).to_be_visible()
    finally:
        launcher_server["api"]("DELETE", f"/api/schedules/{created['id']}")


def test_schedule_modal_repeat_builder_compiles_and_previews(page, launcher_server):
    page.goto(launcher_server["base_url"])

    page.get_by_role("button", name="Schedules").click()
    page.get_by_role("button", name="New Schedule").click()
    modal = _modal(page)

    # Default preset: repeat every 30 minutes, compiled to cron with a live preview.
    number_input = modal.locator("input[type='number']").first
    expect(number_input).to_have_value("30")
    expect(modal.get_by_text("*/30 * * * *", exact=True)).to_be_visible()
    expect(modal.get_by_text("Every 30 minutes", exact=True)).to_be_visible()

    number_input.fill("7")
    expect(modal.get_by_text("*/7 * * * *", exact=True)).to_be_visible()
    expect(modal.get_by_text("Every 7 minutes", exact=True)).to_be_visible()

    unit_select = modal.locator("select").nth(2)
    unit_select.select_option("hours")
    expect(modal.get_by_text("0 */7 * * *", exact=True)).to_be_visible()
    expect(modal.get_by_text("Every 7 hours", exact=True)).to_be_visible()
