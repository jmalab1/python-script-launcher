package main

import (
	"net/http"
	"net/http/httptest"
	"os/exec"
	"runtime"
	"slices"
	"testing"
	"time"
)

// TestNewServerSetsHeaderTimeout guards the main server's hop-by-hop
// timeouts: without a ReadHeaderTimeout a client that never finishes
// sending request headers can hold a connection open forever.
func TestNewServerSetsHeaderTimeout(t *testing.T) {
	handler := http.NewServeMux()
	server := newServer(handler)

	if server.Handler != handler {
		t.Error("newServer did not keep the handler")
	}
	if server.ReadHeaderTimeout <= 0 {
		t.Errorf("ReadHeaderTimeout = %v, want > 0", server.ReadHeaderTimeout)
	}
	if server.ReadHeaderTimeout > 30*time.Second {
		t.Errorf("ReadHeaderTimeout = %v, unreasonably long", server.ReadHeaderTimeout)
	}
}

// TestNewServerServes verifies the server object actually responds
// (a plain wiring smoke test).
func TestNewServerServes(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	server := newServer(mux)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	server.Handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", rec.Code, http.StatusOK)
	}
}

// TestBuildChildArgs verifies the detached child is always told to
// open the browser - every launch, including a restart over a running
// instance, should bring the UI up.
func TestBuildChildArgs(t *testing.T) {
	args := buildChildArgs(8765)
	want := []string{"-port", "8765", "-_child", "-_browser"}
	if !slices.Equal(args, want) {
		t.Errorf("args = %v, want %v", args, want)
	}
}

// TestStartAndReap verifies the browser opener helper starts the
// command and reaps it after exit (no zombie child left behind), and
// reports failure for a command that cannot even be started. Uses a
// no-op command instead of a real browser opener so nothing pops up
// while the tests run.
func TestStartAndReap(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("uses a unix no-op command")
	}
	if !startAndReap(exec.Command("true")) {
		t.Fatal("startAndReap could not start `true`")
	}

	if startAndReap(exec.Command("/nonexistent-binary-xyz")) {
		t.Error("startAndReap reported success for a missing command")
	}
}
