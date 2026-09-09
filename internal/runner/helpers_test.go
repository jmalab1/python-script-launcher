package runner

import (
	"errors"
	"testing"

	"launchcontrol/internal/ordjson"
)

// TestIsRunning checks the scheduler-facing helper: a run counts as
// running only while its status says so.
func TestIsRunning(t *testing.T) {
	m, _, _ := newTestManager(t)

	if m.IsRunning("nope") {
		t.Fatal("unknown id should not be running")
	}

	r := &Run{ID: "r1", Status: "running"}
	m.mu.Lock()
	m.runs["r1"] = r
	m.mu.Unlock()

	if !m.IsRunning("r1") {
		t.Fatal("running status should report running")
	}

	r.Status = "finished"
	if m.IsRunning("r1") {
		t.Fatal("finished status should not report running")
	}
}

// TestRecordSpawnError checks that a spawn failure is turned into the
// same representation as a failed process: an output line ending in a
// newline and a return code of -1 both on the run and in the result
// pointer.
func TestRecordSpawnError(t *testing.T) {
	m, _, _ := newTestManager(t)

	r := &Run{ID: "r1", Status: "running"}
	m.mu.Lock()
	m.runs["r1"] = r
	m.mu.Unlock()

	var result int
	var stepOutput []string

	m.recordSpawnError(r, &result, errors.New("spawn boom"), &stepOutput)

	if r.ReturnCode == nil || *r.ReturnCode != -1 {
		t.Fatalf("run return code should be -1, got %v", r.ReturnCode)
	}
	if result != -1 {
		t.Fatalf("result should be -1, got %d", result)
	}
	if len(r.Output) != 1 || r.Output[0] != "ERROR: spawn boom\n" {
		t.Fatalf("output line wrong: %v", r.Output)
	}
	if len(stepOutput) != 1 {
		t.Fatalf("step output should have one line, got %v", stepOutput)
	}
}

// TestStepToJSON checks the run-panel rendering of one step: fields
// pass through and a nested output array is copied (mutating the copy
// must not affect the stored step).
func TestStepToJSON(t *testing.T) {
	step := ordjson.New().
		Set("name", "Main").
		Set("status", "running").
		Set("output", []any{"a", "b"})

	out := stepToJSON(step)

	if out.Get("name") != "Main" || out.Get("status") != "running" {
		t.Fatalf("fields not preserved: %v", out)
	}
	copied, _ := out.Get("output").([]any)
	copied[0] = "mutated"
	if step.Get("output").([]any)[0] != "a" {
		t.Fatal("output array should be a copy, not shared with the step")
	}

	// A non-array "output" value is passed through untouched.
	bad := ordjson.New().Set("output", 42)
	if got := stepToJSON(bad).Get("output"); got != 42 {
		t.Fatalf("non-array output should pass through, got %v", got)
	}
}
