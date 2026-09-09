package main

import (
	"net/http"
	"net/http/httptest"
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
