//go:build e2e

// Package e2e drives the real app — the compiled Go server plus the
// vanilla JS frontend — in Chromium. It is a one-to-one port of the
// pytest suite that used to live in this directory (see
// tests/e2e/conftest.py and test_app_e2e.py in git history).
//
// The build tag keeps this file out of plain `go test ./...`, so the
// playwright driver and browser are never needed for regular unit
// runs. Run with:
//
//	make test-e2e
//
// and install the browser driver once with:
//
//	go run github.com/mxschmitt/playwright-go/cmd/playwright install chromium
package e2e_test

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/mxschmitt/playwright-go"
)

// Names the seeded data must have so the tests can find them.
const (
	greetingName   = "E2E Greeting"
	failingName    = "E2E Failing"
	disposableName = "E2E Disposable"
	workflowName   = "E2E Chain"
)

// Waits, in milliseconds. Most UI updates land within seconds; run
// statuses wait the longest because a real Python child script has to
// run to completion before they appear.
const (
	defaultTimeoutMs    = 5000
	completionTimeoutMs = 15000
	rowWaitTimeoutMs    = 10000
	serverReadyWait     = 15 * time.Second
	serverStopGrace     = 10 * time.Second
)

const greetingScript = `import time

print("Hello, E2E!")
print("Starting work...")
time.sleep(1.0)
print("Done!")
`

const failingScript = `import sys

print("about to fail")
print("boom: expected failure", file=sys.stderr)
sys.exit(3)
`

// skipInstall marks a "tooling not installed yet" problem: the suite
// skips instead of failing, mirroring the pytest conftest's graceful
// skip.
type skipInstall struct{ msg string }

func (e skipInstall) Error() string { return e.msg }

// e2eSuite is the session-scoped fixture (the old launcher_server
// fixture): one server, browser and seeded dataset shared by every
// test. Each test opens its own page so no DOM state can leak between
// them.
type e2eSuite struct {
	t *testing.T

	baseURL    string
	dataDir    string
	greetingID string

	pw       *playwright.Playwright
	browser  playwright.Browser
	assert   playwright.PlaywrightAssertions
	stopServ func()
}

var (
	suiteHeld *e2eSuite
)

func TestMain(m *testing.M) {
	s, err := startFixture()
	if err != nil {
		if asSkip, ok := err.(skipInstall); ok {
			fmt.Printf("e2e skipped: %s\n", asSkip.msg)
			os.Exit(0)
		}
		fmt.Fprintf(os.Stderr, "e2e fixture failed: %v\n", err)
		os.Exit(1)
	}
	suiteHeld = s

	code := m.Run()
	s.close()
	os.Exit(code)
}

// startFixture boots one isolated server plus a Chromium browser for
// the whole run and seeds the data the tests drive.
func startFixture() (*e2eSuite, error) {
	repoRoot, err := filepath.Abs(filepath.Join("..", ".."))
	if err != nil {
		return nil, err
	}

	dataDir, err := os.MkdirTemp("", "e2e-data")
	if err != nil {
		return nil, err
	}
	s := &e2eSuite{dataDir: dataDir}

	scriptsDir := filepath.Join(dataDir, "scripts")
	if err := os.MkdirAll(scriptsDir, 0o700); err != nil {
		return nil, err
	}
	if err := os.WriteFile(filepath.Join(scriptsDir, "greet.py"), []byte(greetingScript), 0o600); err != nil {
		return nil, err
	}
	if err := os.WriteFile(filepath.Join(scriptsDir, "fail.py"), []byte(failingScript), 0o600); err != nil {
		return nil, err
	}

	// A free port: bind to :0, read the kernel-assigned port, unbind so
	// the server can take the same one.
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return nil, err
	}
	port := listener.Addr().(*net.TCPAddr).Port
	_ = listener.Close()
	s.baseURL = fmt.Sprintf("http://127.0.0.1:%d", port)
	logPath := filepath.Join(dataDir, "server.log")

	// The server command comes from LAUNCHER_SERVER_CMD when the suite
	// must drive a particular binary (e.g. a release build); the
	// default is the dev binary, built on demand.
	argv := []string{filepath.Join(repoRoot, "dist", "launchctl"),
		"-port", strconv.Itoa(port), "-foreground"}
	if override := os.Getenv("LAUNCHER_SERVER_CMD"); override != "" {
		argv = append(strings.Fields(override), strconv.Itoa(port))
	} else if _, statErr := os.Stat(argv[0]); os.IsNotExist(statErr) {
		build := exec.Command("make", "go-build") //nolint:gosec // fixed dev-tooling args
		build.Dir = repoRoot
		build.Stdout, build.Stderr = os.Stdout, os.Stderr
		if buildErr := build.Run(); buildErr != nil {
			return nil, fmt.Errorf("building the server failed: %w", buildErr)
		}
	}

	cmd := exec.Command(argv[0], argv[1:]...) //nolint:gosec // argv assembled from the fixed choices above
	cmd.Dir = repoRoot
	cmd.Env = append(os.Environ(), "LAUNCHER_DATA_DIR="+dataDir)
	logFile, err := os.Create(logPath)
	if err != nil {
		return nil, err
	}
	defer logFile.Close()
	cmd.Stdout = logFile
	cmd.Stderr = logFile
	if err := cmd.Start(); err != nil {
		return nil, err
	}
	s.stopServ = func() {
		_ = cmd.Process.Signal(os.Interrupt)
		done := make(chan struct{})
		go func() { _ = cmd.Wait(); close(done) }()
		select {
		case <-done:
		case <-time.After(serverStopGrace):
			_ = cmd.Process.Kill()
			<-done
		}
		_ = os.RemoveAll(dataDir)
	}

	pollErr := s.waitReady(logPath)
	if pollErr != nil {
		s.stopServ()
		return nil, pollErr
	}

	// Seed the data through the API, exactly like conftest.py did.
	greetingRaw, err := apiRequest(s.baseURL, http.MethodPost, "/api/profiles", map[string]any{
		"id":          "profile_e2e_greet",
		"name":        greetingName,
		"script_path": filepath.Join(scriptsDir, "greet.py"),
		"args":        []any{},
		"custom_args": []any{},
	})
	if err != nil {
		s.stopServ()
		return nil, err
	}
	greeting, _ := greetingRaw.(map[string]any)
	workflow, err := apiRequest(s.baseURL, http.MethodPost, "/api/workflows", map[string]any{
		"id":   "workflow_e2e",
		"name": workflowName,
		"steps": []any{map[string]any{
			"type":       "sequential",
			"profile_id": greeting["id"],
		}},
		"extra_args":        []any{},
		"continue_on_error": false,
	})
	if err != nil {
		s.stopServ()
		return nil, err
	}
	// The failing profile is seeded here too, like conftest did.
	if _, err := apiRequest(s.baseURL, http.MethodPost, "/api/profiles", map[string]any{
		"id":          "profile_e2e_fail",
		"name":        failingName,
		"script_path": filepath.Join(scriptsDir, "fail.py"),
		"args":        []any{},
		"custom_args": []any{},
	}); err != nil {
		s.stopServ()
		return nil, err
	}

	s.greetingID, _ = greeting["id"].(string)
	_ = workflow

	pw, err := playwright.Run()
	if err != nil {
		s.stopServ()
		if isInstallMissing(err) {
			return nil, skipInstall{"run: go run github.com/mxschmitt/playwright-go/cmd/playwright install (" + err.Error() + ")"}
		}
		return nil, err
	}
	s.pw = pw

	browser, err := pw.Chromium.Launch()
	if err != nil {
		_ = pw.Stop()
		s.stopServ()
		if isInstallMissing(err) {
			return nil, skipInstall{
				"Chromium is not installed - run: go run " +
					"github.com/mxschmitt/playwright-go/cmd/playwright install chromium (" + err.Error() + ")",
			}
		}
		return nil, err
	}
	s.browser = browser
	s.assert = playwright.NewPlaywrightAssertions(float64(defaultTimeoutMs))
	return s, nil
}

// isInstallMissing reports whether err is the "browser/driver not
// downloaded yet" complaint rather than a real failure.
func isInstallMissing(err error) bool {
	lower := strings.ToLower(err.Error())
	return strings.Contains(lower, "install") ||
		strings.Contains(lower, "executable doesn't exist") ||
		strings.Contains(lower, "driver")
}

func (s *e2eSuite) waitReady(logPath string) error {
	deadline := time.Now().Add(serverReadyWait)
	for {
		resp, err := http.Get(s.baseURL + "/api/profiles") //nolint:gosec,noctx // local test server
		if err == nil {
			_ = resp.Body.Close()
			if resp.StatusCode == http.StatusOK {
				return nil
			}
		}
		if time.Now().After(deadline) {
			log, _ := os.ReadFile(logPath)
			return fmt.Errorf("e2e server did not start.\n%s", log)
		}
		time.Sleep(100 * time.Millisecond)
	}
}

// close tears the fixture down: browser, then server and data dir.
func (s *e2eSuite) close() {
	if s.browser != nil {
		_ = s.browser.Close()
	}
	if s.pw != nil {
		_ = s.pw.Stop()
	}
	if s.stopServ != nil {
		s.stopServ()
	}
}

// apiRequest is the tiny JSON client used to seed data and to inspect
// collections from inside tests. List endpoints return arrays, single
// resources objects — hence the generic any.
func apiRequest(baseURL, method, path string, payload map[string]any) (any, error) {
	var body io.Reader
	if payload != nil {
		raw, err := json.Marshal(payload)
		if err != nil {
			return nil, err
		}
		body = bytes.NewReader(raw)
	}
	req, err := http.NewRequest(method, baseURL+path, body)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	var out any
	if err := json.Unmarshal(raw, &out); err != nil {
		return nil, fmt.Errorf("decoding %s %s response: %w (%s)", method, path, err, raw)
	}
	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("%s %s: status %d: %s", method, path, resp.StatusCode, raw)
	}
	return out, nil
}

// api is the test-facing wrapper: failures fail the calling test.
func (s *e2eSuite) api(t *testing.T, method, path string, payload map[string]any) any {
	t.Helper()
	out, err := apiRequest(s.baseURL, method, path, payload)
	if err != nil {
		t.Fatalf("api %s %s: %v", method, path, err)
	}
	return out
}

// page gives the test a fresh page in its own context (fresh page
// per test, like pytest-playwright's function-scoped page fixture).
func (s *e2eSuite) page(t *testing.T) playwright.Page {
	t.Helper()
	ctx, err := s.browser.NewContext()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = ctx.Close() })
	ctx.SetDefaultTimeout(float64(defaultTimeoutMs))
	page, err := ctx.NewPage()
	if err != nil {
		t.Fatal(err)
	}
	return page
}

// card locates a profile/workflow card root by its title heading. Card
// roots carry a Tailwind `group` marker class; picking the nearest
// ancestor with that class from the h3 keeps the locator unambiguous.
func card(page playwright.Page, panelID, name string) playwright.Locator {
	heading := page.Locator("#"+panelID+" h3", playwright.PageLocatorOptions{HasText: name})
	return heading.Locator("xpath=ancestor::div[contains(@class,'group')][1]")
}

// modalShell is the top-level modal overlay: every modal renders into
// that one z-50 layer.
func modalShell(page playwright.Page) playwright.Locator {
	return page.Locator("div.fixed.inset-0.z-50")
}

// expectVisible waits up to msecs for loc to be visible.
func (s *e2eSuite) expectVisible(loc playwright.Locator, msecs float64) {
	if err := s.assert.Locator(loc).ToBeVisible(
		playwright.LocatorAssertionsToBeVisibleOptions{Timeout: playwright.Float(msecs)}); err != nil {
		s.t.Fatal(err)
	}
}

func (s *e2eSuite) expectVisibleNow(loc playwright.Locator) {
	s.expectVisible(loc, float64(defaultTimeoutMs))
}

// expectHidden waits for loc to disappear.
func (s *e2eSuite) expectHidden(loc playwright.Locator) {
	if err := s.assert.Locator(loc).ToBeHidden(); err != nil {
		s.t.Fatal(err)
	}
}

// expectHeadingOn asserts a named heading (role-based lookup).
func expectHeadingOn(s *e2eSuite, loc playwright.Locator, name string, exact bool) {
	s.expectVisibleNow(loc.GetByRole(*playwright.AriaRoleHeading,
		playwright.LocatorGetByRoleOptions{Name: name, Exact: playwright.Bool(exact)}))
}

func expectHeading(s *e2eSuite, page playwright.Page, name string, exact bool) {
	if err := s.assert.Locator(page.GetByRole(*playwright.AriaRoleHeading,
		playwright.PageGetByRoleOptions{Name: name, Exact: playwright.Bool(exact)})).ToBeVisible(); err != nil {
		s.t.Fatal(err)
	}
}

// --- the tests themselves, one per pytest test function ---

func TestProfilesPanelRendersSeededCards(t *testing.T) {
	s := fixture(t)
	page := s.page(t)
	page.Goto(s.baseURL)

	greetingCard := card(page, "panel-profiles", greetingName)
	expectHeadingOn(s, greetingCard, greetingName, false)
	s.expectVisibleNow(greetingCard.GetByText("greet.py"))

	failingCard := card(page, "panel-profiles", failingName)
	expectHeadingOn(s, failingCard, failingName, false)
}

func TestSidebarNavigationBetweenPanels(t *testing.T) {
	s := fixture(t)
	page := s.page(t)
	page.Goto(s.baseURL)
	expectHeading(s, page, "Profiles", true)

	page.GetByRole(*playwright.AriaRoleButton, playwright.PageGetByRoleOptions{Name: "Workflows"}).Click()
	expectHeading(s, page, "Workflows", true)
	if !strings.HasSuffix(page.URL(), "#/workflows") {
		t.Errorf("URL after Workflows = %q", page.URL())
	}

	page.GetByRole(*playwright.AriaRoleButton, playwright.PageGetByRoleOptions{Name: "Schedules"}).Click()
	expectHeading(s, page, "Schedules", true)
	if !strings.HasSuffix(page.URL(), "#/schedules") {
		t.Errorf("URL after Schedules = %q", page.URL())
	}

	page.GetByRole(*playwright.AriaRoleButton, playwright.PageGetByRoleOptions{Name: "Audit"}).Click()
	expectHeading(s, page, "Audit", true)
	if !strings.HasSuffix(page.URL(), "#/audit") {
		t.Errorf("URL after Audit = %q", page.URL())
	}

	page.GetByRole(*playwright.AriaRoleButton, playwright.PageGetByRoleOptions{Name: "Profiles"}).Click()
	expectHeading(s, page, "Profiles", true)
}

func TestRunProfileShowsLiveOutputAndCompletedStatus(t *testing.T) {
	s := fixture(t)
	page := s.page(t)
	page.Goto(s.baseURL)

	card(page, "panel-profiles", greetingName).
		GetByRole(*playwright.AriaRoleButton, playwright.LocatorGetByRoleOptions{Name: "Run"}).Click()

	modal := modalShell(page)
	expectHeadingOn(s, modal, "Profile Run", false)
	s.expectVisible(modal.GetByText("Hello, E2E!"), float64(completionTimeoutMs))
	s.expectVisible(modal.GetByText("Completed",
		playwright.LocatorGetByTextOptions{Exact: playwright.Bool(true)}), float64(completionTimeoutMs))

	modal.GetByRole(*playwright.AriaRoleButton, playwright.LocatorGetByRoleOptions{Name: "Close"}).Click()
	s.expectHidden(modal)
}

func TestProfileRunIsRecordedInHistory(t *testing.T) {
	s := fixture(t)
	page := s.page(t)
	page.Goto(s.baseURL)

	card(page, "panel-profiles", greetingName).
		GetByRole(*playwright.AriaRoleButton, playwright.LocatorGetByRoleOptions{Name: "Run"}).Click()
	modal := modalShell(page)
	s.expectVisible(modal.GetByText("Completed",
		playwright.LocatorGetByTextOptions{Exact: playwright.Bool(true)}), float64(completionTimeoutMs))
	modal.GetByRole(*playwright.AriaRoleButton, playwright.LocatorGetByRoleOptions{Name: "Close"}).Click()

	// The profiles panel polls history every 3s; wait for the new row.
	row := page.Locator("#panel-profiles tbody tr",
		playwright.PageLocatorOptions{HasText: greetingName}).
		Filter(playwright.LocatorFilterOptions{HasText: "completed"}).First()
	s.expectVisible(row, float64(rowWaitTimeoutMs))
}

func TestFailingProfileReportsFailedStatusAndErrorOutput(t *testing.T) {
	s := fixture(t)
	page := s.page(t)
	page.Goto(s.baseURL)

	card(page, "panel-profiles", failingName).
		GetByRole(*playwright.AriaRoleButton, playwright.LocatorGetByRoleOptions{Name: "Run"}).Click()

	modal := modalShell(page)
	expectHeadingOn(s, modal, "Profile Run", false)
	s.expectVisible(modal.GetByText("boom: expected failure"), float64(rowWaitTimeoutMs))
	s.expectVisible(modal.GetByText("Failed",
		playwright.LocatorGetByTextOptions{Exact: playwright.Bool(true)}), float64(rowWaitTimeoutMs))
}

func TestRunWorkflowShowsStepLogAndCompletion(t *testing.T) {
	s := fixture(t)
	page := s.page(t)
	page.Goto(s.baseURL)

	page.GetByRole(*playwright.AriaRoleButton, playwright.PageGetByRoleOptions{Name: "Workflows"}).Click()
	workflowCard := card(page, "panel-workflows", workflowName)
	expectHeadingOn(s, workflowCard, workflowName, false)
	workflowCard.GetByRole(*playwright.AriaRoleButton, playwright.LocatorGetByRoleOptions{Name: "Run"}).Click()

	modal := modalShell(page)
	expectHeadingOn(s, modal, "Workflow Run", false)
	s.expectVisible(modal.GetByText("[RUN] Step 1: E2E Greeting"), float64(rowWaitTimeoutMs))
	s.expectVisible(modal.GetByText("Workflow completed"), float64(completionTimeoutMs))
}

func TestNewProfileModalShowsInlineErrorWhenRequiredFieldsMissing(t *testing.T) {
	s := fixture(t)
	page := s.page(t)
	page.Goto(s.baseURL)

	page.GetByRole(*playwright.AriaRoleButton, playwright.PageGetByRoleOptions{Name: "New Profile"}).Click()
	modal := modalShell(page)
	expectHeadingOn(s, modal, "New Profile", false)

	if err := page.GetByPlaceholder("e.g. Data Pipeline").Fill("E2E Typed"); err != nil {
		t.Fatal(err)
	}
	modal.GetByRole(*playwright.AriaRoleButton, playwright.LocatorGetByRoleOptions{Name: "Save Profile"}).Click()

	// Validation errors appear inline in the modal, never as a native
	// alert().
	s.expectVisibleNow(modal.GetByText("Name and script path are required."))
	expectHeadingOn(s, modal, "New Profile", false)

	modal.GetByRole(*playwright.AriaRoleButton, playwright.LocatorGetByRoleOptions{Name: "Cancel"}).Click()
	s.expectHidden(modal)
}

func TestProfileDeleteRoutesThroughConfirmModal(t *testing.T) {
	s := fixture(t)
	s.api(t, http.MethodPost, "/api/profiles", map[string]any{
		"id":          "profile_e2e_disposable",
		"name":        disposableName,
		"script_path": filepath.Join(s.dataDir, "scripts", "greet.py"),
		"args":        []any{},
		"custom_args": []any{},
	})

	page := s.page(t)
	page.Goto(s.baseURL)
	disposableCard := card(page, "panel-profiles", disposableName)
	s.expectVisibleNow(disposableCard)

	disposableCard.GetByRole(*playwright.AriaRoleButton,
		playwright.LocatorGetByRoleOptions{Name: "Delete", Exact: playwright.Bool(true)}).Click()

	modal := modalShell(page)
	expectHeadingOn(s, modal, "Delete profile", false)
	modal.GetByRole(*playwright.AriaRoleButton,
		playwright.LocatorGetByRoleOptions{Name: "Delete", Exact: playwright.Bool(true)}).Click()

	s.expectHidden(modal)
	s.expectHidden(disposableCard)

	trashedRaw := s.api(t, http.MethodGet, "/api/profiles", nil)
	trashed, ok := trashedRaw.([]any)
	if !ok {
		t.Fatalf("profiles response is not a list: %v", trashedRaw)
	}
	var disposable map[string]any
	for _, item := range trashed {
		p, ok := item.(map[string]any)
		if !ok {
			continue
		}
		if p["id"] == "profile_e2e_disposable" {
			disposable = p
			break
		}
	}
	if disposable == nil {
		t.Fatal("disposable profile not found after delete")
	}
	if disposable["group"] != "__trash__" {
		t.Errorf("group = %v, want __trash__", disposable["group"])
	}
}

func TestAuditPanelListsSeededChanges(t *testing.T) {
	s := fixture(t)
	page := s.page(t)
	page.Goto(s.baseURL)

	page.GetByRole(*playwright.AriaRoleButton, playwright.PageGetByRoleOptions{Name: "Audit"}).Click()
	expectHeading(s, page, "Audit", true)

	profileRow := page.Locator("#panel-audit tbody tr",
		playwright.PageLocatorOptions{HasText: greetingName}).First()
	s.expectVisibleNow(profileRow)
	s.expectVisibleNow(profileRow.Filter(playwright.LocatorFilterOptions{HasText: "Created"}))

	workflowRow := page.Locator("#panel-audit tbody tr",
		playwright.PageLocatorOptions{HasText: workflowName}).First()
	s.expectVisibleNow(workflowRow)
}

func TestLogsPanelShowsLiveServerLog(t *testing.T) {
	s := fixture(t)
	page := s.page(t)
	page.Goto(s.baseURL)

	page.GetByRole(*playwright.AriaRoleButton, playwright.PageGetByRoleOptions{Name: "Logs"}).Click()
	expectHeading(s, page, "Server Logs", true)

	// Page load and API polling generate request lines in the server's
	// own log.
	line := page.Locator("#panel-logs .font-mono > div",
		playwright.PageLocatorOptions{HasText: "GET"}).First()
	s.expectVisible(line, float64(rowWaitTimeoutMs))
}

func TestThemeToggleUpdatesRootClassAndPersists(t *testing.T) {
	s := fixture(t)
	page := s.page(t)
	page.Goto(s.baseURL)
	expectHeading(s, page, "Profiles", true)

	dark, err := page.Evaluate("document.documentElement.classList.contains('dark')")
	if err != nil {
		t.Fatal(err)
	}
	if dark != true {
		t.Errorf("dark class initially = %v, want true", dark)
	}

	page.GetByRole(*playwright.AriaRoleButton, playwright.PageGetByRoleOptions{Name: "Light Mode"}).Click()
	expectHeading(s, page, "Profiles", true)
	s.expectVisibleNow(page.GetByRole(*playwright.AriaRoleButton,
		playwright.PageGetByRoleOptions{Name: "Dark Mode"}).First())
	dark, err = page.Evaluate("document.documentElement.classList.contains('dark')")
	if err != nil {
		t.Fatal(err)
	}
	if dark != false {
		t.Errorf("dark class after Light Mode = %v, want false", dark)
	}
	theme, err := page.Evaluate("localStorage.getItem('theme')")
	if err != nil {
		t.Fatal(err)
	}
	if theme != "light" {
		t.Errorf("localStorage theme = %v, want light", theme)
	}

	page.GetByRole(*playwright.AriaRoleButton, playwright.PageGetByRoleOptions{Name: "Dark Mode"}).Click()
	s.expectVisibleNow(page.GetByRole(*playwright.AriaRoleButton,
		playwright.PageGetByRoleOptions{Name: "Light Mode"}).First())
	dark, err = page.Evaluate("document.documentElement.classList.contains('dark')")
	if err != nil {
		t.Fatal(err)
	}
	if dark != true {
		t.Errorf("dark class after Dark Mode = %v, want true", dark)
	}
	theme, err = page.Evaluate("localStorage.getItem('theme')")
	if err != nil {
		t.Fatal(err)
	}
	if theme != "dark" {
		t.Errorf("localStorage theme = %v, want dark", theme)
	}
}

func TestSchedulesPanelShowsScheduleAndCardBadge(t *testing.T) {
	s := fixture(t)
	createdRaw := s.api(t, http.MethodPost, "/api/schedules", map[string]any{
		"name":        "Hourly greeting",
		"target_type": "profile",
		"target_id":   s.greetingID,
		"cron":        "0 * * * *",
		"enabled":     true,
	})
	created, _ := createdRaw.(map[string]any)
	t.Cleanup(func() {
		createdID, _ := created["id"].(string)
		s.api(t, http.MethodDelete, "/api/schedules/"+createdID, nil)
	})

	page := s.page(t)
	page.Goto(s.baseURL)

	page.GetByRole(*playwright.AriaRoleButton, playwright.PageGetByRoleOptions{Name: "Schedules"}).Click()
	panelLoc := page.Locator("#panel-schedules")
	s.expectVisibleNow(panelLoc.GetByRole(*playwright.AriaRoleHeading,
		playwright.LocatorGetByRoleOptions{Name: "Hourly greeting"}))
	s.expectVisibleNow(panelLoc.GetByText("Every hour",
		playwright.LocatorGetByTextOptions{Exact: playwright.Bool(true)}))
	s.expectVisibleNow(panelLoc.GetByText("Next:"))
	// The profile card advertises its schedule back on the Profiles panel.
	page.GetByRole(*playwright.AriaRoleButton, playwright.PageGetByRoleOptions{Name: "Profiles"}).Click()
	greetingCard := card(page, "panel-profiles", greetingName)
	s.expectVisibleNow(greetingCard.GetByText("Scheduled"))
}

func TestScheduleModalRepeatBuilderCompilesAndPreviews(t *testing.T) {
	s := fixture(t)
	page := s.page(t)
	page.Goto(s.baseURL)

	page.GetByRole(*playwright.AriaRoleButton, playwright.PageGetByRoleOptions{Name: "Schedules"}).Click()
	page.GetByRole(*playwright.AriaRoleButton, playwright.PageGetByRoleOptions{Name: "New Schedule"}).Click()
	modal := modalShell(page)

	// Default preset: repeat every 30 minutes, compiled to cron with a
	// live preview.
	numberInput := modal.Locator("input[type='number']").First()
	if err := s.assert.Locator(numberInput).ToHaveValue("30"); err != nil {
		t.Fatal(err)
	}
	s.expectVisibleNow(modal.GetByText("*/30 * * * *",
		playwright.LocatorGetByTextOptions{Exact: playwright.Bool(true)}))
	s.expectVisibleNow(modal.GetByText("Every 30 minutes",
		playwright.LocatorGetByTextOptions{Exact: playwright.Bool(true)}))

	numberInput.Fill("7")
	s.expectVisibleNow(modal.GetByText("*/7 * * * *",
		playwright.LocatorGetByTextOptions{Exact: playwright.Bool(true)}))
	s.expectVisibleNow(modal.GetByText("Every 7 minutes",
		playwright.LocatorGetByTextOptions{Exact: playwright.Bool(true)}))

	unitSelect := modal.Locator("select").Nth(2)
	// The modal re-renders its controls after the Fill above, and the
	// driver's SelectOption keeps resolving the pre-render <option>
	// nodes ("did not find some options"). Driving the change event
	// directly matches what a real choice does: set the value, let the
	// app's onChange handler run.
	if _, err := unitSelect.Evaluate("el => { el.value = 'hours'; el.dispatchEvent(new Event('change', { bubbles: true })); }", nil); err != nil {
		t.Fatal(err)
	}
	s.expectVisibleNow(modal.GetByText("0 */7 * * *",
		playwright.LocatorGetByTextOptions{Exact: playwright.Bool(true)}))
	s.expectVisibleNow(modal.GetByText("Every 7 hours",
		playwright.LocatorGetByTextOptions{Exact: playwright.Bool(true)}))
}

// fixture returns the once-initialized suite lazily so individual
// tests can also skip when tooling is missing (e.g. browser removed
// after TestMain passed).
func fixture(t *testing.T) *e2eSuite {
	t.Helper()
	if suiteHeld == nil {
		t.Fatal("e2e fixture not initialized")
	}
	s := suiteHeld
	s.t = t
	return s
}
