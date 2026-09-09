package api

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"launchcontrol/internal/ordjson"
	"launchcontrol/internal/runner"
	"launchcontrol/internal/scheduler"
	"launchcontrol/internal/store"
)

// newTestAPI builds an API over a throwaway data dir with the system
// python3 as the script interpreter.
func newTestAPI(t *testing.T) *API {
	t.Helper()
	dir := t.TempDir()
	db, err := store.Open(filepath.Join(dir, "launcher.db"), dir)
	if err != nil {
		t.Fatalf("store.Open: %v", err)
	}
	t.Cleanup(func() { db.Close() })
	runs := runner.NewManager(db, func() (string, error) { return "python3", nil })
	sched := scheduler.New(db, runs)
	return New(db, runs, sched, dir, filepath.Join(dir, "server.log"))
}

// call invokes the route handller directly and returns the status code
// and parsed body (as *ordjson.OMap, []any, or plain token).
func call(t *testing.T, a *API, method, target, body string) (int, any) {
	t.Helper()
	var reader io.Reader
	if body != "" {
		reader = strings.NewReader(body)
	}
	req := httptest.NewRequest(method, target, reader)
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	a.ServeHTTP(rec, req)
	raw := rec.Body.Bytes()
	parsed, err := ordjson.Parse(raw)
	if err != nil {
		t.Fatalf("response for %s %s is not JSON: %v (%q)", method, target, err, raw)
	}
	return rec.Code, parsed
}

// m asserts the response is a JSON object.
func m(v any) *ordjson.OMap { return v.(*ordjson.OMap) }

// arr asserts the response is a JSON array.
func arr(v any) []any { return v.([]any) }

func writeScript(t *testing.T, dir, body string) string {
	t.Helper()
	path := filepath.Join(dir, "script.py")
	if err := os.WriteFile(path, []byte(body), 0o755); err != nil {
		t.Fatal(err)
	}
	return path
}

func recID(v any) string { return ordjson.GetStr(m(v), "id") }

func TestProfileCRUDAndAudit(t *testing.T) {
	a := newTestAPI(t)
	_, created := call(t, a, http.MethodPost, "/api/profiles", `{"name":"A"}`)
	if recID(created) == "" || !strings.HasPrefix(recID(created), "profile_") {
		t.Fatalf("create did not assign an id: %v", created)
	}
	id := recID(created)

	// Update with the same id replaces in place (not appended).
	call(t, a, http.MethodPost, "/api/profiles", `{"name":"A2","id":"`+id+`"}`)
	_, list := call(t, a, http.MethodGet, "/api/profiles", "")
	if len(arr(list)) != 1 || ordjson.GetStr(m(arr(list)[0]), "name") != "A2" {
		t.Fatalf("update should replace in place, got %v", arr(list))
	}

	// Delete (trash), restore, then permanent delete.
	call(t, a, http.MethodDelete, "/api/profiles/"+id, "")
	_, list = call(t, a, http.MethodGet, "/api/profiles", "")
	if len(arr(list)) != 1 || ordjson.GetStr(m(arr(list)[0]), "group") != "__trash__" {
		t.Fatalf("trash state missing: %v", arr(list))
	}
	_, restored := call(t, a, http.MethodPost, "/api/profiles/"+id+"/restore", "")
	if ordjson.GetStr(m(restored), "group") != "" {
		t.Fatalf("restore did not clear the trash group: %v", restored)
	}
	call(t, a, http.MethodDelete, "/api/profiles/"+id+"/permanent", "")
	_, list = call(t, a, http.MethodGet, "/api/profiles", "")
	if len(arr(list)) != 0 {
		t.Fatalf("permanent delete failed: %v", arr(list))
	}

	// The audit trail must have captured every step.
	_, audit := call(t, a, http.MethodGet, "/api/audit?page=1&per_page=20", "")
	if fmt.Sprint(m(audit).Get("total")) != "5" {
		t.Fatalf("audit total = %v, want 5 (created, updated, deleted, restored, permanently_deleted)", m(audit).Get("total"))
	}
	actions := []string{}
	for _, e := range arr(m(audit).Get("entries")) {
		actions = append(actions, ordjson.GetStr(m(e), "action"))
	}
	// Newest first.
	if strings.Join(actions, ",") != "permanently_deleted,restored,deleted,updated,created" {
		t.Errorf("audit actions = %v", actions)
	}
}

func TestProfileDuplicateAndReorder(t *testing.T) {
	a := newTestAPI(t)
	call(t, a, http.MethodPost, "/api/profiles", `{"name":"Alpha","id":"p1"}`)
	call(t, a, http.MethodPost, "/api/profiles", `{"name":"Beta","id":"p2"}`)
	call(t, a, http.MethodPost, "/api/profiles", `{"name":"Gamma","id":"p3"}`)

	_, dup := call(t, a, http.MethodPost, "/api/profiles/p1/duplicate", "")
	if ordjson.GetStr(m(dup), "name") != "Alpha (copy)" || recID(dup) == "p1" {
		t.Fatalf("duplicate wrong: %v", dup)
	}
	_, list := call(t, a, http.MethodGet, "/api/profiles", "")
	names := []string{}
	for _, raw := range arr(list) {
		names = append(names, ordjson.GetStr(m(raw), "name"))
	}
	// The duplicate lands right after its source.
	if strings.Join(names, "#") != "Alpha#Alpha (copy)#Beta#Gamma" {
		t.Errorf("duplicate position wrong: %v", names)
	}

	// Reorder: move Gamma first.
	call(t, a, http.MethodPost, "/api/profiles/reorder", `{"order":["p3","p1","p2","`+recID(dup)+`"]}`)
	_, list = call(t, a, http.MethodGet, "/api/profiles", "")
	names = nil
	for _, raw := range arr(list) {
		names = append(names, ordjson.GetStr(m(raw), "name"))
	}
	if strings.Join(names, "#") != "Gamma#Alpha#Beta#Alpha (copy)" {
		t.Errorf("reorder wrong: %v", names)
	}
}

func TestWorkflowCreateEmbedsProfileSnapshots(t *testing.T) {
	a := newTestAPI(t)
	call(t, a, http.MethodPost, "/api/profiles", `{"name":"Step","id":"p1","args":["--x"]}`)
	_, wf := call(t, a, http.MethodPost, "/api/workflows",
		`{"name":"Chain","id":"w1","steps":[{"profile_id":"p1"}]}`)
	steps := ordjson.GetArr(m(wf), "steps")
	if len(steps) != 1 {
		t.Fatalf("workflow steps missing: %v", wf)
	}
	if ordjson.GetMap(m(steps[0]), "profile") == nil {
		t.Fatal("profile snapshot not embedded")
	}
}

func TestRunProfileEndToEnd(t *testing.T) {
	a := newTestAPI(t)
	dir := t.TempDir()
	script := writeScript(t, dir, "print('e2e out')\n")
	call(t, a, http.MethodPost, "/api/profiles",
		fmt.Sprintf(`{"name":"Run","script_path":%s}`, jsonString(script)))
	_, list := call(t, a, http.MethodGet, "/api/profiles", "")
	id := recID(arr(list)[0])

	_, result := call(t, a, http.MethodPost, "/api/run/profile", `{"profile_id":"`+id+`"}`)
	runID := ordjson.GetStr(m(result), "run_id")
	if runID == "" {
		t.Fatalf("no run id: %v", result)
	}

	deadline := time.Now().Add(10 * time.Second)
	var snap *ordjson.OMap
	for time.Now().Before(deadline) {
		_, s := call(t, a, http.MethodGet, "/api/runs/"+runID, "")
		if ordjson.GetStr(m(s), "status") != "running" {
			snap = m(s)
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	if snap == nil || ordjson.GetStr(snap, "status") != "completed" {
		t.Fatalf("run did not complete: %v", snap)
	}
	output := ordjson.GetArr(snap, "output")
	if len(output) != 1 || output[0] != "e2e out\n" {
		t.Errorf("output wrong: %v", output)
	}

	// History shows the completed run.
	_, hist := call(t, a, http.MethodGet, "/api/history", "")
	entries := arr(m(hist).Get("entries"))
	if len(entries) != 1 {
		t.Fatalf("history entries = %d", len(entries))
	}
	e := m(entries[0])
	if ordjson.GetStr(e, "status") != "completed" || ordjson.GetStr(e, "name") != "Run" {
		t.Errorf("history entry wrong: %v", e)
	}
	if e.Get("duration") == nil {
		t.Error("history entry should carry a duration")
	}
	// Cancelling an unknown run 404s.
	status, errResp := call(t, a, http.MethodPost, "/api/runs/nope/cancel", "")
	if status != 404 || ordjson.GetStr(m(errResp), "error") == "" {
		t.Errorf("cancel unknown run: %d %v", status, errResp)
	}
}

func TestRunProfileMissingScript(t *testing.T) {
	a := newTestAPI(t)
	call(t, a, http.MethodPost, "/api/profiles", `{"name":"X","script_path":"/gone/nope.py"}`)
	_, list := call(t, a, http.MethodGet, "/api/profiles", "")
	id := recID(arr(list)[0])
	status, resp := call(t, a, http.MethodPost, "/api/run/profile", `{"profile_id":"`+id+`"}`)
	if status != 400 || !strings.Contains(ordjson.GetStr(m(resp), "error"), "Script not found") {
		t.Errorf("got %d %v", status, resp)
	}
}

func TestHistoryFiltersAndDetail(t *testing.T) {
	a := newTestAPI(t)
	dir := t.TempDir()
	script := writeScript(t, dir, "print('f')\n")
	call(t, a, http.MethodPost, "/api/profiles", fmt.Sprintf(`{"name":"Filter Test","script_path":%s}`, jsonString(script)))
	_, list := call(t, a, http.MethodGet, "/api/profiles", "")
	id := recID(arr(list)[0])
	call(t, a, http.MethodPost, "/api/run/profile", `{"profile_id":"`+id+`"}`)
	deadline := time.Now().Add(10 * time.Second)
	for time.Now().Before(deadline) {
		_, hist := call(t, a, http.MethodGet, "/api/history", "")
		entries := arr(m(hist).Get("entries"))
		if len(entries) == 1 && ordjson.GetStr(m(entries[0]), "status") == "completed" {
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	// Name filter (case-insensitive substring).
	_, hist := call(t, a, http.MethodGet, "/api/history?name=filter", "")
	if fmt.Sprint(m(hist).Get("total")) != "1" {
		t.Errorf("name filter failed: %v", m(hist).Get("total"))
	}
	_, hist = call(t, a, http.MethodGet, "/api/history?name=nope", "")
	if fmt.Sprint(m(hist).Get("total")) != "0" {
		t.Errorf("name filter should exclude: %v", m(hist).Get("total"))
	}
	// Status filter.
	_, hist = call(t, a, http.MethodGet, "/api/history?status=completed", "")
	if fmt.Sprint(m(hist).Get("total")) != "1" {
		t.Errorf("status filter failed: %v", m(hist).Get("total"))
	}
	// Detail by entry id.
	_, detail := call(t, a, http.MethodGet, "/api/history?per_page=1", "")
	entryID := ordjson.GetStr(m(arr(m(detail).Get("entries"))[0]), "id")
	_, entry := call(t, a, http.MethodGet, "/api/history/"+entryID, "")
	if ordjson.GetStr(m(entry), "run_id") == "" {
		t.Fatalf("detail failed: %v", entry)
	}
	// Bulk delete matches entry ids (Python behaviour).
	call(t, a, http.MethodPost, "/api/history/bulk", `{"ids":["`+entryID+`"]}`)
	_, hist = call(t, a, http.MethodGet, "/api/history", "")
	if fmt.Sprint(m(hist).Get("total")) != "0" {
		t.Errorf("bulk delete by run id failed")
	}
}

func TestScheduleCRUDAndPreview(t *testing.T) {
	a := newTestAPI(t)
	call(t, a, http.MethodPost, "/api/profiles", `{"name":"Target","id":"p1","script_path":"/x"}`)
	_, sched := call(t, a, http.MethodPost, "/api/schedules",
		`{"name":"Every 7 min","target_type":"profile","target_id":"p1","cron":"*/7 * * * *"}`)
	if m(sched).Get("next_run_at") == nil {
		t.Fatal("next_run_at missing")
	}
	id := recID(sched)

	// List is enriched.
	_, list := call(t, a, http.MethodGet, "/api/schedules", "")
	first := m(arr(list)[0])
	if ordjson.GetStr(first, "target_name") != "Target" {
		t.Errorf("target_name missing: %v", first)
	}
	if ordjson.GetStr(first, "description") != "Every 7 minutes" {
		t.Errorf("list description wrong: %v", first)
	}
	if _, ok := first.GetOK("target_trashed"); !ok {
		t.Error("target_trashed missing")
	}

	// Toggle off clears next_run_at.
	_, toggled := call(t, a, http.MethodPost, "/api/schedules/"+id+"/toggle", "")
	if ordjson.GetBool(m(toggled), "enabled") || m(toggled).Get("next_run_at") != nil {
		t.Errorf("toggle off wrong: %v", toggled)
	}
	_, toggled = call(t, a, http.MethodPost, "/api/schedules/"+id+"/toggle", "")
	if !ordjson.GetBool(m(toggled), "enabled") {
		t.Errorf("toggle on wrong: %v", toggled)
	}

	// Preview endpoint.
	_, preview := call(t, a, http.MethodGet, "/api/schedules/preview?cron=0%209%20*%20*%201-5", "")
	if ordjson.GetStr(m(preview), "description") != "Weekdays at 09:00" {
		t.Errorf("preview description wrong: %v", preview)
	}
	if len(arr(m(preview).Get("next"))) != 3 {
		t.Errorf("preview count wrong: %v", preview)
	}
	// Invalid cron errors with the human message.
	status, errResp := call(t, a, http.MethodGet, "/api/schedules/preview?cron=0%200", "")
	if status != 400 || !strings.Contains(ordjson.GetStr(m(errResp), "error"), "Invalid cron expression") {
		t.Errorf("preview validation wrong: %d %v", status, errResp)
	}

	// Duplicate gets a fresh name.
	_, dup := call(t, a, http.MethodPost, "/api/schedules/"+id+"/duplicate", "")
	if ordjson.GetStr(m(dup), "name") != "Every 7 min (copy)" {
		t.Errorf("duplicate name wrong: %v", dup)
	}

	// Trash stops firing and clears next_run_at.
	call(t, a, http.MethodDelete, "/api/schedules/"+id, "")
	_, list = call(t, a, http.MethodGet, "/api/schedules", "")
	if m(arr(list)[0]).Get("next_run_at") != nil {
		t.Error("trashed schedule must clear next_run_at")
	}
	_, restored := call(t, a, http.MethodPost, "/api/schedules/"+id+"/restore", "")
	if m(restored) == nil || ordjson.GetStr(m(restored), "group") == "__trash__" {
		t.Errorf("restore failed: %v", restored)
	}
	// Remove the duplicate from earlier too, then both permanently.
	call(t, a, http.MethodDelete, "/api/schedules/"+recID(dup)+"/permanent", "")
	call(t, a, http.MethodDelete, "/api/schedules/"+id+"/permanent", "")
	_, list = call(t, a, http.MethodGet, "/api/schedules", "")
	if len(arr(list)) != 0 {
		t.Errorf("permanent delete failed: %v", arr(list))
	}
}

func TestScheduleValidationErrors(t *testing.T) {
	a := newTestAPI(t)
	status, resp := call(t, a, http.MethodPost, "/api/schedules",
		`{"target_type":"profile","target_id":"ghost","cron":"* * * * *"}`)
	if status != 400 || ordjson.GetStr(m(resp), "error") != "Target not found" {
		t.Errorf("got %d %v", status, resp)
	}
	call(t, a, http.MethodPost, "/api/profiles", `{"name":"T","id":"p1"}`)
	status, resp = call(t, a, http.MethodPost, "/api/schedules",
		`{"target_type":"profile","target_id":"p1","cron":"bad"}`)
	if status != 400 || !strings.Contains(ordjson.GetStr(m(resp), "error"), "Invalid cron") {
		t.Errorf("got %d %v", status, resp)
	}
	status, resp = call(t, a, http.MethodPost, "/api/schedules",
		`{"target_type":"fish","target_id":"p1","cron":"* * * * *"}`)
	if status != 400 || ordjson.GetStr(m(resp), "error") != "target_type must be 'profile' or 'workflow'" {
		t.Errorf("got %d %v", status, resp)
	}
}

func TestBrowseDirectoryEndpoint(t *testing.T) {
	a := newTestAPI(t)
	dir := t.TempDir()
	writeScript(t, dir, "")
	_, resp := call(t, a, http.MethodGet, "/api/browse?path="+urlEscape(dir), "")
	if m(resp).Get("entries") == nil {
		t.Fatalf("browse failed: %v", resp)
	}
	// Selecting a non-Python file gets the explanatory error.
	txt := filepath.Join(dir, "notes.txt")
	os.WriteFile(txt, []byte("x"), 0o644)
	_, resp = call(t, a, http.MethodGet, "/api/browse?path="+urlEscape(txt), "")
	if !strings.Contains(ordjson.GetStr(m(resp), "error"), "not a Python script") {
		t.Errorf("browse of a non-script file wrong: %v", resp)
	}
	// script_exists
	_, resp = call(t, a, http.MethodGet, "/api/script_exists?path="+urlEscape(filepath.Join(dir, "script.py")), "")
	if m(resp).Get("exists") != true {
		t.Errorf("script_exists wrong: %v", resp)
	}
}

func TestStaticFileServingAndTraversal(t *testing.T) {
	a := newTestAPI(t)
	req := httptest.NewRequest(http.MethodGet, "/static/js/api.js", nil)
	rec := httptest.NewRecorder()
	a.ServeHTTP(rec, req)
	if rec.Code != 200 || !bytes.Contains(rec.Body.Bytes(), []byte("fetch")) {
		t.Fatalf("static serving wrong: %d", rec.Code)
	}
	tr := httptest.NewRequest(http.MethodGet, "/static/../go.mod", nil)
	rec2 := httptest.NewRecorder()
	a.ServeHTTP(rec2, tr)
	if rec2.Code != 404 && rec2.Code != 403 {
		t.Errorf("traversal not blocked: %d", rec2.Code)
	}
}

func TestLogsEndpointShape(t *testing.T) {
	a := newTestAPI(t)
	for i := 0; i < 5; i++ {
		f, _ := os.OpenFile(a.LogPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
		f.WriteString(fmt.Sprintf("line %d\n", i))
		f.Close()
	}
	time.Sleep(20 * time.Millisecond)
	_, resp := call(t, a, http.MethodGet, "/api/logs", "")
	if m(resp).Get("reset") != true || m(resp).Get("next_offset") == nil {
		t.Fatalf("logs shape wrong: %v", resp)
	}
	entries := arr(m(resp).Get("entries"))
	if len(entries) != 5 || entries[0] != "line 0" {
		t.Errorf("tail wrong: %v", entries)
	}
	offset := m(resp).Get("next_offset")
	_, resp2 := call(t, a, http.MethodGet, "/api/logs?after="+fmt.Sprint(offset), "")
	if m(resp2).Get("reset") != false {
		t.Errorf("incremental read should not reset: %v", resp2)
	}
	// A stale offset (beyond EOF) resets.
	_, resp3 := call(t, a, http.MethodGet, "/api/logs?after=999999", "")
	if m(resp3).Get("reset") != true {
		t.Error("stale offset should reset to a full tail")
	}
}

func TestInvalidJSONBodyRejected(t *testing.T) {
	a := newTestAPI(t)
	status, resp := call(t, a, http.MethodPost, "/api/profiles", `{invalid`)
	if status != 400 || ordjson.GetStr(m(resp), "error") != "Invalid JSON" {
		t.Errorf("got %d %v", status, resp)
	}
}

func TestGzipResponses(t *testing.T) {
	a := newTestAPI(t)
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Accept-Encoding", "gzip")
	rec := httptest.NewRecorder()
	a.ServeHTTP(rec, req)
	if rec.Header().Get("Content-Encoding") != "gzip" {
		t.Error("index should be gzipped when accepted")
	}
	plain := httptest.NewRequest(http.MethodGet, "/", nil)
	rec2 := httptest.NewRecorder()
	a.ServeHTTP(rec2, plain)
	if rec2.Header().Get("Content-Encoding") == "gzip" {
		t.Error("index must not be gzipped when not accepted")
	}
}

// --- helpers ---

func jsonString(s string) string {
	b, _ := json.Marshal(s)
	return string(b)
}

func urlEscape(s string) string {
	return strings.ReplaceAll(strings.ReplaceAll(strings.ReplaceAll(s, "%", "%25"), " ", "%20"), "#", "%23")
}
