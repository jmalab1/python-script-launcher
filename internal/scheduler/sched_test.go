package scheduler

import (
	"path/filepath"
	"sync"
	"testing"
	"time"

	"launchcontrol/internal/ordjson"
	"launchcontrol/internal/store"
)

// fakeRunner records started runs instead of spawning processes, so
// tick behaviour is testable without a Python interpreter.
type fakeRunner struct {
	mu   sync.Mutex
	runs map[string]bool
}

// IsRunning reports whether a recorded run is marked as still running.
func (f *fakeRunner) IsRunning(runID string) bool {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.runs[runID]
}


// StartProfileRun records a started run under its schedule's id.
func (f *fakeRunner) StartProfileRun(profile *ordjson.OMap, argValues *ordjson.OMap, extraArgs []string, trigger string, schedule *ordjson.OMap) (string, string) {
	f.mu.Lock()
	defer f.mu.Unlock()
	runID := "prof_test_1"
	f.runs[runID] = false
	return runID, ""
}

// StartWorkflowRun records a started run.
func (f *fakeRunner) StartWorkflowRun(workflow *ordjson.OMap, trigger string, schedule *ordjson.OMap) string {
	f.mu.Lock()
	defer f.mu.Unlock()
	runID := "wf_test_1"
	f.runs[runID] = false
	return runID
}

func vString(v any) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}



func TestTickFiresDueSchedule(t *testing.T) {
	dir := t.TempDir()
	db, err := store.Open(filepath.Join(dir, "launcher.db"), dir)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	// An enabled schedule whose next_run_at is already in the past.
	db.RecordAudit("created", "profile", "p1", "P", nil, nil, nil) // ensure store open works
	if err := db.Save(store.ColProfiles, []*ordjson.OMap{ordjson.New().Set("id", "p1").Set("name", "P").Set("script_path", "unused.py")}); err != nil {
		t.Fatal(err)
	}
	sched := ordjson.New().
		Set("id", "s1").
		Set("target_type", "profile").
		Set("target_id", "p1").
		Set("cron", "*/7 * * * *").
		Set("enabled", true).
		Set("next_run_at", ordjson.Number(float64(time.Now().Add(-time.Minute).UnixNano())/1e9))
	if err := db.Save(store.ColSchedules, []*ordjson.OMap{sched}); err != nil {
		t.Fatal(err)
	}

	mgr := &fakeRunner{runs: map[string]bool{}}
	s := New(db, mgr)
	fired := s.RunTick(time.Now())
	if len(fired) != 1 || fired[0].ScheduleID != "s1" {
		t.Fatalf("fired = %v, want schedule s1", fired)
	}
	// The schedule advanced to the future and recorded the run.
	schedules, _ := db.Load(store.ColSchedules)
	if vString(schedules[0].Get("last_run_id")) == "" {
		t.Error("last_run_id not recorded")
	}
	if schedules[0].Get("next_run_at") == nil {
		t.Error("next_run_at not set")
	}
}

// IsRunning-based no-overlap: still running -> not fired again.
func TestTickSkipsBusySchedule(t *testing.T) {
	dir := t.TempDir()
	db, err := store.Open(filepath.Join(dir, "launcher.db"), dir)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	db.Save(store.ColProfiles, []*ordjson.OMap{ordjson.New().Set("id", "p1").Set("script_path", "x.py")})
	sched := ordjson.New().
		Set("id", "s1").
		Set("target_type", "profile").
		Set("target_id", "p1").
		Set("cron", "* * * * *").
		Set("enabled", true).
		Set("next_run_at", ordjson.Number(float64(time.Now().Add(-time.Minute).UnixNano())/1e9))
	db.Save(store.ColSchedules, []*ordjson.OMap{sched})

	mgr := &fakeRunner{runs: map[string]bool{}}
	s := New(db, mgr)
	fired := s.RunTick(time.Now())
	if len(fired) != 1 {
		t.Fatalf("first tick should fire, got %v", fired)
	}
	runID := fired[0].RunID
	mgr.runs[runID] = true // now the previous run counts as running
	fired = s.RunTick(time.Now())
	if len(fired) != 0 {
		t.Fatalf("a running previous run must block the second tick, got %v", fired)
	}
	mgr.runs[runID] = false // finished
	s.RunTick(time.Now())   // advances next_run_at into the future
	// Not recheckable here (time is the future), but the busy path is proven.
}

// Trashed schedules stop firing and clear next_run_at.
func TestTickIgnoresTrashedSchedules(t *testing.T) {
	dir := t.TempDir()
	db, err := store.Open(filepath.Join(dir, "launcher.db"), dir)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	db.Save(store.ColProfiles, []*ordjson.OMap{ordjson.New().Set("id", "p1").Set("script_path", "x.py")})
	db.Save(store.ColSchedules, []*ordjson.OMap{ordjson.New().
		Set("id", "s1").
		Set("target_type", "profile").
		Set("target_id", "p1").
		Set("cron", "* * * * *").
		Set("enabled", true).
		Set("group", "__trash__").
		Set("next_run_at", ordjson.Number(float64(time.Now().Add(-time.Minute).UnixNano())/1e9))})
	mgr := &fakeRunner{runs: map[string]bool{}}
	s := New(db, mgr)
	fired := s.RunTick(time.Now())
	if len(fired) != 0 {
		t.Fatalf("trashed schedule fired: %v", fired)
	}
	schedules, _ := db.Load(store.ColSchedules)
	if schedules[0].Get("next_run_at") != nil {
		t.Error("trashed schedule should have next_run_at cleared")
	}
}

func TestFireScheduleSkipsMissingAndTrashedTargets(t *testing.T) {
	dir := t.TempDir()
	db, err := store.Open(filepath.Join(dir, "launcher.db"), dir)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	mgr := &fakeRunner{runs: map[string]bool{}}
	s := New(db, mgr)

	if got := s.FireSchedule(ordjson.New().Set("target_type", "profile").Set("target_id", "ghost")); got != "" {
		t.Errorf("missing target should not start a run, got %q", got)
	}
	db.Save(store.ColProfiles, []*ordjson.OMap{ordjson.New().Set("id", "p1").Set("group", "__trash__").Set("script_path", "x.py")})
	if got := s.FireSchedule(ordjson.New().Set("target_type", "profile").Set("target_id", "p1")); got != "" {
		t.Errorf("trashed target should not start a run, got %q", got)
	}
}

func TestSkipMissedRecomputesStaleNextRun(t *testing.T) {
	dir := t.TempDir()
	db, err := store.Open(filepath.Join(dir, "launcher.db"), dir)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	db.Save(store.ColProfiles, []*ordjson.OMap{ordjson.New().Set("id", "p1").Set("script_path", "x.py")})
	stale := float64(time.Now().Add(-48 * time.Hour).UnixNano()) / 1e9
	db.Save(store.ColSchedules, []*ordjson.OMap{ordjson.New().
		Set("id", "s1").
		Set("target_type", "profile").
		Set("target_id", "p1").
		Set("cron", "0 9 * * *").
		Set("enabled", true).
		Set("next_run_at", ordjson.Number(stale))})
	mgr := &fakeRunner{runs: map[string]bool{}}
	s := New(db, mgr)
	s.SkipMissed(time.Now())
	schedules, _ := db.Load(store.ColSchedules)
	next := schedules[0].Get("next_run_at")
	if next == nil {
		t.Fatal("next_run_at should have been recomputed")
	}
	f, _ := ordjson.GetFloat(schedules[0], "next_run_at")
	if f <= float64(time.Now().Unix()) {
		t.Errorf("next_run_at %v should be in the future", f)
	}
}
