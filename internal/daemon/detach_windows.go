//go:build windows

package daemon

import (
	"os/exec"
	"syscall"
)

// Windows process-creation flags. DETACHED_PROCESS means the child gets
// no console at all (so no console window is tied to the server), and
// CREATE_NEW_PROCESS_GROUP keeps it out of the caller's Ctrl+C group.
const (
	createDetachedProcess = 0x00000008
	createNewProcessGroup = 0x00000200
)

// setDetached starts the child without a console window and in its own
// process group, so closing the terminal never kills it — the parent
// exits right after the child is up and serving.
func setDetached(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{
		CreationFlags: createDetachedProcess | createNewProcessGroup,
	}
}
