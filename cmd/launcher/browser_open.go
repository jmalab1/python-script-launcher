//go:build !windows

package main

import (
	"os/exec"
	"runtime"
)

// openBrowser opens the UI in the default browser (all platforms; the
// caller decides when, e.g. on a first launch).
func openBrowser(url string) {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "darwin":
		// #nosec G204 -- the command is the fixed platform opener and
		// url is the app's own http://127.0.0.1:<port> address.
		cmd = exec.Command("open", url)
	default:
		// #nosec G204 -- the command is the fixed platform opener and
		// url is the app's own http://127.0.0.1:<port> address.
		cmd = exec.Command("xdg-open", url)
	}
	startAndReap(cmd)
}
