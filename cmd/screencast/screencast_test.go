package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"
	"time"
)

func TestResolveOutputJoinsRepoForRelativePaths(t *testing.T) {
	root := t.TempDir()

	got, err := resolveOutput(root, "demo/tour.webm")
	if err != nil {
		t.Fatal(err)
	}
	if want := filepath.Join(root, "demo", "tour.webm"); got != want {
		t.Errorf("resolveOutput = %q, want %q", got, want)
	}

	got, err = resolveOutput(root, "/tmp/abs/tour.webm")
	if err != nil {
		t.Fatal(err)
	}
	if got != "/tmp/abs/tour.webm" {
		t.Errorf("absolute path changed: %q", got)
	}
}

// seedStubServer accepts every POST and answers with a minimal JSON
// object, enough for the seeder to finish: it only reads the ids back.
func seedStubServer(t *testing.T) (string, map[string][]string) {
	t.Helper()
	sent := make(map[string][]string)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var in map[string]any
		if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
			t.Fatal(err)
		}
		in["id"] = "id1"
		out, _ := json.Marshal(in)
		sent[r.URL.Path] = append(sent[r.URL.Path], string(out))
		_, _ = w.Write(out)
	}))
	t.Cleanup(srv.Close)
	return srv.URL, sent
}

func TestSeedPostsTheExpectedDemoData(t *testing.T) {
	saved := seedWait
	seedWait = time.Millisecond // no real scripts run in the stub
	defer func() { seedWait = saved }()

	baseURL, sent := seedStubServer(t)
	created, err := seed(baseURL, "/scripts/testing")
	if err != nil {
		t.Fatalf("seed: %v", err)
	}

	// Five demo profiles, in tour order, each pointing into the
	// example-scripts directory.
	if len(created) != 5 {
		t.Fatalf("seed created %d profiles, want 5", len(created))
	}
	for _, p := range created {
		script, _ := p["script_path"].(string)
		if filepath.Dir(script) != "/scripts/testing" {
			t.Errorf("script_path %q not in scripts/testing", script)
		}
	}
	if created[0]["name"] != "Daily Report" || created[4]["name"] != "Email Report" {
		t.Errorf("profile order off: %v", created)
	}

	if len(sent["/api/workflows"]) != 1 {
		t.Fatalf("workflows posted: %v", len(sent["/api/workflows"]))
	}
	var workflow map[string]any
	if err := json.Unmarshal([]byte(sent["/api/workflows"][0]), &workflow); err != nil {
		t.Fatal(err)
	}
	if workflow["name"] != "Nightly Pipeline" {
		t.Errorf("workflow name = %v", workflow["name"])
	}
	steps, _ := workflow["steps"].([]any)
	if len(steps) != 3 {
		t.Errorf("workflow has %d steps, want 3", len(steps))
	}

	// Two schedules back the card badges during the tour.
	if len(sent["/api/schedules"]) != 2 {
		t.Errorf("schedules posted: %v", len(sent["/api/schedules"]))
	}
	// And two pre-runs give History and Audit rows.
	if len(sent["/api/run/profile"]) != 2 {
		t.Errorf("pre-runs posted: %v", len(sent["/api/run/profile"]))
	}
}
