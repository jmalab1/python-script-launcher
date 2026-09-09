//go:build !windows

package main

import (
	"os/exec"
	"runtime"
)

// openBrowser opens the UI in the default browser (unused off Windows;
// provided for portability and tests).
func openBrowser(url string) {
	switch runtime.GOOS {
	case "darwin":
		exec.Command("open", url).Start()
	default:
		exec.Command("xdg-open", url).Start()
	}
}
