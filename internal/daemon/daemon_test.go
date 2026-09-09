package daemon

import (
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"testing"
	"time"
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

// TestRecordPID: the pid file lands in the data dir, holds the plain
// decimal pid, and reads back through ReadPID.
func TestRecordPID(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("LAUNCHER_DATA_DIR", dir)

	if err := RecordPID(8765, 4242); err != nil {
		t.Fatalf("RecordPID: %v", err)
	}
	if want := filepath.Join(dir, "launcher-8765.pid"); PIDFile(8765) != want {
		t.Errorf("PIDFile = %q, want %q", PIDFile(8765), want)
	}
	raw, err := os.ReadFile(PIDFile(8765))
	if err != nil {
		t.Fatal(err)
	}
	if string(raw) != "4242" {
		t.Errorf("pid file content = %q, want \"4242\"", raw)
	}
	if pid, ok := ReadPID(8765); !ok || pid != 4242 {
		t.Errorf("ReadPID = (%d, %v), want (4242, true)", pid, ok)
	}
}

// TestPortOpen: a port held by a listener counts as open; the same port
// right after the listener closes does not.
func TestPortOpen(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("grab a free port: %v", err)
	}
	port := ln.Addr().(*net.TCPAddr).Port

	if !PortOpen(port) {
		t.Errorf("PortOpen(%d) = false while a listener holds the port", port)
	}
	if err := ln.Close(); err != nil {
		t.Fatal(err)
	}
	if PortOpen(port) {
		t.Errorf("PortOpen(%d) = true after the listener closed", port)
	}
}

// TestStartDetachedBadExecutable: a missing binary fails fast, before
// any readiness wait, and no process is left behind.
func TestStartDetachedBadExecutable(t *testing.T) {
	exe := filepath.Join(t.TempDir(), "no-such-launchctl")
	if _, err := StartDetached(exe, nil, nil, 50*time.Millisecond, func() bool { return false }); err == nil {
		t.Fatal("starting a nonexistent executable should fail")
	}
}

// TestStartDetachedChildDiesImmediately: when the child exits before
// becoming ready, the error says so. It spawns a plain `sleep 0`, not
// the real server, and the wait goroutine reaps it, so nothing lingers.
func TestStartDetachedChildDiesImmediately(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("unix-only test (uses /bin/sleep)")
	}
	sleep, err := exec.LookPath("sleep")
	if err != nil {
		t.Skipf("no sleep binary on PATH: %v", err)
	}

	_, err = StartDetached(sleep, []string{"0"}, nil, 5*time.Second, func() bool { return false })
	if err == nil {
		t.Fatal("a child that exits before ready should be an error")
	}
	if !strings.Contains(err.Error(), "exited immediately") {
		t.Errorf("unexpected error: %v", err)
	}
}

// TestStartDetachedHappyPathIsE2ECovered documents the deliberate gap:
// the happy path spawns the real detached server, which the unit tests
// cannot reliably clean up, so it is left to tests/e2e.
func TestStartDetachedHappyPathIsE2ECovered(t *testing.T) {
	t.Skip("StartDetached's happy path spawns the real detached server; covered by tests/e2e")
}
