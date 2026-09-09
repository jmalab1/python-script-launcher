//go:build windows

package main

import "os/exec"

// openBrowser opens the UI in the default browser via the shell, the
// way webbrowser.open did.
func openBrowser(url string) {
	exec.Command("cmd", "/c", "start", url).Start()
}
