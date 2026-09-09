package runner

import (
	"os/exec"
	"testing"
)

// TestSetSysProcAttr checks the process setup helper runs cleanly on
// this platform: it only sets builder options before exec, so calling
// it once must not panic.
func TestSetSysProcAttr(t *testing.T) {
	setSysProcAttr(&exec.Cmd{})
}
