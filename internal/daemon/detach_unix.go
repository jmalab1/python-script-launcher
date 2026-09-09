//go:build !windows

package daemon

import "os/exec"
import "syscall"

// setDetached puts the child in its own session so it survives the
// terminal closing, like a classic unix double-fork.
func setDetached(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
}
