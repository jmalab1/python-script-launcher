// Command screencast records a demo tour of the launcher UI with
// Playwright.
//
// It boots the compiled server (dist/launchctl) on a free port with a
// throwaway data directory, seeds it with tagged profiles, workflows
// and schedules built from the example scripts, then drives the
// browser through a guided tour while recording video.
//
// The finished recording is written to demo/launcher_demo.webm by
// default:
//
//	make demo
//	go run ./cmd/screencast --output demo/tour.webm --headed
//
// Requires the Chromium driver, installed once like for the e2e suite:
//
//	go run github.com/mxschmitt/playwright-go/cmd/playwright install chromium
//
// This is a dev tool only — the app itself never imports it.
package main

import (
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"

	"github.com/mxschmitt/playwright-go"

	"launchcontrol/internal/devtools"
)

// Example scripts (scripts/testing) the seeded profiles point at.
const demoScriptsDir = "scripts" + string(os.PathSeparator) + "testing"

// workflowCompletionTimeoutMs is how long to wait for a full workflow
// run: several real Python child scripts have to execute before the
// "Workflow completed" banner can appear.
const workflowCompletionTimeoutMs = 20000.0

func main() {
	err := run(os.Args[1:])
	if err == nil {
		return
	}
	fmt.Fprintln(os.Stderr, "screencast:", err)
	os.Exit(1)
}

func run(args []string) error {
	output := flag.String("output", "demo/launcher_demo.webm", "where to write the .webm video")
	headed := flag.Bool("headed", false, "watch the browser while recording")
	pause := flag.Float64("pause", 1.0, "seconds to linger on each step")
	if err := flag.CommandLine.Parse(args); err != nil {
		return err
	}

	root, err := devtools.RepoRoot()
	if err != nil {
		return err
	}
	outPath, err := resolveOutput(root, *output)
	if err != nil {
		return err
	}

	dataDir, err := os.MkdirTemp("", "launcher-demo-")
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

	seeded, err := seed(srv.BaseURL, filepath.Join(root, "scripts", "testing"))
	if err != nil {
		return err
	}
	fmt.Printf("Seeded %d profiles on %s\n", len(seeded), srv.BaseURL)

	videoDir := filepath.Join(dataDir, "video")
	if err := os.MkdirAll(videoDir, 0o750); err != nil {
		return err
	}

	if err := recordTour(srv.BaseURL, videoDir, outPath, *headed, *pause*1000); err != nil {
		return err
	}
	fmt.Printf("Screencast written to %s\n", outPath)
	return nil
}

// resolveOutput makes relative output paths land in the repo (where
// the Makefile and git expect them).
func resolveOutput(root, output string) (string, error) {
	path := output
	if !filepath.IsAbs(path) {
		path = filepath.Join(root, path)
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o750); err != nil {
		return "", err
	}
	return path, nil
}

// recordTour launches a fresh Chromium, records the tour as a webm
// video, and moves the finished file to outputPath when done.
func recordTour(baseURL, videoDir, outputPath string, headed bool, pauseMs float64) error {
	pw, err := playwright.Run()
	if err != nil {
		return fmt.Errorf("playwright run (installed the driver?): %w", err)
	}
	defer pw.Stop()

	browser, err := pw.Chromium.Launch(playwright.BrowserTypeLaunchOptions{
		Headless: playwright.Bool(!headed),
	})
	if err != nil {
		return err
	}
	defer browser.Close()

	// Demo profiles and workflows carry tag ids ("tag_reports", ...);
	// the human-readable tag list lives in the browser's localStorage,
	// so it is injected before any page script runs.
	ctx, err := browser.NewContext(playwright.BrowserNewContextOptions{
		Viewport: &playwright.Size{Width: 1600, Height: 900},
		RecordVideo: &playwright.RecordVideo{
			Dir:  playwright.String(videoDir),
			Size: &playwright.Size{Width: 1600, Height: 900},
		},
	})
	if err != nil {
		return err
	}
	if err := ctx.AddInitScript(playwright.Script{Content: playwright.String(
		`localStorage.setItem('tags', JSON.stringify([` +
			`{ id: 'tag_reports', name: 'Reports', color: 'sky' },` +
			`{ id: 'tag_data', name: 'Data', color: 'violet' },` +
			`{ id: 'tag_ops', name: 'Ops', color: 'amber' },` +
			`]));`)}); err != nil {
		return err
	}

	page, err := ctx.NewPage()
	if err != nil {
		return err
	}
	if err := tour(page, baseURL, pauseMs); err != nil {
		return err
	}

	// Closing the context finalizes the video file that was written
	// while recording.
	videoPath, err := page.Video().Path()
	if err != nil {
		return err
	}
	if err := ctx.Close(); err != nil {
		return err
	}
	if err := copyFile(videoPath, outputPath); err != nil {
		return err
	}
	return browser.Close()
}

// copyFile moves the recording to its destination. Copy-plus-delete
// instead of a rename because the temp data dir may sit on another
// filesystem than the repo.
func copyFile(src, dst string) error {
	in, err := os.Open(src) //#nosec G304 -- the recording path comes from playwright's own temp dir
	if err != nil {
		return err
	}
	defer in.Close()

	out, err := os.Create(dst) //#nosec G304 -- the destination is the user-chosen output path
	if err != nil {
		return err
	}
	defer out.Close()

	if _, err := io.Copy(out, in); err != nil {
		return err
	}
	return os.Remove(src)
}
