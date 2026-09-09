// Package daemon gives the compiled launcher a built-in detach mode:
// "./launchctl" spawns itself as a setsid background child, waits until
// the server answers on its port, records the child's PID and exits —
// so closing the terminal never kills the app. "-stop" reverses it.
package daemon

import (
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"syscall"
	"time"

	"launchcontrol/internal/config"
)

// PIDFile records the detached server listening on `port`; one file
// per port keeps instances and their stop targets apart.
func PIDFile(port int) string {
	return filepath.Join(config.DataDir(), fmt.Sprintf("launcher-%d.pid", port))
}

// ReadPID returns the recorded PID for the port, or false when there
// is none.
func ReadPID(port int) (int, bool) {
	raw, err := os.ReadFile(PIDFile(port))
	if err != nil {
		return 0, false
	}
	pid, err := strconv.Atoi(string(raw))
	if err != nil || pid <= 0 {
		return 0, false
	}
	return pid, true
}

// RecordPID records the pid of the detached server listening on the
// given port (the parent right after spawning it).
func RecordPID(port, pid int) error { return writePID(port, pid) }

// writePID records the pid.
func writePID(port, pid int) error {
	return os.WriteFile(PIDFile(port), []byte(strconv.Itoa(pid)), 0o600)
}

// alive reports whether a process still exists (does not distinguish
// zombies; good enough for this app's bookkeeping).
func alive(pid int) bool {
	if runtime.GOOS == "windows" {
		// No Signal(0) probe on Windows; a recorded PID is assumed alive
		// and Stop removes the file when the kill fails.
		return true
	}
	proc, err := os.FindProcess(pid)
	if err != nil {
		return false
	}
	return proc.Signal(syscall.Signal(0)) == nil
}

// IsRunning reports the live PID of the previously detached server on
// the given port, if any (stale pid files are cleaned up here).
func IsRunning(port int) (int, bool) {
	pid, ok := ReadPID(port)
	if !ok {
		return 0, false
	}
	if !alive(pid) {
		// A stale PID file is best-effort cleanup; nothing useful can
		// be done if the remove fails.
		_ = os.Remove(PIDFile(port))
		return 0, false
	}
	return pid, true
}

// PortOpen checks whether something already answers on 127.0.0.1:port.
func PortOpen(port int) bool {
	conn, err := net.DialTimeout("tcp", net.JoinHostPort("127.0.0.1", strconv.Itoa(port)), 300*time.Millisecond)
	if err != nil {
		return false
	}
	_ = conn.Close()
	return true
}

// StartDetached spawns the binary as an independent background server
// and waits until ready() reports success (or the timeout elapses).
// Returns the child PID.
func StartDetached(exe string, args []string, env []string, timeout time.Duration, ready func() bool) (int, error) {
	// #nosec G204 -- exe is this binary's own path (os.Executable) and
	// args are the fixed -port/-_child flags built by main().
	cmd := exec.Command(exe, args...)
	cmd.Env = env
	// The child must not die with the parent's session/terminal.
	setDetached(cmd)
	if err := cmd.Start(); err != nil {
		return 0, err
	}
	pid := cmd.Process.Pid
	waitCh := make(chan error, 1) // reaped by this goroutine
	go func() { waitCh <- cmd.Wait() }()
	deadline := time.Now().Add(timeout)
	for {
		if ready() {
			return pid, nil
		}
		select {
		case waitErr := <-waitCh:
			return 0, fmt.Errorf("server process exited immediately (%v); see data/server.log", waitErr)
		default:
		}
		if time.Now().After(deadline) {
			return 0, fmt.Errorf("server did not become ready within %v; see data/server.log", timeout)
		}
		time.Sleep(100 * time.Millisecond)
	}
}

// Stop terminates the detached server recorded for the port. Returns
// whether something was actually running.
func Stop(port int) (bool, error) {
	pid, ok := IsRunning(port)
	if !ok {
		return false, nil
	}
	proc, err := os.FindProcess(pid)
	if err != nil {
		_ = os.Remove(PIDFile(port))
		return false, nil
	}

	// Ask nicely first, then force after a short grace period.
	if signalErr := proc.Signal(syscall.SIGTERM); signalErr == nil && runtime.GOOS != "windows" {
		exited := make(chan error, 1)
		go func() {
			_, waitErr := proc.Wait()
			exited <- waitErr
		}()
		select {
		case <-exited:
		case <-time.After(3 * time.Second):
			_ = proc.Kill()
			<-exited
		}
	} else {
		_ = proc.Kill()
	}
	_ = os.Remove(PIDFile(port))
	return true, nil
}
