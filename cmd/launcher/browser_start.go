package main

import "os/exec"

// startAndReap launches cmd without waiting, then reaps it in the
// background once it exits, so it cannot linger as a zombie child of
// the long-running server. Reports whether the command was started.
func startAndReap(cmd *exec.Cmd) bool {
	if err := cmd.Start(); err != nil {
		return false
	}
	go func() { _ = cmd.Wait() }()
	return true
}
