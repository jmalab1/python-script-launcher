package store

import (
	"encoding/json"
	"fmt"
	"strings"
	"testing"

	"launchcontrol/internal/ordjson"
)

// insertHistoryRow writes a raw row straight into SQLite, bypassing
// Save (which assigns ids and would paper over what we want to plant).
func insertHistoryRow(t *testing.T, db *DB, id, blob string) {
	t.Helper()
	_, err := db.sql.Exec(
		`INSERT INTO history (id, run_id, type, json) VALUES (?, 'run-legacy', 'command', ?)`,
		id, blob)
	if err != nil {
		t.Fatal(err)
	}
}

// TestLoadHistoryEmpty checks a fresh database: no history yet and no
// error.
func TestLoadHistoryEmpty(t *testing.T) {
	db, _ := openTestDB(t)
	entries, err := db.LoadHistory()
	if err != nil {
		t.Fatalf("LoadHistory on an empty database: %v", err)
	}
	if len(entries) != 0 {
		t.Fatalf("got %d entries, want 0", len(entries))
	}
}

// TestLoadHistoryBackfillsMissingIDs covers load_history's backfill: an
// entry stored without an id gets one assigned, and the fix is written
// back so it survives the next load.
func TestLoadHistoryBackfillsMissingIDs(t *testing.T) {
	db, _ := openTestDB(t)
	insertHistoryRow(t, db, "row1", `{"run_id": "run-1", "name": "Old"}`)

	entries, err := db.LoadHistory()
	if err != nil {
		t.Fatalf("LoadHistory: %v", err)
	}
	if len(entries) != 1 {
		t.Fatalf("got %d entries, want 1", len(entries))
	}
	id := ordjson.GetStr(entries[0], "id")
	if len(id) != 32 {
		t.Errorf("backfilled id should be a 32-char hex id, got %q", id)
	}

	again, err := db.Load("history")
	if err != nil {
		t.Fatal(err)
	}
	if got := ordjson.GetStr(again[0], "id"); got != id {
		t.Errorf("backfilled id was not saved: got %q, want %q", got, id)
	}
}

// TestLoadHistoryCorruptRecord checks that a row with malformed JSON
// surfaces as an error instead of being silently dropped.
func TestLoadHistoryCorruptRecord(t *testing.T) {
	db, _ := openTestDB(t)
	insertHistoryRow(t, db, "bad", `{not json`)

	if _, err := db.LoadHistory(); err == nil {
		t.Fatal("a corrupt history record should make LoadHistory fail")
	}
}

// TestSaveHistoryMinimal covers the fields every entry carries and
// checks that unset optional fields are simply absent, like the Python
// keyword arguments defaulting to None.
func TestSaveHistoryMinimal(t *testing.T) {
	db, _ := openTestDB(t)
	db.SaveHistory("run-1", "Backup", "command", "running", json.Number("0"),
		[]string{"line one", "line two"}, 1759234567.5, HistoryEntryOptions{})

	entries, err := db.LoadHistory()
	if err != nil {
		t.Fatalf("LoadHistory: %v", err)
	}
	if len(entries) != 1 {
		t.Fatalf("got %d entries, want 1", len(entries))
	}
	e := entries[0]

	if got := ordjson.GetStr(e, "run_id"); got != "run-1" {
		t.Errorf("run_id = %q", got)
	}
	if got := ordjson.GetStr(e, "name"); got != "Backup" {
		t.Errorf("name = %q", got)
	}
	if got := ordjson.GetStr(e, "type"); got != "command" {
		t.Errorf("type = %q", got)
	}
	if got := ordjson.GetStr(e, "status"); got != "running" {
		t.Errorf("status = %q", got)
	}
	if len(ordjson.GetStr(e, "id")) != 32 {
		t.Errorf("entry should have a generated id, got %q", e.Get("id"))
	}
	if got, ok := e.Get("returncode").(json.Number); !ok || got.String() != "0" {
		t.Errorf("returncode = %v (%T), want json.Number \"0\"", e.Get("returncode"), e.Get("returncode"))
	}
	if got := ordjson.GetArr(e, "output"); len(got) != 2 || got[0] != "line one" || got[1] != "line two" {
		t.Errorf("output = %v", got)
	}
	if got := ordjson.GetStr(e, "output_preview"); got != "line oneline two" {
		t.Errorf("output_preview = %q", got)
	}
	if got, ok := e.Get("started_at").(json.Number); !ok || got.String() != ordjson.Number(1759234567.5).String() {
		t.Errorf("started_at = %v (%T), want %v", e.Get("started_at"), e.Get("started_at"), ordjson.Number(1759234567.5))
	}
	if _, ok := e.Get("timestamp").(json.Number); !ok {
		t.Errorf("timestamp should be a json.Number, got %v (%T)", e.Get("timestamp"), e.Get("timestamp"))
	}

	for _, key := range []string{"trigger", "schedule_id", "schedule_name", "workflow_log", "steps", "command", "timed_out"} {
		if _, present := e.GetOK(key); present {
			t.Errorf("optional field %q should be absent when not set", key)
		}
	}
}

// TestSaveHistoryWithOptions covers every optional field landing in the
// entry under the keys the Python implementation used.
func TestSaveHistoryWithOptions(t *testing.T) {
	db, _ := openTestDB(t)
	steps := ordjson.New().Set("1", rec("command", "echo hi"))
	db.SaveHistory("run-2", "Nightly backup", "workflow", "success", nil,
		[]string{"done"}, 1.5, HistoryEntryOptions{
			WorkflowLog:  []string{"step 1 ok"},
			Steps:        steps,
			Command:      []string{"echo", "hi"},
			Trigger:      "schedule",
			ScheduleID:   "sched-1",
			ScheduleName: "Nightly",
			TimedOut:     true,
		})

	entries, err := db.LoadHistory()
	if err != nil {
		t.Fatalf("LoadHistory: %v", err)
	}
	e := entries[0]

	if got := ordjson.GetStr(e, "trigger"); got != "schedule" {
		t.Errorf("trigger = %q", got)
	}
	if got := ordjson.GetStr(e, "schedule_id"); got != "sched-1" {
		t.Errorf("schedule_id = %q", got)
	}
	if got := ordjson.GetStr(e, "schedule_name"); got != "Nightly" {
		t.Errorf("schedule_name = %q", got)
	}
	if got := ordjson.GetArr(e, "workflow_log"); len(got) != 1 || got[0] != "step 1 ok" {
		t.Errorf("workflow_log = %v", got)
	}
	storedSteps := ordjson.GetMap(e, "steps")
	if storedSteps == nil {
		t.Fatal("steps missing")
	}
	if got := ordjson.GetStr(ordjson.GetMap(storedSteps, "1"), "command"); got != "echo hi" {
		t.Errorf("steps[1].command = %q", got)
	}
	if got := ordjson.GetArr(e, "command"); len(got) != 2 || got[0] != "echo" || got[1] != "hi" {
		t.Errorf("command = %v", got)
	}
	if !ordjson.GetBool(e, "timed_out") {
		t.Error("timed_out should be true")
	}

	// A nil returncode is stored as a present-but-null value, the same
	// shape Python's json.dumps wrote for None.
	if rc, present := e.GetOK("returncode"); !present || rc != nil {
		t.Errorf("returncode = %v (present=%v), want null", rc, present)
	}
}

// TestSaveHistoryUnicodeRoundTrip pins the ensure_ascii=False storage
// shape: non-ASCII text goes to SQLite as UTF-8 and reads back
// unchanged.
func TestSaveHistoryUnicodeRoundTrip(t *testing.T) {
	db, _ := openTestDB(t)
	db.SaveHistory("run-u", "Résumé 日本語", "command", "success", json.Number("0"),
		[]string{"héllo"}, 1.0, HistoryEntryOptions{})

	entries, err := db.LoadHistory()
	if err != nil {
		t.Fatalf("LoadHistory: %v", err)
	}
	if got := ordjson.GetStr(entries[0], "name"); got != "Résumé 日本語" {
		t.Errorf("name = %q", got)
	}
	if got := ordjson.GetArr(entries[0], "output"); len(got) != 1 || got[0] != "héllo" {
		t.Errorf("output = %v", got)
	}
}

// TestUpdateHistoryUpdatesNewestMatch: two entries share a run_id, the
// update lands on the last (newest) one and the earlier entry stays
// untouched. Fields left nil must not change the entry.
func TestUpdateHistoryUpdatesNewestMatch(t *testing.T) {
	db, _ := openTestDB(t)
	db.SaveHistory("run-1", "First", "command", "running", json.Number("-1"),
		[]string{"early"}, 1.0, HistoryEntryOptions{})
	db.SaveHistory("run-1", "Second", "command", "running", json.Number("-1"),
		[]string{"late"}, 2.0, HistoryEntryOptions{})

	status := "success"
	rc := 0
	if !db.UpdateHistory("run-1", HistoryUpdate{Status: &status, ReturnCode: &rc}) {
		t.Fatal("UpdateHistory reported no match")
	}

	entries, err := db.LoadHistory()
	if err != nil {
		t.Fatalf("LoadHistory: %v", err)
	}
	if len(entries) != 2 {
		t.Fatalf("got %d entries, want 2", len(entries))
	}
	first, last := entries[0], entries[1]

	if ordjson.GetStr(first, "status") != "running" || ordjson.GetStr(first, "name") != "First" {
		t.Errorf("the older entry was modified: %v", first)
	}
	if got := ordjson.GetStr(last, "status"); got != "success" {
		t.Errorf("status = %q, want success", got)
	}
	if got := ordjson.GetStr(last, "name"); got != "Second" {
		t.Errorf("name should be untouched, got %q", got)
	}
	if got, ok := last.Get("returncode").(json.Number); !ok || got.String() != "0" {
		t.Errorf("returncode = %v (%T), want json.Number \"0\"", last.Get("returncode"), last.Get("returncode"))
	}
	if got := ordjson.GetArr(last, "output"); len(got) != 1 || got[0] != "late" {
		t.Errorf("nil Output must leave output untouched, got %v", got)
	}
	if _, present := last.GetOK("workflow_log"); present {
		t.Error("nil WorkflowLog must not add workflow_log")
	}
}

// TestUpdateHistoryFullUpdate covers every writable field, including
// output_preview being recomputed alongside output.
func TestUpdateHistoryFullUpdate(t *testing.T) {
	db, _ := openTestDB(t)
	db.SaveHistory("run-1", "Job", "command", "running", json.Number("-1"),
		[]string{"old"}, 1.0, HistoryEntryOptions{})

	status := "timeout"
	rc := 124
	steps := ordjson.New().Set("1", rec("command", "x"))
	ok := db.UpdateHistory("run-1", HistoryUpdate{
		Status:      &status,
		ReturnCode:  &rc,
		Output:      []string{"out1", "out2"},
		WorkflowLog: []string{"a", "b"},
		Steps:       steps,
		TimedOut:    true,
	})
	if !ok {
		t.Fatal("UpdateHistory reported no match")
	}

	entries, err := db.LoadHistory()
	if err != nil {
		t.Fatalf("LoadHistory: %v", err)
	}
	e := entries[0]

	if got := ordjson.GetStr(e, "status"); got != "timeout" {
		t.Errorf("status = %q", got)
	}
	if got, ok := e.Get("returncode").(json.Number); !ok || got.String() != "124" {
		t.Errorf("returncode = %v (%T), want json.Number \"124\"", e.Get("returncode"), e.Get("returncode"))
	}
	if got := ordjson.GetArr(e, "output"); len(got) != 2 || got[0] != "out1" || got[1] != "out2" {
		t.Errorf("output = %v", got)
	}
	if got := ordjson.GetStr(e, "output_preview"); got != "out1out2" {
		t.Errorf("output_preview = %q, want \"out1out2\"", got)
	}
	if got := ordjson.GetArr(e, "workflow_log"); len(got) != 2 || got[0] != "a" || got[1] != "b" {
		t.Errorf("workflow_log = %v", got)
	}
	if got := ordjson.GetMap(e, "steps"); got == nil || ordjson.GetMap(got, "1") == nil {
		t.Errorf("steps = %v", e.Get("steps"))
	}
	if !ordjson.GetBool(e, "timed_out") {
		t.Error("timed_out should be true")
	}
}

// TestUpdateHistoryNoMatch: an unknown run_id reports false and leaves
// the stored entries alone.
func TestUpdateHistoryNoMatch(t *testing.T) {
	db, _ := openTestDB(t)
	db.SaveHistory("run-1", "Job", "command", "running", json.Number("-1"),
		[]string{"out"}, 1.0, HistoryEntryOptions{})

	if db.UpdateHistory("run-missing", HistoryUpdate{}) {
		t.Fatal("UpdateHistory should report false for an unknown run_id")
	}
	entries, _ := db.LoadHistory()
	if len(entries) != 1 || ordjson.GetStr(entries[0], "status") != "running" {
		t.Errorf("entries changed despite no match: %v", entries)
	}
}

// TestRemoveHistory: only entries matching the predicate disappear and
// the reported count matches; removing nothing changes nothing.
func TestRemoveHistory(t *testing.T) {
	db, _ := openTestDB(t)
	db.SaveHistory("run-a", "A1", "command", "success", json.Number("0"), nil, 1.0, HistoryEntryOptions{})
	db.SaveHistory("run-b", "B", "command", "success", json.Number("0"), nil, 2.0, HistoryEntryOptions{})
	db.SaveHistory("run-a", "A2", "command", "success", json.Number("0"), nil, 3.0, HistoryEntryOptions{})

	removed := db.RemoveHistory(func(e *ordjson.OMap) bool {
		return ordjson.GetStr(e, "run_id") == "run-a"
	})
	if removed != 2 {
		t.Fatalf("removed %d entries, want 2", removed)
	}

	entries, err := db.LoadHistory()
	if err != nil {
		t.Fatalf("LoadHistory: %v", err)
	}
	if len(entries) != 1 || ordjson.GetStr(entries[0], "run_id") != "run-b" {
		t.Fatalf("remaining entries wrong: %v", entries)
	}

	if again := db.RemoveHistory(func(*ordjson.OMap) bool { return false }); again != 0 {
		t.Errorf("removing nothing should report 0, got %d", again)
	}
}

// TestReplaceHistory swaps the whole collection in one go; entries
// without an id still get one, like any other save. Replacing with
// nothing empties the collection.
func TestReplaceHistory(t *testing.T) {
	db, _ := openTestDB(t)
	db.SaveHistory("run-1", "Old", "command", "success", json.Number("0"), nil, 1.0, HistoryEntryOptions{})
	db.SaveHistory("run-2", "Also old", "command", "success", json.Number("0"), nil, 2.0, HistoryEntryOptions{})

	db.ReplaceHistory([]*ordjson.OMap{
		rec("run_id", "run-9", "type", "command", "name", "Fresh"),
	})

	entries, err := db.LoadHistory()
	if err != nil {
		t.Fatalf("LoadHistory: %v", err)
	}
	if len(entries) != 1 {
		t.Fatalf("got %d entries, want 1", len(entries))
	}
	if got := ordjson.GetStr(entries[0], "run_id"); got != "run-9" {
		t.Errorf("run_id = %q, want run-9", got)
	}
	if ordjson.GetStr(entries[0], "id") == "" {
		t.Error("replaced entry should have an assigned id")
	}

	db.ReplaceHistory(nil)
	entries, _ = db.LoadHistory()
	if len(entries) != 0 {
		t.Errorf("replacing with nothing should empty the collection, got %d entries", len(entries))
	}
}

// TestJoinOutputPreview: the preview is the last 20 output lines joined
// with no separator, like Python's "".join(output[-20:]).
func TestJoinOutputPreview(t *testing.T) {
	if got := joinOutputPreview([]string{"a", "b", "c"}); got != "abc" {
		t.Errorf("short output: got %q, want \"abc\"", got)
	}
	if got := joinOutputPreview(nil); got != "" {
		t.Errorf("empty output: got %q, want \"\"", got)
	}

	var lines []string
	for i := 0; i < 25; i++ {
		lines = append(lines, fmt.Sprintf("L%02d", i))
	}
	if got, want := joinOutputPreview(lines), strings.Join(lines[5:], ""); got != want {
		t.Errorf("long output: got %q, want %q", got, want)
	}

	exact := make([]string, 20)
	for i := range exact {
		exact[i] = "x"
	}
	if got := joinOutputPreview(exact); got != strings.Repeat("x", 20) {
		t.Errorf("exactly 20 lines should not be trimmed, got %q", got)
	}
}

// TestToStrings: lines keep their order and values; nil gives an empty
// list so the stored JSON always holds a real array.
func TestToStrings(t *testing.T) {
	got := toStrings([]string{"a", "b"})
	if len(got) != 2 || got[0] != "a" || got[1] != "b" {
		t.Errorf("got %v, want [a b]", got)
	}
	if n := len(toStrings(nil)); n != 0 {
		t.Errorf("nil input should give an empty list, got %v", toStrings(nil))
	}
}

// TestJSONInt: ints must store as JSON integer literals (json.Number),
// not floats that would come back reformatted and change the bytes.
func TestJSONInt(t *testing.T) {
	for _, tc := range []struct {
		in   int
		want string
	}{{0, "0"}, {5, "5"}, {-3, "-3"}, {124, "124"}} {
		n, ok := jsonInt(tc.in).(json.Number)
		if !ok || n.String() != tc.want {
			t.Errorf("jsonInt(%d) = %v (%T), want json.Number %q", tc.in, jsonInt(tc.in), jsonInt(tc.in), tc.want)
		}
	}
}
