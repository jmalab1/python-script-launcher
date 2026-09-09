//go:build windows

package main

import "os/exec"

// openBrowser opens the UI in the default browser via the shell, the
// way webbrowser.open did. The shell process is awaited in the
// background (it returns quickly) so it cannot linger unreaped.
func openBrowser(url string) {
	// #nosec G204 -- the command is the fixed Windows shell opener and
	// url is the app's own http://127.0.0.1:<port> address.
	startAndReap(exec.Command("cmd", "/c", "start", url))
}
