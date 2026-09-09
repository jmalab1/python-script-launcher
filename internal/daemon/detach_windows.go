//go:build windows

package daemon

import "os/exec"

// setDetached is a no-op on Windows: console programs already detach
// from the caller's lifetime, and the launcher runs in the foreground
// there anyway.
func setDetached(cmd *exec.Cmd) {}
