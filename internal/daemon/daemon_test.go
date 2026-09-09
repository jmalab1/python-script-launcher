package daemon

import (
	"os"
	"os/exec"
	"runtime"
	"syscall"
	"testing"
)

func TestPIDBookkeeping(t *testing.T) {
	t.Setenv("LAUNCHER_DATA_DIR", t.TempDir())
	if _, ok := ReadPID(8765); ok {
		t.Fatal("no pid file yet, ReadPID should fail")
	}
	if _, running := IsRunning(8765); running {
		t.Fatal("nothing started, IsRunning should be false")
	}
	// Files are scoped per port: one port's state never touches another's.
	if err := writePID(8765, 123456); err != nil {
		t.Fatal(err)
	}
	if _, running := IsRunning(9000); running {
		t.Fatal("another port must not see this instance")
	}
	if err := writePID(8765, 999999); err != nil {
		t.Fatal(err)
	}

	// A pid file pointing at a dead process is cleaned up and reports
	// not-running.
	if _, running := IsRunning(8765); running {
		t.Fatal("stale pid should not count as running")
	}
	if _, err := os.Stat(PIDFile(8765)); !os.IsNotExist(err) {
		t.Fatal("stale pid file should have been removed")
	}
}

// TestStopKillsSpawnedProcess exercises Stop end to end against a real
// long-running child (unix only: it relies on SIGTERM semantics).
func TestStopKillsSpawnedProcess(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("unix-only test (uses /bin/sleep + SIGTERM)")
	}
	t.Setenv("LAUNCHER_DATA_DIR", t.TempDir())
	proc := exec.Command("/bin/sleep", "60")
	if err := proc.Start(); err != nil {
		t.Skipf("cannot spawn sleep: %v", err)
	}
	pid := proc.Process.Pid
	if err := writePID(8765, pid); err != nil {
		t.Fatal(err)
	}

	stopped, err := Stop(8765)
	if err != nil || !stopped {
		t.Fatalf("Stop: stopped=%v err=%v", stopped, err)
	}
	stillAlive := func() bool {
		target, err := os.FindProcess(pid)
		if err != nil {
			return false
		}
		return target.Signal(syscall.Signal(0)) == nil
	}
	if stillAlive() {
		t.Error("Stop did not terminate the spawned process")
	}
	if _, running := IsRunning(8765); running {
		t.Error("pid file should be removed after Stop")
	}
	// cmd.Wait to reap (may already be reaped by Stop; either is fine).
	_ = proc.Wait()
}
