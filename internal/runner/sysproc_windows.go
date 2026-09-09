//go:build windows

package runner

import (
	"os/exec"
	"syscall"
)

// On Windows a script started from a windowless binary would otherwise
// flash a console window per run; CREATE_NO_WINDOW (0x08000000) plus
// HideWindow suppresses that, matching the Python Popen creationflags.
func setSysProcAttr(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{
		HideWindow:    true,
		CreationFlags: 0x08000000,
	}
}
