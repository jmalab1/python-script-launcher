package main

import (
	"fmt"
	"path/filepath"
	"time"

	"github.com/mxschmitt/playwright-go"

	"launchcontrol/internal/devtools"
)

// seedWait allows the two pre-runs to land in History and Audit
// before the tour starts. It is a variable so tests can shorten it.
var seedWait = 2500 * time.Millisecond

// devtoolsAPI is the POST-only wrapper around the shared JSON client;
// everything the seeder posts is a JSON object in and out.
func devtoolsAPI(baseURL, path string, payload map[string]any) (map[string]any, error) {
	out, err := devtools.APIRequest(baseURL, "POST", path, payload)
	if err != nil {
		return nil, err
	}
	obj, ok := out.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("%s: response is not an object: %v", path, out)
	}
	return obj, nil
}

// seed fills the demo server with profiles, a workflow and schedules
// via the HTTP API, and pre-runs two profiles so History and Audit
// have realistic rows. It returns the created profiles.
//
// Profiles and workflows carry `tags` arrays referencing the global
// tag list that recordTour injects into the browser's localStorage.
func seed(baseURL, scriptsDir string) ([]map[string]any, error) {
	script := func(name string) string {
		return filepath.Join(scriptsDir, name)
	}

	type customArg struct {
		Name    string
		Label   string
		Type    string
		Default string
		Value   string
	}
	asArgs := func(args []customArg) []any {
		out := make([]any, 0, len(args))
		for _, a := range args {
			out = append(out, map[string]any{
				"name": a.Name, "label": a.Label, "type": a.Type,
				"default": a.Default, "value": a.Value,
			})
		}
		return out
	}

	specs := []struct {
		id, name, script string
		args             []any
		tags             []string
		customArgs       []customArg
	}{
		{
			id: "profile_demo_report", name: "Daily Report", script: "generate_report.py",
			tags: []string{"tag_reports"},
			customArgs: []customArg{
				{Name: "--format", Label: "Format", Type: "text", Default: "pdf", Value: "pdf"},
			},
		},
		{
			id: "profile_demo_pipeline", name: "Data Pipeline", script: "process_data.py",
			tags: []string{"tag_data", "tag_reports"},
			customArgs: []customArg{
				{Name: "--input", Label: "Input file", Type: "text", Default: "data.csv", Value: "data.csv"},
				{Name: "--clean", Label: "Clean first", Type: "checkbox", Default: "", Value: "true"},
			},
		},
		{
			id: "profile_demo_fetch", name: "Fetch Data", script: "fetch_data.py",
			tags: []string{"tag_data"},
			customArgs: []customArg{
				{Name: "--rows", Label: "Rows", Type: "text", Default: "50", Value: "50"},
			},
		},
		{
			id: "profile_demo_backup", name: "Nightly Backup", script: "backup.py",
			args: []any{"--compress"}, tags: []string{"tag_ops"},
		},
		{
			id: "profile_demo_email", name: "Email Report", script: "send_email.py",
			tags: []string{"tag_reports"},
			customArgs: []customArg{
				{Name: "--to", Label: "Recipient", Type: "text", Default: "team@example.com", Value: "team@example.com"},
			},
		},
	}

	var created []map[string]any
	for _, s := range specs {
		out, err := devtoolsAPI(baseURL, "/api/profiles", map[string]any{
			"id":          s.id,
			"name":        s.name,
			"script_path": script(s.script),
			"args":        s.args,
			"tags":        s.tags,
			"custom_args": asArgs(s.customArgs),
		})
		if err != nil {
			return nil, err
		}
		created = append(created, out)
	}

	report, backup, email := created[0], created[3], created[4]
	if _, err := devtoolsAPI(baseURL, "/api/workflows", map[string]any{
		"id":   "workflow_demo_nightly",
		"name": "Nightly Pipeline",
		"steps": []any{
			map[string]any{"type": "sequential", "profile_id": report["id"]},
			map[string]any{"type": "parallel", "profiles": []any{
				map[string]any{"profile_id": created[2]["id"]},
				map[string]any{"profile_id": backup["id"]},
			}},
			map[string]any{"type": "sequential", "profile_id": email["id"]},
		},
		"extra_args":        []any{},
		"continue_on_error": false,
		"tags":              []string{"tag_ops", "tag_data"},
	}); err != nil {
		return nil, err
	}

	if _, err := devtoolsAPI(baseURL, "/api/schedules", map[string]any{
		"name":        "Every 6 hours",
		"target_type": "profile",
		"target_id":   backup["id"],
		"cron":        "0 */6 * * *",
		"enabled":     true,
	}); err != nil {
		return nil, err
	}
	if _, err := devtoolsAPI(baseURL, "/api/schedules", map[string]any{
		"name":        "Daily at 09:00",
		"target_type": "workflow",
		"target_id":   "workflow_demo_nightly",
		"cron":        "0 9 * * *",
		"enabled":     true,
	}); err != nil {
		return nil, err
	}

	// Pre-runs keep the seeded run going while tags are injected.
	if _, err := devtoolsAPI(baseURL, "/api/run/profile", map[string]any{
		"profile_id": report["id"],
	}); err != nil {
		return nil, err
	}
	if _, err := devtoolsAPI(baseURL, "/api/run/profile", map[string]any{
		"profile_id": backup["id"],
	}); err != nil {
		return nil, err
	}
	time.Sleep(seedWait)

	return created, nil
}

// card locates a profile/workflow card root by its title heading (see
// the same helper in the e2e suite).
func card(page playwright.Page, panelID, name string) playwright.Locator {
	heading := page.Locator("#"+panelID+" h3", playwright.PageLocatorOptions{HasText: name})
	return heading.Locator("xpath=ancestor::div[contains(@class,'group')][1]")
}

// modalShell is the top-level modal overlay: every modal renders into
// that one z-50 layer.
func modalShell(page playwright.Page) playwright.Locator {
	return page.Locator("div.fixed.inset-0.z-50")
}

// waitForHeading blocks until a heading with the given name shows up.
func waitForHeading(page playwright.Page, name string) error {
	return page.GetByRole(*playwright.AriaRoleHeading,
		playwright.PageGetByRoleOptions{Name: name}).WaitFor()
}

// waitForHeadingIn is waitForHeading scoped to one locator (a modal).
func waitForHeadingIn(loc playwright.Locator, name string, timeoutMs float64) error {
	return loc.GetByRole(*playwright.AriaRoleHeading,
		playwright.LocatorGetByRoleOptions{Name: name}).
		WaitFor(playwright.LocatorWaitForOptions{Timeout: playwright.Float(timeoutMs)})
}

// waitForHidden waits for the current modal overlay to close.
func waitForHidden(page playwright.Page) error {
	return modalShell(page).WaitFor(
		playwright.LocatorWaitForOptions{State: playwright.WaitForSelectorStateHidden})
}

// clickButton clicks a role=button with the given name, scoped to loc
// (the page itself when loc is nil) and taking the first match.
func clickButton(loc playwright.Locator, page playwright.Page, name string, exact bool) error {
	opts := playwright.LocatorGetByRoleOptions{Name: name, Exact: playwright.Bool(exact)}
	var btn playwright.Locator
	if loc != nil {
		btn = loc.GetByRole(*playwright.AriaRoleButton, opts).First()
	} else {
		btn = page.GetByRole(*playwright.AriaRoleButton,
			playwright.PageGetByRoleOptions{Name: name, Exact: playwright.Bool(exact)}).First()
	}
	return btn.Click()
}

// tour drives the browser through the demo tour while the video
// records. The numbered steps speak for themselves on the recording:
// panels in sidebar order, plus the tag workflow and theme toggle.
func tour(page playwright.Page, baseURL string, pauseMs float64) error {
	// 1. Profiles panel with the seeded cards.
	if _, err := page.Goto(baseURL); err != nil {
		return err
	}
	if err := waitForHeading(page, "Profiles"); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs * 1.5)

	// 2. Run the Daily Report profile and watch live output stream in.
	modal := modalShell(page)
	daily := card(page, "panel-profiles", "Daily Report")
	if err := clickButton(daily, page, "Run", false); err != nil {
		return err
	}
	if err := waitForHeadingIn(modal, "Profile Run", 5000); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs * 2)
	if err := clickButton(modal, page, "Close", false); err != nil {
		return err
	}
	if err := waitForHidden(page); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs)

	// 3. Scroll the profile-cards column to reveal the remaining cards.
	if err := page.Mouse().Move(430, 400); err != nil {
		return err
	}
	if err := page.Mouse().Wheel(0, 400); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs)
	if err := page.Mouse().Wheel(0, 300); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs)
	if err := page.Mouse().Wheel(0, -700); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs)

	// 4. Tags: filter the list down to one tag, then back to all.
	if err := clickButton(nil, page, "Data 2", false); err != nil {
		return err
	}
	if err := waitForHeading(page, "Profiles"); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs * 1.5)
	if err := clickButton(nil, page, "Data 2", false); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs)

	// 5. Assign an extra tag while editing: Fetch Data also joins
	//    Reports.
	fetchCard := card(page, "panel-profiles", "Fetch Data")
	if err := clickButton(fetchCard, page, "Edit", false); err != nil {
		return err
	}
	if err := waitForHeadingIn(modal, "Edit Profile", 5000); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs)
	if err := clickButton(modal, page, "Reports", true); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs)
	if err := clickButton(modal, page, "Save Profile", false); err != nil {
		return err
	}
	if err := waitForHidden(page); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs)

	// 6. Tag manager: one global list shared by profiles and
	//    workflows, each with a pickable color.
	if err := clickButton(nil, page, "Tags", false); err != nil {
		return err
	}
	if err := waitForHeadingIn(modal, "Manage Tags", 5000); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs * 1.5)
	if err := modal.GetByRole(*playwright.AriaRoleButton,
		playwright.LocatorGetByRoleOptions{Name: "Change color"}).Last().Click(); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs)
	if err := clickButton(modal, page, "rose", false); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs * 1.5)
	if err := clickButton(modal, page, "Done", false); err != nil {
		return err
	}
	if err := waitForHidden(page); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs)

	// 7. Workflows panel; run the chained workflow (same global tags
	//    apply).
	if err := clickButton(nil, page, "Workflows", false); err != nil {
		return err
	}
	if err := waitForHeading(page, "Workflows"); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs)
	nightly := card(page, "panel-workflows", "Nightly Pipeline")
	if err := clickButton(nightly, page, "Run", false); err != nil {
		return err
	}
	if err := waitForHeadingIn(modal, "Workflow Run", 5000); err != nil {
		return err
	}
	if err := modal.GetByText("Workflow completed").
		WaitFor(playwright.LocatorWaitForOptions{Timeout: playwright.Float(workflowCompletionTimeoutMs)}); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs * 2)
	if err := clickButton(modal, page, "Close", false); err != nil {
		return err
	}
	if err := waitForHidden(page); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs)

	// 8. Schedules panel and the live cron preview in the editor.
	if err := clickButton(nil, page, "Schedules", false); err != nil {
		return err
	}
	if err := waitForHeading(page, "Schedules"); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs)
	if err := clickButton(nil, page, "New Schedule", false); err != nil {
		return err
	}
	if err := waitForHeadingIn(modal, "New Schedule", 5000); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs)
	numberInput := modal.Locator("input[type='number']").First()
	if err := numberInput.Fill("15"); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs)
	if err := numberInput.Fill("45"); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs)
	if err := clickButton(modal, page, "Cancel", false); err != nil {
		return err
	}
	if err := waitForHidden(page); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs)

	// 9. Audit trail.
	if err := clickButton(nil, page, "Audit", false); err != nil {
		return err
	}
	if err := waitForHeading(page, "Audit"); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs * 1.5)

	// 10. Server logs with live tailing.
	if err := clickButton(nil, page, "Logs", false); err != nil {
		return err
	}
	if err := waitForHeading(page, "Server Logs"); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs * 2)

	// 11. Theme toggle: light, then back to dark.
	if err := clickButton(nil, page, "Light Mode", false); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs)
	if err := clickButton(nil, page, "Dark Mode", false); err != nil {
		return err
	}
	page.WaitForTimeout(pauseMs)

	// 12. Back to Profiles for the closing shot.
	if err := clickButton(nil, page, "Profiles", false); err != nil {
		return err
	}
	return waitForHeading(page, "Profiles")
}
