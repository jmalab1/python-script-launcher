package runner

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"launchcontrol/internal/ordjson"
	"launchcontrol/internal/store"
)

// python3 resolves the system interpreter for tests.
func python3() (string, error) { return "python3", nil }

// toStrings converts a snapshot output array to plain strings.
func toStrings(v any) []string {
	arr, _ := v.([]any)
	out := make([]string, len(arr))
	for i, item := range arr {
		out[i], _ = item.(string)
	}
	return out
}

func newTestManager(t *testing.T) (*Manager, *store.DB, string) {
	t.Helper()
	dir := t.TempDir()
	db, err := store.Open(filepath.Join(dir, "launcher.db"), dir)
	if err != nil {
		t.Fatalf("store.Open: %v", err)
	}
	t.Cleanup(func() { db.Close() })
	return NewManager(db, python3), db, dir
}

func writeScript(t *testing.T, dir, name, body string) string {
	t.Helper()
	path := filepath.Join(dir, name)
	if err := os.WriteFile(path, []byte(body), 0o755); err != nil {
		t.Fatal(err)
	}
	return path
}

func profile(t *testing.T, scriptPath string, extra ...any) *ordjson.OMap {
	t.Helper()
	p := ordjson.New().Set("id", "p1").Set("name", "Test").Set("script_path", scriptPath)
	for i := 0; i+1 < len(extra); i += 2 {
		p.Set(extra[i].(string), extra[i+1])
	}
	return p
}
func waitForFinish(t *testing.T, m *Manager, runID string, timeout time.Duration) *Run {
	t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		// Read the status under the manager lock; once a run is finished
		// no goroutine writes to it again, so the returned pointer is
		// safe to inspect.
		m.mu.Lock()
		r, ok := m.runs[runID]
		done := ok && finishedStatuses[r.Status]
		m.mu.Unlock()
		if done {
			return r
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatalf("run %s did not finish within %v", runID, timeout)
	return nil
}

func TestRunScriptCapturesOutputAndStatus(t *testing.T) {
	m, db, dir := newTestManager(t)
	script := writeScript(t, dir, "ok.py", "print('hello')\nprint('world')\n")
	runID, errStr := m.StartProfileRun(profile(t, script), nil, nil, "manual", nil)
	if errStr != "" {
		t.Fatalf("unexpected error: %s", errStr)
	}
	r := waitForFinish(t, m, runID, 10*time.Second)
	if r.Status != "completed" {
		t.Errorf("status = %q, want completed", r.Status)
	}
	joined := strings.Join(r.Output, "")
	if !strings.Contains(joined, "hello\n") || !strings.Contains(joined, "world\n") {
		t.Errorf("output missing lines: %q", joined)
	}
	// Lines keep their trailing newline, like Python's readline capture.
	if r.Output[0] != "hello\n" {
		t.Errorf("first line = %q, want %q", r.Output[0], "hello\n")
	}
	// History must contain the run, updated to completed.
	history, _ := db.LoadHistory()
	if len(history) != 1 || ordjson.GetStr(history[0], "status") != "completed" {
		t.Errorf("history wrong: %v", history)
	}
	if ordjson.GetStr(history[0], "run_id") != runID {
		t.Errorf("history run_id = %q", ordjson.GetStr(history[0], "run_id"))
	}
}

func TestRunScriptCombinesStderr(t *testing.T) {
	m, _, dir := newTestManager(t)
	script := writeScript(t, dir, "err.py", "import sys\nprint('out')\nprint('err', file=sys.stderr)\n")
	runID, _ := m.StartProfileRun(profile(t, script), nil, nil, "manual", nil)
	r := waitForFinish(t, m, runID, 10*time.Second)
	joined := strings.Join(r.Output, "")
	if !strings.Contains(joined, "out\n") || !strings.Contains(joined, "err\n") {
		t.Errorf("stderr not captured: %q", joined)
	}
}

func TestFailingScriptMarkedFailed(t *testing.T) {
	m, db, dir := newTestManager(t)
	script := writeScript(t, dir, "fail.py", "import sys\nprint('boom')\nsys.exit(3)\n")
	runID, _ := m.StartProfileRun(profile(t, script), nil, nil, "manual", nil)
	r := waitForFinish(t, m, runID, 10*time.Second)
	if r.Status != "failed" {
		t.Errorf("status = %q, want failed", r.Status)
	}
	if r.ReturnCode == nil || *r.ReturnCode != 3 {
		t.Errorf("returncode = %v, want 3", r.ReturnCode)
	}
	history, _ := db.LoadHistory()
	if len(history) != 1 || ordjson.GetStr(history[0], "status") != "failed" {
		t.Errorf("history not updated: %v", history)
	}
}

func TestMissingScriptRejected(t *testing.T) {
	m, _, _ := newTestManager(t)
	_, errStr := m.StartProfileRun(profile(t, "/nonexistent/nope.py"), nil, nil, "manual", nil)
	if errStr != "Script not found: /nonexistent/nope.py" {
		t.Errorf("errStr = %q", errStr)
	}
}

func TestTimeoutKillsScript(t *testing.T) {
	m, db, dir := newTestManager(t)
	script := writeScript(t, dir, "slow.py", "print('started', flush=True)\nimport time\ntime.sleep(30)\n")
	p := profile(t, script, "timeout", json.Number("0.5"))
	runID, _ := m.StartProfileRun(p, nil, nil, "manual", nil)
	r := waitForFinish(t, m, runID, 15*time.Second)
	if r.Status != "failed" {
		t.Errorf("status = %q, want failed", r.Status)
	}
	if !r.TimedOut {
		t.Error("TimedOut flag not set")
	}
	joined := strings.Join(r.Output, "")
	if !strings.Contains(joined, "Timed out after 0.5s and was killed.") {
		t.Errorf("timeout message missing: %q", joined)
	}
	history, _ := db.LoadHistory()
	if len(history) != 1 || history[0].Get("timed_out") != true {
		t.Errorf("history timed_out missing: %v", history)
	}
}

// TestTimeoutNotFlaggedWhenScriptFinishesFirst guards the watchdog race:
// a script that finishes just before the deadline completes normally.
func TestTimeoutNotFlaggedWhenScriptFinishesFirst(t *testing.T) {
	m, _, dir := newTestManager(t)
	script := writeScript(t, dir, "quick.py", "print('fast')\n")
	p := profile(t, script, "timeout", json.Number("30"))
	runID, _ := m.StartProfileRun(p, nil, nil, "manual", nil)
	r := waitForFinish(t, m, runID, 10*time.Second)
	if r.Status != "completed" || r.TimedOut {
		t.Errorf("status=%q timedOut=%v, want completed/no timeout", r.Status, r.TimedOut)
	}
}

func TestCancelRun(t *testing.T) {
	m, db, dir := newTestManager(t)
	script := writeScript(t, dir, "hang.py", "print('ready', flush=True)\nimport time\ntime.sleep(60)\n")
	runID, _ := m.StartProfileRun(profile(t, script), nil, nil, "manual", nil)

	// Wait until the script is actually running before cancelling.
	deadline := time.Now().Add(10 * time.Second)
	for time.Now().Before(deadline) {
		snap := m.Poll(runID)
		if snap != nil && strings.Contains(strings.Join(toStrings(snap.Get("output")), ""), "ready") {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	if !m.CancelRun(runID) {
		t.Fatal("CancelRun returned false for a running run")
	}
	r := waitForFinish(t, m, runID, 10*time.Second)
	if r.Status != "cancelled" {
		t.Errorf("status = %q, want cancelled", r.Status)
	}
	if !strings.Contains(strings.Join(r.Output, ""), CancelMessage) {
		t.Errorf("cancel message missing: %q", strings.Join(r.Output, ""))
	}
	// A second cancel reports nothing to cancel.
	if m.CancelRun(runID) {
		t.Error("cancelling a finished run should return false")
	}
	history, _ := db.LoadHistory()
	if len(history) != 1 || ordjson.GetStr(history[0], "status") != "cancelled" {
		t.Errorf("history not updated to cancelled: %v", history)
	}
}

func TestSequentialWorkflow(t *testing.T) {
	m, db, dir := newTestManager(t)
	s1 := writeScript(t, dir, "a.py", "print('A out')\n")
	s2 := writeScript(t, dir, "b.py", "print('B out')\n")
	pa := profile(t, s1, "id", "pa", "name", "Step A")
	pb := profile(t, s2, "id", "pb", "name", "Step B")
	if err := db.Save(store.ColProfiles, []*ordjson.OMap{pa, pb}); err != nil {
		t.Fatal(err)
	}
	wf := ordjson.New().Set("id", "wf1").Set("name", "Chain").Set("steps", []any{
		ordjson.New().Set("profile_id", "pa"),
		ordjson.New().Set("profile_id", "pb"),
	})
	runID := m.StartWorkflowRun(wf, "manual", nil)
	r := waitForFinish(t, m, runID, 20*time.Second)
	if r.Status != "completed" {
		t.Errorf("status = %q; log=%v", r.Status, r.WorkflowLog)
	}
	logText := strings.Join(r.WorkflowLog, "\n")
	for _, want := range []string{
		"Starting workflow: Chain",
		"[RUN] Step 1: Step A",
		"[DONE] Step 1 (Step A) completed successfully",
		"[RUN] Step 2: Step B",
		"[DONE] Step 2 (Step B) completed successfully",
		"Workflow completed",
	} {
		if !strings.Contains(logText, want) {
			t.Errorf("workflow log missing %q in:\n%s", want, logText)
		}
	}
	// Steps must be present with per-step output, in insertion order.
	if r.Steps.Len() != 2 {
		t.Fatalf("got %d steps, want 2", r.Steps.Len())
	}
	first := ordjson.GetMap(r.Steps, "1. Step A")
	if first == nil || ordjson.GetStr(first, "status") != "completed" {
		t.Errorf("step 1 wrong: %v", first)
	}
	history, _ := db.LoadHistory()
	if len(history) != 1 {
		t.Fatalf("history entries = %d, want 1", len(history))
	}
	entry := history[0]
	storedSteps := ordjson.GetMap(entry, "steps")
	if storedSteps == nil || storedSteps.Len() != 2 {
		t.Fatalf("history steps missing: %v", entry.Get("steps"))
	}
	if storedSteps.Keys()[0] != "1. Step A" {
		t.Errorf("step key order wrong: %v", storedSteps.Keys())
	}
}

func TestWorkflowStopsOnFirstFailureWithoutContinueOnError(t *testing.T) {
	m, db, dir := newTestManager(t)
	s1 := writeScript(t, dir, "ok.py", "print('fine')\n")
	s2 := writeScript(t, dir, "bad.py", "import sys\nsys.exit(1)\n")
	s3 := writeScript(t, dir, "never.py", "print('never')\n")
	pa := profile(t, s1, "id", "pa", "name", "Good")
	pb := profile(t, s2, "id", "pb", "name", "Bad")
	pc := profile(t, s3, "id", "pc", "name", "Never")
	if err := db.Save(store.ColProfiles, []*ordjson.OMap{pa, pb, pc}); err != nil {
		t.Fatal(err)
	}
	wf := ordjson.New().Set("id", "wf1").Set("name", "Chain").Set("steps", []any{
		ordjson.New().Set("profile_id", "pa"),
		ordjson.New().Set("profile_id", "pb"),
		ordjson.New().Set("profile_id", "pc"),
	})
	runID := m.StartWorkflowRun(wf, "manual", nil)
	r := waitForFinish(t, m, runID, 20*time.Second)
	if r.Status != "failed" {
		t.Errorf("status = %q, want failed", r.Status)
	}
	logText := strings.Join(r.WorkflowLog, "\n")
	if !strings.Contains(logText, "[ABORT] Workflow stopped due to error.") {
		t.Errorf("abort line missing:\n%s", logText)
	}
	if strings.Contains(logText, "Never") {
		t.Errorf("third step should not have run:\n%s", logText)
	}
}

func TestWorkflowContinueOnErrorRunsAllSteps(t *testing.T) {
	m, db, dir := newTestManager(t)
	s1 := writeScript(t, dir, "bad.py", "import sys\nsys.exit(1)\n")
	s2 := writeScript(t, dir, "ok.py", "print('still here')\n")
	pa := profile(t, s1, "id", "pa", "name", "Bad")
	pb := profile(t, s2, "id", "pb", "name", "Good")
	if err := db.Save(store.ColProfiles, []*ordjson.OMap{pa, pb}); err != nil {
		t.Fatal(err)
	}
	wf := ordjson.New().Set("id", "wf1").Set("name", "Chain").
		Set("continue_on_error", true).
		Set("steps", []any{
			ordjson.New().Set("profile_id", "pa"),
			ordjson.New().Set("profile_id", "pb"),
		})
	runID := m.StartWorkflowRun(wf, "manual", nil)
	r := waitForFinish(t, m, runID, 20*time.Second)
	if r.Status != "failed" {
		t.Errorf("status = %q, want failed (a step failed)", r.Status)
	}
	logText := strings.Join(r.WorkflowLog, "\n")
	if !strings.Contains(logText, "[FAIL] Step 1 (Bad) exited with code 1") {
		t.Errorf("fail line wrong:\n%s", logText)
	}
	// Script output lives in the step records, not the workflow log.
	steps := r.Steps
	step2 := ordjson.GetMap(steps, "2. Good")
	if step2 == nil || ordjson.GetStr(step2, "status") != "completed" {
		t.Errorf("second step did not complete despite continue_on_error: %v", step2)
	}
}

func TestParallelWorkflowRunsConcurrently(t *testing.T) {
	m, db, dir := newTestManager(t)
	// Three scripts that all sleep 1s; sequentially that is 3s, in
	// parallel under 2s.
	scripts := make([]*ordjson.OMap, 3)
	steps := []any{}
	for i := 0; i < 3; i++ {
		path := writeScript(t, dir, fmt.Sprintf("p%d.py", i), "import time\ntime.sleep(1)\nprint('done')\n")
		p := profile(t, path, "id", fmt.Sprintf("p%d", i), "name", fmt.Sprintf("Par %d", i))
		scripts[i] = p
		steps = append(steps, ordjson.New().Set("profile_id", p.Get("id")))
	}
	if err := db.Save(store.ColProfiles, scripts); err != nil {
		t.Fatal(err)
	}
	wf := ordjson.New().Set("id", "wf1").Set("name", "Par").Set("steps", []any{
		ordjson.New().Set("type", "parallel").Set("profiles", steps),
	})
	runID := m.StartWorkflowRun(wf, "manual", nil)
	start := time.Now()
	r := waitForFinish(t, m, runID, 20*time.Second)
	elapsed := time.Since(start)
	if r.Status != "completed" {
		t.Errorf("status = %q; log=%v", r.Status, r.WorkflowLog)
	}
	if elapsed > 2500*time.Millisecond {
		t.Errorf("parallel group took %v — steps did not run concurrently", elapsed)
	}
	logText := strings.Join(r.WorkflowLog, "\n")
	if !strings.Contains(logText, "[PARALLEL] Running 3 steps: Par 0, Par 1, Par 2") {
		t.Errorf("parallel log line wrong:\n%s", logText)
	}
}

func TestWorkflowMissingProfileSkips(t *testing.T) {
	m, db, dir := newTestManager(t)
	s1 := writeScript(t, dir, "ok.py", "print('fine')\n")
	pa := profile(t, s1, "id", "pa", "name", "Good")
	if err := db.Save(store.ColProfiles, []*ordjson.OMap{pa}); err != nil {
		t.Fatal(err)
	}
	wf := ordjson.New().Set("id", "wf1").Set("name", "Chain").Set("steps", []any{
		ordjson.New().Set("profile_id", "ghost"),
		ordjson.New().Set("profile_id", "pa"),
	})
	runID := m.StartWorkflowRun(wf, "manual", nil)
	r := waitForFinish(t, m, runID, 20*time.Second)
	// Python behaviour: the missing profile is skipped with [SKIP] and,
	// without continue_on_error, marks the run failed.
	if r.Status != "failed" {
		t.Errorf("status = %q, want failed", r.Status)
	}
	logText := strings.Join(r.WorkflowLog, "\n")
	if !strings.Contains(logText, "[SKIP] Profile not found: ghost") {
		t.Errorf("skip line missing:\n%s", logText)
	}
}

func TestWorkflowMissingProfileFailsRunWithoutContinueOnError(t *testing.T) {
	m, _, _ := newTestManager(t)
	wf := ordjson.New().Set("id", "wf1").Set("name", "Chain").Set("steps", []any{
		ordjson.New().Set("profile_id", "ghost"),
	})
	runID := m.StartWorkflowRun(wf, "manual", nil)
	r := waitForFinish(t, m, runID, 10*time.Second)
	if r.Status != "failed" {
		t.Errorf("status = %q, want failed", r.Status)
	}
}

// TestWorkflowStepUsesProfileSnapshot exercises the embedded-snapshot
// resolution: steps that carry a "profile" dict use it instead of the
// live profile.
func TestWorkflowStepUsesProfileSnapshot(t *testing.T) {
	m, db, dir := newTestManager(t)
	script := writeScript(t, dir, "ok.py", "print('snapshot used')\n")
	pa := profile(t, script, "id", "pa", "name", "Snapshot Step")
	if err := db.Save(store.ColProfiles, []*ordjson.OMap{}); err != nil {
		t.Fatal(err)
	}
	wf := ordjson.New().Set("id", "wf1").Set("name", "Chain").Set("steps", []any{
		ordjson.New().Set("profile_id", "missing-live").Set("profile", pa),
	})
	runID := m.StartWorkflowRun(wf, "manual", nil)
	r := waitForFinish(t, m, runID, 20*time.Second)
	if r.Status != "completed" {
		t.Errorf("status = %q; log=%v", r.Status, r.WorkflowLog)
	}
	if !strings.Contains(strings.Join(r.Output, ""), "snapshot used") {
		t.Errorf("snapshot script did not run: %v", r.Output)
	}
	_ = db
}

func TestBuildCustomArgs(t *testing.T) {
	custom := []any{
		ordjson.New().Set("name", "--name").Set("type", "text").Set("default", "World"),
		ordjson.New().Set("name", "--rows").Set("type", "text").Set("default", "5"),
		ordjson.New().Set("name", "--verbose").Set("type", "checkbox"),
		ordjson.New().Set("name", "--day").Set("type", "date"),
		ordjson.New().Set("name", "").Set("default", "skipped"),
	}
	got := BuildCustomArgs(custom, nil)
	want := []string{"--name", "World", "--rows", "5"}
	if fmt.Sprint(got) != fmt.Sprint(want) {
		t.Errorf("got %v, want %v", got, want)
	}
	// Overrides win over defaults; unchecked checkbox is omitted; dates
	// are reformatted.
	overrides := ordjson.New().
		Set("--name", "Override")
	custom2 := []any{
		ordjson.New().Set("name", "--name").Set("default", "World"),
		ordjson.New().Set("name", "--verbose").Set("type", "checkbox"),
		ordjson.New().Set("name", "--day").Set("type", "date").Set("format", "%d/%m/%Y"),
	}
	got2 := BuildCustomArgs(custom2, overrides)
	if fmt.Sprint(got2) != fmt.Sprint([]string{"--name", "Override"}) {
		t.Errorf("got %v", got2)
	}
	overrides3 := ordjson.New().Set("--verbose", "true").Set("--day", "2026-05-01")
	got3 := BuildCustomArgs(custom2, overrides3)
	// --name keeps its default because the override does not mention it.
	if fmt.Sprint(got3) != fmt.Sprint([]string{"--name", "World", "--verbose", "--day", "01/05/2026"}) {
		t.Errorf("got %v", got3)
	}
}

func TestParseTimeout(t *testing.T) {
	cases := []struct {
		in   any
		want float64
	}{
		{nil, 0}, {"", 0}, {"abc", 0}, {"0", 0}, {"-2", 0}, {"0.0", 0},
		{"30", 30}, {json.Number("2.5"), 2.5}, {float64(10), 10},
		{true, 0},
	}
	for _, c := range cases {
		if got := ParseTimeout(c.in); got != c.want {
			t.Errorf("ParseTimeout(%v) = %v, want %v", c.in, got, c.want)
		}
	}
}

func TestFormatDateValue(t *testing.T) {
	if got := FormatDateValue("2026-05-01", "%d/%m/%Y"); got != "01/05/2026" {
		t.Errorf("got %q", got)
	}
	if got := FormatDateValue("2026-05-01", ""); got != "2026-05-01" {
		t.Errorf("default format should pass through, got %q", got)
	}
	if got := FormatDateValue("not-a-date", "%d/%m/%Y"); got != "not-a-date" {
		t.Errorf("invalid input should pass through, got %q", got)
	}
}

func TestPruneActiveRuns(t *testing.T) {
	m, _, _ := newTestManager(t)
	now := float64(time.Now().Unix())
	m.mu.Lock()
	// Two expired finished runs, three live ones.
	for _, spec := range []struct {
		id     string
		status string
		fin    float64
	}{
		{"old1", "completed", now - FinishedRunTTLSeconds - 10},
		{"old2", "failed", now - FinishedRunTTLSeconds - 5},
		{"live1", "running", 0},
		{"live2", "running", 0},
		{"fresh", "completed", now - 5},
	} {
		m.runs[spec.id] = &Run{ID: spec.id, Status: spec.status, FinishedAt: spec.fin}
	}
	m.mu.Unlock()
	m.Prune()
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, ok := m.runs["old1"]; ok {
		t.Error("old1 should have been pruned")
	}
	if _, ok := m.runs["old2"]; ok {
		t.Error("old2 should have been pruned")
	}
	if _, ok := m.runs["fresh"]; !ok {
		t.Error("fresh should be kept")
	}
	if _, ok := m.runs["live1"]; !ok {
		t.Error("running runs are never pruned")
	}
}

func TestPollSnapshotShape(t *testing.T) {
	m, _, dir := newTestManager(t)
	script := writeScript(t, dir, "ok.py", "print('x')\n")
	runID, _ := m.StartProfileRun(profile(t, script), nil, nil, "manual", nil)
	waitForFinish(t, m, runID, 10*time.Second)
	snap := m.Poll(runID)
	if snap == nil {
		t.Fatal("Poll returned nil for a live run")
	}
	// The poll view carries exactly the fields the run panel renders.
	for _, key := range []string{"output", "workflow_log", "status", "returncode", "steps", "current_step", "command", "timed_out", "cancelled"} {
		if _, ok := snap.GetOK(key); !ok {
			t.Errorf("snapshot missing key %q", key)
		}
	}
	if snap.Get("command") == nil {
		t.Error("profile run should expose its command")
	}
	if m.Poll("nope") != nil {
		t.Error("unknown run should poll as nil")
	}
}

func TestConcurrentRunsAreIndependent(t *testing.T) {
	m, _, dir := newTestManager(t)
	var wg sync.WaitGroup
	ids := make([]string, 4)
	for i := 0; i < 4; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			script := writeScript(t, dir, fmt.Sprintf("c%d.py", i), fmt.Sprintf("print('run %d')\n", i))
			id, _ := m.StartProfileRun(profile(t, script), nil, nil, "manual", nil)
			ids[i] = id
		}(i)
	}
	wg.Wait()
	for i, id := range ids {
		r := waitForFinish(t, m, id, 10*time.Second)
		if r.Status != "completed" {
			t.Errorf("run %d status %q", i, r.Status)
		}
	}
	if got := len(m.PollAll().Keys()); got < 4 {
		t.Errorf("PollAll has %d runs, want >= 4", got)
	}
}
