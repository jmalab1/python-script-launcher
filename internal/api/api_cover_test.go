package api

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"launchcontrol/internal/ordjson"
	"launchcontrol/internal/store"
)

// --- helpers for the coverage tests below ---

// auditCount returns the audit "total" for a query string such as
// "?action=deleted&entity=workflow", so tests can assert that a
// mutation left exactly the expected trail behind.
func auditCount(t *testing.T, a *API, query string) string {
	t.Helper()
	_, audit := call(t, a, http.MethodGet, "/api/audit"+query, "")
	return fmt.Sprint(m(audit).Get("total"))
}

// waitForRun polls a run until it leaves the starting/running states
// and returns its final snapshot, failing the test on timeout.
func waitForRun(t *testing.T, a *API, runID string) *ordjson.OMap {
	t.Helper()
	deadline := time.Now().Add(10 * time.Second)
	for time.Now().Before(deadline) {
		_, s := call(t, a, http.MethodGet, "/api/runs/"+runID, "")
		status := ordjson.GetStr(m(s), "status")
		if status != "starting" && status != "running" {
			return m(s)
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatalf("run %s never finished", runID)
	return nil
}

// filesystemRoot walks up from dir to the top-most directory ("/" on
// unix, a drive root on Windows). Browsing it is the only code path
// that consults the drive list.
func filesystemRoot(dir string) string {
	root := dir
	for {
		parent := filepath.Dir(root)
		if parent == root {
			return root
		}
		root = parent
	}
}

// TestHandlerMuxRouting exercises the top-level handler returned by
// Handler(): API requests must reach the shared router, and requests
// outside it must 404.
func TestHandlerMuxRouting(t *testing.T) {
	a := newTestAPI(t)
	h := a.Handler()

	req := httptest.NewRequest(http.MethodGet, "/api/profiles", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("GET /api/profiles through the mux = %d", rec.Code)
	}
	if _, err := ordjson.Parse(rec.Body.Bytes()); err != nil {
		t.Fatalf("response is not JSON: %v (%q)", err, rec.Body.String())
	}

	// Unknown paths fall through to the standard 404.
	req = httptest.NewRequest(http.MethodGet, "/nowhere", nil)
	rec = httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Errorf("GET /nowhere = %d, want 404", rec.Code)
	}

	// Methods outside GET/POST/DELETE are not served on /api either.
	req = httptest.NewRequest(http.MethodPut, "/api/profiles", nil)
	rec = httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Errorf("PUT /api/profiles = %d, want 404", rec.Code)
	}
}

// TestAuditDetailEndpoint checks the single-entry audit view: the list
// endpoint returns trimmed rows, the detail endpoint returns the full
// stored entry including the integrity hash, and unknown ids 404.
func TestAuditDetailEndpoint(t *testing.T) {
	a := newTestAPI(t)
	call(t, a, http.MethodPost, "/api/profiles", `{"name":"A","id":"p1"}`)

	_, list := call(t, a, http.MethodGet, "/api/audit?page=1&per_page=5", "")
	entries := arr(m(list).Get("entries"))
	if len(entries) != 1 {
		t.Fatalf("audit list entries = %d, want 1", len(entries))
	}
	// The list view must not leak the full entry.
	if ordjson.GetStr(m(entries[0]), "_hash") != "" {
		t.Error("audit list rows should be summarized without the hash")
	}
	entryID := ordjson.GetStr(m(entries[0]), "id")

	_, detail := call(t, a, http.MethodGet, "/api/audit/"+entryID, "")
	d := m(detail)
	if ordjson.GetStr(d, "action") != "created" ||
		ordjson.GetStr(d, "entity_type") != "profile" ||
		ordjson.GetStr(d, "entity_id") != "p1" {
		t.Errorf("audit detail wrong: %v", d)
	}
	if ordjson.GetStr(d, "_hash") == "" {
		t.Error("audit detail should include the integrity hash")
	}

	status, resp := call(t, a, http.MethodGet, "/api/audit/nope", "")
	if status != 404 || ordjson.GetStr(m(resp), "error") != "Not found" {
		t.Errorf("unknown audit id: %d %v", status, resp)
	}
}

// TestHistoryDeleteAndClear covers deleting one entry (by entry id and
// by run id) and wiping the whole history. Entries are seeded through
// the store's own SaveHistory, so no interpreter is involved.
func TestHistoryDeleteAndClear(t *testing.T) {
	a := newTestAPI(t)
	a.DB.SaveHistory("run_1", "One", "profile", "completed", ordjson.Number(0), []string{"out"}, 1000.0, store.HistoryEntryOptions{})
	a.DB.SaveHistory("run_2", "Two", "profile", "failed", ordjson.Number(1), nil, 2000.0, store.HistoryEntryOptions{})

	_, hist := call(t, a, http.MethodGet, "/api/history", "")
	entries := arr(m(hist).Get("entries"))
	if len(entries) != 2 {
		t.Fatalf("seeded history entries = %d, want 2", len(entries))
	}

	// Delete one entry by its entry id.
	var id2 string
	for _, raw := range entries {
		if ordjson.GetStr(m(raw), "run_id") == "run_2" {
			id2 = ordjson.GetStr(m(raw), "id")
		}
	}
	if id2 == "" {
		t.Fatal("seeded entry has no id")
	}
	status, resp := call(t, a, http.MethodDelete, "/api/history/"+id2, "")
	if status != 200 || ordjson.GetBool(m(resp), "ok") != true {
		t.Fatalf("delete by id: %d %v", status, resp)
	}

	_, hist = call(t, a, http.MethodGet, "/api/history", "")
	remaining := arr(m(hist).Get("entries"))
	if len(remaining) != 1 || ordjson.GetStr(m(remaining[0]), "run_id") != "run_1" {
		t.Fatalf("wrong entry removed: %v", remaining)
	}

	// Deleting by run id exercises the fallback when no entry id matches.
	call(t, a, http.MethodDelete, "/api/history/run_1", "")
	_, hist = call(t, a, http.MethodGet, "/api/history", "")
	if fmt.Sprint(m(hist).Get("total")) != "0" {
		t.Fatalf("delete by run id failed: %v", m(hist).Get("entries"))
	}

	// Deleting from an empty history still answers ok.
	_, resp = call(t, a, http.MethodDelete, "/api/history/ghost", "")
	if ordjson.GetBool(m(resp), "ok") != true {
		t.Errorf("delete on empty history should still be ok: %v", resp)
	}

	// Clear wipes everything.
	a.DB.SaveHistory("run_3", "Three", "profile", "completed", nil, nil, 3000.0, store.HistoryEntryOptions{})
	status, resp = call(t, a, http.MethodDelete, "/api/history", "")
	if status != 200 || ordjson.GetBool(m(resp), "ok") != true {
		t.Fatalf("clear history: %d %v", status, resp)
	}
	_, hist = call(t, a, http.MethodGet, "/api/history", "")
	if fmt.Sprint(m(hist).Get("total")) != "0" {
		t.Errorf("history not cleared: %v", m(hist).Get("entries"))
	}
}

// TestEntryTime checks the timestamp a history entry is shown for: the
// started_at field wins over the fallback timestamp, both stored shapes
// (json.Number and float64) are accepted, and missing fields give zero.
func TestEntryTime(t *testing.T) {
	if got := entryTime(ordjson.New().Set("started_at", ordjson.Number(50.5)).Set("timestamp", ordjson.Number(60))); got != 50.5 {
		t.Errorf("entryTime with started_at = %v, want 50.5", got)
	}

	if got := entryTime(ordjson.New().Set("started_at", 42.0)); got != 42.0 {
		t.Errorf("entryTime with float64 started_at = %v, want 42", got)
	}

	// Legacy entries predating started_at fall back to the timestamp.
	if got := entryTime(ordjson.New().Set("timestamp", ordjson.Number(60.25))); got != 60.25 {
		t.Errorf("entryTime fallback = %v, want 60.25", got)
	}

	if got := entryTime(ordjson.New()); got != 0 {
		t.Errorf("entryTime with no fields = %v, want 0", got)
	}
}

// TestPythonStr checks the Python str() mimic used for run arguments:
// booleans become "True"/"False", other values fall through to fmt.
func TestPythonStr(t *testing.T) {
	cases := []struct {
		in   any
		want string
	}{
		{"hello", "hello"},
		{true, "True"},
		{false, "False"},
		{json.Number("3.14"), "3.14"},
		{float64(2.5), "2.5"},
	}
	for _, c := range cases {
		if got := pythonStr(c.in); got != c.want {
			t.Errorf("pythonStr(%v) = %q, want %q", c.in, got, c.want)
		}
	}
}

// TestRunWorkflow covers the workflow run endpoint. A workflow with no
// steps completes without ever spawning a process, so the happy path
// needs no interpreter; a run with real steps would need the built
// Python runtime and is left to the end-to-end suite.
func TestRunWorkflow(t *testing.T) {
	a := newTestAPI(t)
	status, resp := call(t, a, http.MethodPost, "/api/run/workflow", `{"workflow_id":"ghost"}`)
	if status != 404 || ordjson.GetStr(m(resp), "error") != "Workflow not found" {
		t.Fatalf("unknown workflow: %d %v", status, resp)
	}

	// An empty body must also answer "Workflow not found", not crash.
	status, resp = call(t, a, http.MethodPost, "/api/run/workflow", "")
	if status != 404 || ordjson.GetStr(m(resp), "error") != "Workflow not found" {
		t.Fatalf("missing body: %d %v", status, resp)
	}

	call(t, a, http.MethodPost, "/api/workflows", `{"name":"Empty","id":"w1","steps":[]}`)
	status, resp = call(t, a, http.MethodPost, "/api/run/workflow", `{"workflow_id":"w1"}`)
	if status != 200 {
		t.Fatalf("start workflow run: %d %v", status, resp)
	}
	runID := ordjson.GetStr(m(resp), "run_id")
	if runID == "" {
		t.Fatalf("no run id: %v", resp)
	}

	snap := waitForRun(t, a, runID)
	if ordjson.GetStr(snap, "status") != "completed" {
		t.Fatalf("empty workflow should complete, got %v", snap)
	}

	// The run lands in history as a completed workflow entry.
	deadline := time.Now().Add(10 * time.Second)
	var entry *ordjson.OMap
	for time.Now().Before(deadline) {
		_, hist := call(t, a, http.MethodGet, "/api/history?type=workflow", "")
		entries := arr(m(hist).Get("entries"))
		if len(entries) == 1 && ordjson.GetStr(m(entries[0]), "status") == "completed" {
			entry = m(entries[0])
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	if entry == nil {
		t.Fatal("workflow run never reached history as completed")
	}
	if ordjson.GetStr(entry, "name") != "Empty" || ordjson.GetStr(entry, "run_id") != runID {
		t.Errorf("history entry wrong: %v", entry)
	}
}

// TestScheduleRunNow covers firing a schedule immediately: unknown
// schedules and unstartable targets error, a working target starts a
// run, records it on the schedule, and leaves a run_now audit entry.
func TestScheduleRunNow(t *testing.T) {
	a := newTestAPI(t)
	status, resp := call(t, a, http.MethodPost, "/api/schedules/ghost/run_now", "")
	if status != 400 || ordjson.GetStr(m(resp), "error") != "Schedule not found" {
		t.Fatalf("unknown schedule: %d %v", status, resp)
	}

	// A target whose script is missing cannot start a run.
	call(t, a, http.MethodPost, "/api/profiles", `{"name":"Gone","id":"p1","script_path":"/gone/nope.py"}`)
	_, sched := call(t, a, http.MethodPost, "/api/schedules",
		`{"name":"S1","target_type":"profile","target_id":"p1","cron":"* * * * *"}`)
	id := recID(sched)
	status, resp = call(t, a, http.MethodPost, "/api/schedules/"+id+"/run_now", "")
	if status != 400 || !strings.Contains(ordjson.GetStr(m(resp), "error"), "Could not start run") {
		t.Fatalf("missing-script target: %d %v", status, resp)
	}

	// A zero-step workflow target starts without needing an interpreter.
	call(t, a, http.MethodPost, "/api/workflows", `{"name":"Empty","id":"w1","steps":[]}`)
	_, sched = call(t, a, http.MethodPost, "/api/schedules",
		`{"name":"WF sched","target_type":"workflow","target_id":"w1","cron":"* * * * *"}`)
	wid := recID(sched)

	_, result := call(t, a, http.MethodPost, "/api/schedules/"+wid+"/run_now", "")
	runID := ordjson.GetStr(m(result), "run_id")
	if runID == "" {
		t.Fatalf("run_now did not start a run: %v", result)
	}

	// The schedule remembers the manual run.
	_, list := call(t, a, http.MethodGet, "/api/schedules", "")
	var wfSched *ordjson.OMap
	for _, raw := range arr(list) {
		if ordjson.GetStr(m(raw), "id") == wid {
			wfSched = m(raw)
		}
	}
	if wfSched == nil {
		t.Fatal("schedule vanished from the list")
	}
	if ordjson.GetStr(wfSched, "last_run_id") != runID || wfSched.Get("last_run_at") == nil {
		t.Errorf("run bookkeeping wrong: %v", wfSched)
	}

	// The manual firing is audited.
	if got := auditCount(t, a, "?action=run_now"); got != "1" {
		t.Errorf("run_now audit total = %s, want 1", got)
	}
}

// TestWorkflowTrashLifecycle walks a workflow through delete, restore,
// duplicate, reorder and permanent delete, checking list state and the
// audit trail after each step.
func TestWorkflowTrashLifecycle(t *testing.T) {
	a := newTestAPI(t)
	call(t, a, http.MethodPost, "/api/profiles", `{"name":"Step","id":"p1","args":["--x"]}`)
	_, wf := call(t, a, http.MethodPost, "/api/workflows",
		`{"name":"Chain","id":"w1","steps":[{"profile_id":"p1"}]}`)
	if recID(wf) != "w1" {
		t.Fatalf("create did not keep the id: %v", wf)
	}

	// Delete moves the workflow to the trash.
	call(t, a, http.MethodDelete, "/api/workflows/w1", "")
	_, list := call(t, a, http.MethodGet, "/api/workflows", "")
	if ordjson.GetStr(m(arr(list)[0]), "group") != "__trash__" {
		t.Fatalf("delete did not trash: %v", arr(list))
	}

	// Restore pulls it back out and clears the trash group.
	_, restored := call(t, a, http.MethodPost, "/api/workflows/w1/restore", "")
	if ordjson.GetStr(m(restored), "group") != "" {
		t.Fatalf("restore failed: %v", restored)
	}

	// Restoring something that is not in the trash 404s.
	status, resp := call(t, a, http.MethodPost, "/api/workflows/w1/restore", "")
	if status != 404 || ordjson.GetStr(m(resp), "error") != "Not found" {
		t.Errorf("restore of a live workflow: %d %v", status, resp)
	}

	// The duplicate lands right after its source, with fresh snapshots.
	_, dup := call(t, a, http.MethodPost, "/api/workflows/w1/duplicate", "")
	dupID := recID(dup)
	if ordjson.GetStr(m(dup), "name") != "Chain (copy)" || dupID == "w1" {
		t.Fatalf("duplicate wrong: %v", dup)
	}
	dupSteps := ordjson.GetArr(m(dup), "steps")
	if len(dupSteps) != 1 || ordjson.GetMap(m(dupSteps[0]), "profile") == nil {
		t.Errorf("duplicate should embed fresh profile snapshots: %v", dup)
	}
	_, list = call(t, a, http.MethodGet, "/api/workflows", "")
	ids := []string{}
	for _, raw := range arr(list) {
		ids = append(ids, recID(raw))
	}
	if strings.Join(ids, "#") != "w1#"+dupID {
		t.Errorf("duplicate position wrong: %v", ids)
	}

	// Duplicating an unknown workflow 404s.
	status, resp = call(t, a, http.MethodPost, "/api/workflows/ghost/duplicate", "")
	if status != 404 || ordjson.GetStr(m(resp), "error") != "Not found" {
		t.Errorf("duplicate of unknown workflow: %d %v", status, resp)
	}

	// Reorder moves the duplicate first.
	order := `{"order":["` + dupID + `","w1"]}`
	call(t, a, http.MethodPost, "/api/workflows/reorder", order)
	_, list = call(t, a, http.MethodGet, "/api/workflows", "")
	ids = nil
	for _, raw := range arr(list) {
		ids = append(ids, recID(raw))
	}
	if strings.Join(ids, "#") != dupID+"#w1" {
		t.Errorf("reorder wrong: %v", ids)
	}

	// Repeating the same order must not audit a second reorder.
	call(t, a, http.MethodPost, "/api/workflows/reorder", order)
	if got := auditCount(t, a, "?action=reordered"); got != "1" {
		t.Errorf("reordered audit total = %s, want 1", got)
	}

	// Permanent delete takes the workflow's schedules with it.
	_, sched := call(t, a, http.MethodPost, "/api/schedules",
		`{"name":"S","target_type":"workflow","target_id":"w1","cron":"* * * * *"}`)
	schedID := recID(sched)
	call(t, a, http.MethodDelete, "/api/workflows/w1/permanent", "")
	_, list = call(t, a, http.MethodGet, "/api/workflows", "")
	if len(arr(list)) != 1 || recID(arr(list)[0]) != dupID {
		t.Fatalf("permanent delete left: %v", arr(list))
	}
	_, schedList := call(t, a, http.MethodGet, "/api/schedules", "")
	if len(arr(schedList)) != 0 {
		t.Errorf("schedules of a deleted workflow survived: %v", arr(schedList))
	}

	// The audit trail for the whole lifecycle, filtered to workflows.
	for _, check := range []struct{ query, want string }{
		{"?action=created&entity=workflow", "2"}, // create + duplicate
		{"?action=deleted&entity=workflow", "1"},
		{"?action=restored&entity=workflow", "1"},
		{"?action=permanently_deleted&entity=workflow", "1"},
	} {
		if got := auditCount(t, a, check.query); got != check.want {
			t.Errorf("audit %s = %s, want %s", check.query, got, check.want)
		}
	}

	// The permanent-delete entry names the schedule it removed.
	_, audit := call(t, a, http.MethodGet, "/api/audit?action=permanently_deleted", "")
	permanentID := ordjson.GetStr(m(arr(m(audit).Get("entries"))[0]), "id")
	_, detail := call(t, a, http.MethodGet, "/api/audit/"+permanentID, "")
	removed := ordjson.GetArr(ordjson.GetMap(m(detail), "details"), "schedules_removed")
	if len(removed) != 1 || fmt.Sprint(removed[0]) != schedID {
		t.Errorf("permanently_deleted details wrong: %v", m(detail).Get("details"))
	}
}

// TestBrowseFilesystemRoot is a smoke test for the drive-list hook:
// browsing the top-most directory is the only path that consults it,
// and on non-Windows builds the list is simply empty.
func TestBrowseFilesystemRoot(t *testing.T) {
	a := newTestAPI(t)
	root := filesystemRoot(t.TempDir())

	_, resp := call(t, a, http.MethodGet, "/api/browse?path="+urlEscape(root), "")
	if ordjson.GetStr(m(resp), "error") != "" {
		t.Fatalf("browse of the filesystem root failed: %v", resp)
	}
	if m(resp).Get("entries") == nil {
		t.Errorf("root browse missing entries: %v", resp)
	}
}
