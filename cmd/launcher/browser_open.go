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
		// #nosec G204 -- the command is the fixed platform opener and
		// url is the app's own http://127.0.0.1:<port> address.
		_ = exec.Command("open", url).Start()
	default:
		// #nosec G204 -- the command is the fixed platform opener and
		// url is the app's own http://127.0.0.1:<port> address.
		_ = exec.Command("xdg-open", url).Start()
	}
}
