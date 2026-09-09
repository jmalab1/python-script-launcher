// Package devtools is shared plumbing for the developer tools under
// cmd/: it boots the compiled launcher server on a free port with a
// throwaway data directory and gives the tools a tiny JSON client for
// its HTTP API. Nothing here is used by the app itself.
package devtools

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"time"
)

// readyPoll is how often BootServer re-checks whether the server is
// answering yet.
const readyPoll = 100 * time.Millisecond

// readyTimeout is how long BootServer waits for the first successful
// API response before giving up.
const readyTimeout = 15 * time.Second

// Server is one launcher binary running in the foreground, started by
// BootServer and stopped again with Stop.
type Server struct {
	// BaseURL is where the server answers, e.g. http://127.0.0.1:8765.
	BaseURL string
	// LogPath is the file the server's own log output goes to. Reads
	// from it when reporting why the server never came up.
	LogPath string

	cmd *exec.Cmd
}

// RepoRoot walks up from the working directory until it finds go.mod,
// so the tools work no matter which subdirectory they were started
// from. It fails when there is no repo above the current directory.
func RepoRoot() (string, error) {
	dir, err := filepath.Abs(".")
	if err != nil {
		return "", err
	}
	for {
		if _, err := os.Stat(filepath.Join(dir, "go.mod")); err == nil {
			return dir, nil
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return "", fmt.Errorf("no repo root (go.mod) found above %s - run the tool from inside the repo", dir)
		}
		dir = parent
	}
}

// FreePort asks the kernel for an unused TCP port on localhost. The
// listener is closed again right away, so the caller's server can bind
// the same port a moment later.
func FreePort() (int, error) {
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return 0, err
	}
	defer l.Close()
	return l.Addr().(*net.TCPAddr).Port, nil
}

// BootServer starts dist/launchctl on the given port with its data
// directory pointed at dataDir. If the binary is missing it is built
// first, the same way the e2e suite does. It returns once the server
// answers /api/profiles.
func BootServer(repoRoot string, port int, dataDir string) (*Server, error) {
	bin := filepath.Join(repoRoot, "dist", "launchctl")

	if _, err := os.Stat(bin); os.IsNotExist(err) {
		// Building the app's own binary from inside the repo; the
		// command and args are fixed, only the output path varies.
		build := exec.Command("go", "build", "-o", bin, "./cmd/launcher") //#nosec G204 -- fixed args, repo-internal output path
		build.Dir = repoRoot
		build.Stdout, build.Stderr = os.Stdout, os.Stderr
		if err := build.Run(); err != nil {
			return nil, fmt.Errorf("building the server failed: %w", err)
		}
	}

	logPath := filepath.Join(dataDir, "server.log")
	logFile, err := os.Create(logPath) //#nosec G304 -- log path built from the tool-owned temp data dir
	if err != nil {
		return nil, err
	}
	defer logFile.Close()

	// Same as above: the app's own binary with fixed flag arguments.
	cmd := exec.Command(bin, "-port", fmt.Sprint(port), "-foreground") //#nosec G204 -- repo-internal binary, fixed args
	cmd.Dir = repoRoot
	cmd.Env = append(os.Environ(), "LAUNCHER_DATA_DIR="+dataDir)
	cmd.Stdout, cmd.Stderr = logFile, logFile
	if err := cmd.Start(); err != nil {
		return nil, err
	}

	s := &Server{
		BaseURL: fmt.Sprintf("http://127.0.0.1:%d", port),
		LogPath: logPath,
		cmd:     cmd,
	}

	if err := waitReady(s.BaseURL, readyTimeout); err != nil {
		s.Stop()
		return nil, err
	}
	return s, nil
}

// Stop ends the server: first politely, then hard after a grace
// period, like the e2e suite does.
func (s *Server) Stop() {
	if s.cmd == nil || s.cmd.Process == nil {
		return
	}
	_ = s.cmd.Process.Signal(os.Interrupt)
	done := make(chan struct{})
	go func() { _ = s.cmd.Wait(); close(done) }()
	select {
	case <-done:
	case <-time.After(10 * time.Second):
		_ = s.cmd.Process.Kill()
		<-done
	}
}

// waitReady polls /api/profiles until the server answers with 200 OK,
// or the deadline passes.
func waitReady(baseURL string, timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	for {
		resp, err := http.Get(baseURL + "/api/profiles") //nolint:gosec,noctx // local dev server
		if err == nil {
			_ = resp.Body.Close()
			if resp.StatusCode == http.StatusOK {
				return nil
			}
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("server did not start")
		}
		time.Sleep(readyPoll)
	}
}

// APIRequest is the tiny JSON client the tools use to seed data. The
// response body is decoded into any: list endpoints return JSON
// arrays, single resources return JSON objects.
func APIRequest(baseURL, method, path string, payload any) (any, error) {
	var body io.Reader
	if payload != nil {
		raw, err := json.Marshal(payload)
		if err != nil {
			return nil, err
		}
		body = bytes.NewReader(raw)
	}

	req, err := http.NewRequest(method, baseURL+path, body)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("%s %s: status %d: %s", method, path, resp.StatusCode, raw)
	}

	var out any
	if err := json.Unmarshal(raw, &out); err != nil {
		return nil, fmt.Errorf("decoding %s %s response: %w", method, path, err)
	}
	return out, nil
}
