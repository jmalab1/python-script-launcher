package devtools

import (
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestRepoRootFindsGoMod(t *testing.T) {
	// The package itself lives somewhere under the repo.
	root, err := RepoRoot()
	if err != nil {
		t.Fatalf("RepoRoot: %v", err)
	}
	if _, err := os.Stat(filepath.Join(root, "go.mod")); err != nil {
		t.Fatalf("found root %s has no go.mod: %v", root, err)
	}
}

func TestFreePortIsBoundable(t *testing.T) {
	port, err := FreePort()
	if err != nil {
		t.Fatalf("FreePort: %v", err)
	}
	if port <= 0 {
		t.Fatalf("port = %d, want positive", port)
	}
	// Binding the returned port again must succeed (the probe
	// listener was closed).
	l, err := listenOn(port)
	if err != nil {
		t.Fatalf("rebind %d: %v", port, err)
	}
	l.Close()
}

func TestWaitReadySucceedsAfterDelay(t *testing.T) {
	var hits int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits++
		// Only answer once the poller has retried a few times.
		if hits < 3 {
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		fmt.Fprint(w, "[]")
	}))
	defer srv.Close()

	start := time.Now()
	if err := waitReady(srv.URL, 5*time.Second); err != nil {
		t.Fatalf("waitReady: %v", err)
	}
	if time.Since(start) < 200*time.Millisecond {
		t.Errorf("waitReady returned too fast, did it skip polling?")
	}
}

func TestWaitReadyTimesOutWhenServerStaysDown(t *testing.T) {
	// A closed port: no server answers there.
	baseURL := "http://127.0.0.1:1/api/unused"
	if err := waitReady(baseURL, 300*time.Millisecond); err == nil {
		t.Fatal("waitReady should have timed out")
	}
}

func TestAPIRequestPostsAndDecodes(t *testing.T) {
	var gotPath, gotBody string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		body := make([]byte, r.ContentLength)
		_, _ = r.Body.Read(body)
		gotBody = string(body)
		fmt.Fprint(w, `{"id": "abc", "name": "Test"}`)
	}))
	defer srv.Close()

	out, err := APIRequest(srv.URL, http.MethodPost, "/api/profiles", map[string]any{"name": "Test"})
	if err != nil {
		t.Fatalf("APIRequest: %v", err)
	}
	obj, ok := out.(map[string]any)
	if !ok {
		t.Fatalf("response is not an object: %v", out)
	}
	if obj["id"] != "abc" || obj["name"] != "Test" {
		t.Errorf("decoded object = %v", obj)
	}
	if gotPath != "/api/profiles" {
		t.Errorf("request path = %s", gotPath)
	}
	if gotBody == "" {
		t.Errorf("payload body was empty")
	}
}

func TestAPIRequestReportsErrorStatus(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "nope", http.StatusBadRequest)
	}))
	defer srv.Close()

	_, err := APIRequest(srv.URL, http.MethodGet, "/api/nope", nil)
	if err == nil {
		t.Fatal("expected an error for status 400")
	}
}

func TestAPIRequestReportsBadJSON(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, "not json]")
	}))
	defer srv.Close()

	_, err := APIRequest(srv.URL, http.MethodGet, "/api/nope", nil)
	if err == nil {
		t.Fatal("expected a decode error")
	}
}

func listenOn(port int) (net.Listener, error) {
	return net.Listen("tcp", fmt.Sprintf("127.0.0.1:%d", port))
}
