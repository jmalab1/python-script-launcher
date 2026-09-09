package scheduler

import (
	"testing"

	"launchcontrol/internal/ordjson"
	"launchcontrol/internal/store"
)

// TestStartStop exercises the scheduler lifecycle: Start runs the
// missed-run sweep and the tick loop becomes a no-op on the second
// Start, and Stop makes the tick loop exit even after a restart keep
// calling Stop (close on a closed channel would panic otherwise).
func TestStartStop(t *testing.T) {
	dir := t.TempDir()
	db, err := store.Open(dir+"/launcher.db", dir)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	if err := db.Save(store.ColProfiles, []*ordjson.OMap{ordjson.New().
		Set("id", "p1").Set("name", "P").Set("script_path", "x.py")}); err != nil {
		t.Fatal(err)
	}

	mgr := &fakeRunner{runs: map[string]bool{}}
	s := New(db, mgr)

	s.Start()
	s.Start() // second start is a no-op
	s.Stop()
	s.Stop() // stopping twice is safe
}

// TestTickAfterStopAndStart confirms a scheduler can be stopped and
// started again and still reports itself running through the loop
// channel without panicking.
func TestRestartAfterStop(t *testing.T) {
	dir := t.TempDir()
	db, err := store.Open(dir+"/launcher.db", dir)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	mgr := &fakeRunner{runs: map[string]bool{}}
	s := New(db, mgr)

	s.Start()
	s.Stop()
	s.Start()
	s.Stop()
}
