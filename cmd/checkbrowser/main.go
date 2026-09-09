// Command checkbrowser is a quick manual check: the profile editor's
// Browse button opens the in-app file explorer and can pick a script.
// Not part of the test suite (it mirrors what a user would click
// through); run after UI changes:
//
//	make check-browser
//
// It needs the Chromium driver installed once, like the e2e suite:
//
//	go run github.com/mxschmitt/playwright-go/cmd/playwright install chromium
package main

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/mxschmitt/playwright-go"

	"launchcontrol/internal/devtools"
)

// The directory levels the check double-clicks through, ending at the
// example scripts the file picker should reach.
var descendPath = []string{"dev", "python-web-launcher", "scripts", "testing"}

// pickTimeout bounds wait steps: set on the browser context so every
// locator call waits up to 5s before failing.
const pickTimeout = 5000.0

func main() {
	err := run()
	if err == nil {
		fmt.Println("file picker OK: browsed to scripts/testing and selected test_script.py")
		return
	}
	fmt.Fprintln(os.Stderr, "checkbrowser:", err)
	os.Exit(1)
}

func run() error {
	root, err := devtools.RepoRoot()
	if err != nil {
		return err
	}
	dataDir, err := os.MkdirTemp("", "browser-check-")
	if err != nil {
		return err
	}
	defer os.RemoveAll(dataDir)

	port, err := devtools.FreePort()
	if err != nil {
		return err
	}
	srv, err := devtools.BootServer(root, port, dataDir)
	if err != nil {
		return err
	}
	defer srv.Stop()

	pw, err := playwright.Run()
	if err != nil {
		return fmt.Errorf("playwright run (installed the driver?): %w", err)
	}
	defer pw.Stop()

	browser, err := pw.Chromium.Launch()
	if err != nil {
		return err
	}
	defer browser.Close()

	page, err := browser.NewPage()
	if err != nil {
		return err
	}
	page.SetDefaultTimeout(pickTimeout)

	want := filepath.Join(root, "scripts", "testing", "test_script.py")
	return drivePicker(page, srv.BaseURL, want)
}

// drivePicker walks the file explorer from its Home listing down to
// scripts/testing, selects test_script.py, and verifies the profile
// editor's path field picked it up.
func drivePicker(page playwright.Page, baseURL, wantPath string) error {
	pickedScript := filepath.Base(wantPath)

	if _, err := page.Goto(baseURL); err != nil {
		return err
	}
	if err := clickButton(page, "New Profile"); err != nil {
		return err
	}
	if err := clickButton(page, "Browse"); err != nil {
		return err
	}
	if err := waitHeading(page, "Select Python Script"); err != nil {
		return err
	}

	// Navigate Home -> dev -> ... -> testing, waiting for each listing
	// to load (the cwd badge updates when the new directory arrives).
	for _, dir := range descendPath {
		if err := descend(page, dir); err != nil {
			return err
		}
	}

	item := page.Locator("li button", playwright.PageLocatorOptions{HasText: pickedScript}).First()
	if err := item.WaitFor(); err != nil {
		return err
	}
	if err := item.Click(); err != nil {
		return err
	}
	page.WaitForTimeout(200)

	// One click selects the row; Use the Select button. It must be
	// enabled now, and picking it fills the readonly path field.
	useBtn := page.GetByRole(*playwright.AriaRoleButton,
		playwright.PageGetByRoleOptions{Name: "Select", Exact: playwright.Bool(true)})
	if err := useBtn.WaitFor(); err != nil {
		return err
	}
	if disabled, err := useBtn.IsDisabled(); err != nil {
		return err
	} else if disabled {
		return errors.New("Select button should be enabled after picking a script")
	}
	if err := useBtn.Click(); err != nil {
		return err
	}
	return verifyPickedPath(page, wantPath)
}

// inputFieldCheck finishing drivePicker: picking the script fills the
// profile editor's readonly path field.
func verifyPickedPath(page playwright.Page, wantPath string) error {
	got, err := page.Locator(`input[placeholder="No file selected"]`).First().InputValue()
	if err != nil {
		return err
	}
	if !strings.Contains(got, wantPath) {
		return fmt.Errorf("path not filled: got %q, want %q", got, wantPath)
	}
	return nil
}

// descend double-clicks one directory row and waits for the cwd badge
// to change, so the next listing is actually rendered.
func descend(page playwright.Page, dir string) error {
	badge := page.Locator("span.font-mono").First()
	before, err := badge.TextContent()
	if err != nil {
		before = ""
	}

	row := page.Locator("li button", playwright.PageLocatorOptions{HasText: dir}).First()
	if err := row.Dblclick(); err != nil {
		return err
	}

	deadline := time.Now().Add(5 * time.Second)
	for {
		now, err := badge.TextContent()
		if err == nil && now != before {
			return nil
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("file browser cwd badge did not change after opening %q", dir)
		}
		page.WaitForTimeout(100)
	}
}

// waitHeading waits for a role=heading with the given name to appear.
func waitHeading(page playwright.Page, name string) error {
	return page.GetByRole(*playwright.AriaRoleHeading,
		playwright.PageGetByRoleOptions{Name: name}).WaitFor()
}

// clickButton clicks a role=button with the given name on the page,
// taking the first match.
func clickButton(page playwright.Page, name string) error {
	return page.GetByRole(*playwright.AriaRoleButton,
		playwright.PageGetByRoleOptions{Name: name}).First().Click()
}
