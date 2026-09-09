package store

import (
	"log/slog"
	"strings"

	"launchcontrol/internal/ordjson"
)

// HistoryEntryOptions carries the optional fields save_history accepts;
// zero-value fields are omitted from the stored entry exactly like the
// Python keyword arguments defaulting to None.
type HistoryEntryOptions struct {
	WorkflowLog  []string
	Steps        *ordjson.OMap
	Command      []string
	Trigger      string
	ScheduleID   string
	ScheduleName string
	TimedOut     bool
}

// LoadHistory returns the history collection, assigning ids to entries
// that lack one (mirroring load_history's backfill).
func (db *DB) LoadHistory() ([]*ordjson.OMap, error) {
	entries, err := db.Load("history")
	if err != nil {
		return nil, err
	}

	changed := false
	for _, entry := range entries {
		if ordjson.GetStr(entry, "id") == "" {
			entry.Set("id", NewID())
			changed = true
		}
	}
	if changed {
		if err := db.Save("history", entries); err != nil {
			return nil, err
		}
	}
	return entries, nil
}

// jsonInt stores an int as a json.Number so it round-trips as an int.
func jsonInt(n int) any { return ordjson.Number(float64(n)) }

// SaveHistory appends a run record so it shows in history immediately
// (status "running" while it executes).
func (db *DB) SaveHistory(runID, name, runType, status string, returnCode any, output []string, startedAt float64, opts HistoryEntryOptions) {
	entry := ordjson.New().
		Set("id", NewID()).
		Set("run_id", runID).
		Set("name", name).
		Set("type", runType).
		Set("status", status).
		Set("returncode", returnCode).
		Set("output", toStrings(output)).
		Set("output_preview", joinOutputPreview(output)).
		Set("started_at", ordjson.Number(startedAt)).
		Set("timestamp", ordjson.Number(nowSeconds()))
	if opts.Trigger != "" {
		entry.Set("trigger", opts.Trigger)
	}
	if opts.ScheduleID != "" {
		entry.Set("schedule_id", opts.ScheduleID)
	}
	if opts.ScheduleName != "" {
		entry.Set("schedule_name", opts.ScheduleName)
	}
	if opts.WorkflowLog != nil {
		entry.Set("workflow_log", toStrings(opts.WorkflowLog))
	}
	if opts.Steps != nil {
		entry.Set("steps", opts.Steps)
	}
	if opts.Command != nil {
		entry.Set("command", toStrings(opts.Command))
	}
	if opts.TimedOut {
		entry.Set("timed_out", true)
	}

	db.WithCollection("history", func() {
		history, err := db.LoadHistory()
		if err != nil {
			return
		}
		history = append(history, entry)
		// A failed save is logged, not fatal: the Python server also
		// kept serving if history bookkeeping did not stick.
		if err := db.Save("history", history); err != nil {
			slog.Warn("Cannot save history", "err", err)
		}
	})
}

// HistoryUpdate carries update_history's optional fields; nil pointers
// leave the stored value untouched (None in the Python keyword args).
type HistoryUpdate struct {
	Status      *string
	ReturnCode  *int
	Output      []string
	WorkflowLog []string
	Steps       *ordjson.OMap
	TimedOut    bool
}

// UpdateHistory updates the newest entry for runID in place. It reports
// whether a matching entry was found.
func (db *DB) UpdateHistory(runID string, upd HistoryUpdate) bool {
	updated := false
	db.WithCollection("history", func() {
		history, err := db.LoadHistory()
		if err != nil {
			return
		}

		var target *ordjson.OMap
		for _, entry := range history {
			if ordjson.GetStr(entry, "run_id") == runID {
				target = entry // the last match, like the Python loop
			}
		}
		if target == nil {
			return
		}

		if upd.Status != nil {
			target.Set("status", *upd.Status)
		}
		if upd.ReturnCode != nil {
			target.Set("returncode", jsonInt(*upd.ReturnCode))
		}
		if upd.Output != nil {
			target.Set("output", toStrings(upd.Output))
			target.Set("output_preview", joinOutputPreview(upd.Output))
		}
		if upd.WorkflowLog != nil {
			target.Set("workflow_log", toStrings(upd.WorkflowLog))
		}
		if upd.Steps != nil {
			target.Set("steps", upd.Steps)
		}
		if upd.TimedOut {
			target.Set("timed_out", true)
		}
		target.Set("timestamp", ordjson.Number(nowSeconds()))
		if err := db.Save("history", history); err != nil {
			slog.Warn("Cannot save history", "err", err)
		}
		updated = true
	})
	return updated
}

// RemoveHistory deletes entries matching pred and reports how many
// were removed. The load-modify-save runs under the history lock so
// entries written by concurrent run completions cannot be lost.
func (db *DB) RemoveHistory(pred func(*ordjson.OMap) bool) int {
	removed := 0
	db.WithCollection("history", func() {
		history, err := db.LoadHistory()
		if err != nil {
			return
		}

		remaining := make([]*ordjson.OMap, 0, len(history))
		for _, entry := range history {
			if pred(entry) {
				removed++
			} else {
				remaining = append(remaining, entry)
			}
		}
		if removed > 0 {
			if err := db.Save("history", remaining); err != nil {
				slog.Warn("Cannot save history", "err", err)
			}
		}
	})
	return removed
}

// ReplaceHistory atomically replaces the whole history collection.
func (db *DB) ReplaceHistory(entries []*ordjson.OMap) {
	db.WithCollection("history", func() {
		if err := db.Save("history", entries); err != nil {
			slog.Warn("Cannot save history", "err", err)
		}
	})
}

func toStrings(lines []string) []any {
	out := make([]any, len(lines))
	for i, l := range lines {
		out[i] = l
	}
	return out
}

// joinOutputPreview is output_preview: the last 20 lines joined, like
// Python's "".join(output[-20:]).
func joinOutputPreview(output []string) string {
	start := 0
	if len(output) > 20 {
		start = len(output) - 20
	}
	return strings.Join(output[start:], "")
}
