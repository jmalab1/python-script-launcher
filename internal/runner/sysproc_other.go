//go:build !windows

package runner

import "os/exec"

// setSysProcAttr is a no-op off Windows; the Windows build hides the
// child console window like Python's CREATE_NO_WINDOW did.
func setSysProcAttr(cmd *exec.Cmd) {}
