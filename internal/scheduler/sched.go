package scheduler

import (
	"log/slog"
	"sync"
	"time"

	"launchcontrol/internal/ordjson"
	"launchcontrol/internal/store"
)

// Scheduler ticks in the background and starts runs for due schedules
// through the same code path as the web UI, so scheduled runs show up
// in history and the run panel.
type Scheduler struct {
	db   *store.DB
	Runs RunStarter

	stop chan struct{}

	started bool

	// lastScheduledRun maps schedule id -> the run id of its most recent
	// firing, used to avoid starting a new run while the previous one is
	// still active.
	lastScheduledRunMu sync.Mutex
	lastScheduledRun   map[string]string
}

// RunStarter is the slice of the runner the scheduler needs (kept as an
// interface so the scheduler does not depend on the runner package).
// Runs are identified by a (runID, busyCheck) pair: the scheduler starts
// runs and later asks whether the previous one is still active.
type RunStarter interface {
	StartProfileRun(profile *ordjson.OMap, argValues *ordjson.OMap, extraArgs []string, trigger string, schedule *ordjson.OMap) (string, string)
	StartWorkflowRun(workflow *ordjson.OMap, trigger string, schedule *ordjson.OMap) string
	// IsRunning reports whether the given run is still active, used to
	// prevent a schedule from overlapping with its previous run.
	IsRunning(runID string) bool
}

// New creates a scheduler over the database.
func New(db *store.DB, runs RunStarter) *Scheduler {
	return &Scheduler{
		db:               db,
		Runs:             runs,
		stop:             make(chan struct{}),
		lastScheduledRun: map[string]string{},
	}
}

// Start skips missed runs and launches the tick loop (no-op when
// already running).
func (s *Scheduler) Start() {
	if s.started {
		return
	}
	s.SkipMissed(time.Now())
	s.started = true
	go func() {
		// The first tick happens one interval after start, like the
		// Python wait-then-tick loop.
		for {
			select {
			case <-s.stop:
				return
			case <-time.After(5 * time.Second):
				s.RunTick(time.Now())
			}
		}
	}()
	slog.Info("Scheduler started")
}

// Stop signals the loop to exit after the current tick.
func (s *Scheduler) Stop() {
	select {
	case <-s.stop:
	default:
		close(s.stop)
	}
}

// rememberLastScheduledRun records the run id a schedule last fired.
func (s *Scheduler) rememberLastScheduledRun(schedID, runID string) {
	s.lastScheduledRunMu.Lock()
	defer s.lastScheduledRunMu.Unlock()
	if s.lastScheduledRun == nil {
		s.lastScheduledRun = map[string]string{}
	}
	s.lastScheduledRun[schedID] = runID
}

// FireSchedule starts a run for a schedule. It returns the run id, or
// "" when skipped (target missing or in the trash); the next due
// occurrence is unaffected, exactly like the Python version.
func (s *Scheduler) FireSchedule(schedule *ordjson.OMap) string {
	targetType := orDefaultStr(ordjson.GetStr(schedule, "target_type"), "profile")
	targetID := ordjson.GetStr(schedule, "target_id")
	column := store.ColProfiles
	if targetType == "workflow" {
		column = store.ColWorkflows
	}

	items, err := s.db.Load(column)
	if err != nil {
		slog.Warn("Schedule cannot load targets - skipping",
			"schedule", ordjson.GetStr(schedule, "id"), "err", err)
		return ""
	}

	var target *ordjson.OMap
	for _, item := range items {
		if ordjson.GetStr(item, "id") == targetID {
			target = item
			break
		}
	}
	if target == nil || ordjson.GetStr(target, "group") == "__trash__" {
		slog.Warn("Schedule target is missing or trashed - skipping",
			"schedule", ordjson.GetStr(schedule, "id"), "target_type", targetType, "target_id", targetID)
		return ""
	}

	if targetType == "workflow" {
		runID := s.Runs.StartWorkflowRun(target, "scheduled", schedule)
		if runID != "" {
			s.rememberLastScheduledRun(ordjson.GetStr(schedule, "id"), runID)
		}
		return runID
	}

	runID, errStr := s.Runs.StartProfileRun(target, nil, nil, "scheduled", schedule)
	if errStr != "" || runID == "" {
		slog.Warn("Schedule could not start run - skipping",
			"schedule", ordjson.GetStr(schedule, "id"), "err", errStr)
		return ""
	}
	s.rememberLastScheduledRun(ordjson.GetStr(schedule, "id"), runID)
	return runID
}

// scheduleBusy reports whether the previous run started by this
// schedule is still active.
func (s *Scheduler) scheduleBusy(sched *ordjson.OMap) bool {
	schedID := ordjson.GetStr(sched, "id")
	s.lastScheduledRunMu.Lock()
	lastRunID, ok := s.lastScheduledRun[schedID]
	s.lastScheduledRunMu.Unlock()
	if !ok || s.Runs == nil {
		return false
	}
	if s.Runs.IsRunning(lastRunID) {
		return true
	}
	s.lastScheduledRunMu.Lock()
	delete(s.lastScheduledRun, schedID)
	s.lastScheduledRunMu.Unlock()
	return false
}

// RunTick performs one scheduler pass and returns the fired
// (schedule_id, run_id) pairs. Loads the schedules collection fresh so
// API edits take effect within one tick, recomputes missing next_run_at
// values, and fires every enabled schedule whose next_run_at passed.
func (s *Scheduler) RunTick(now time.Time) []firedRun {
	var fired []firedRun
	nowTS := float64(now.UnixNano()) / 1e9
	s.db.WithCollection(store.ColSchedules, func() {
		schedules, err := s.db.Load(store.ColSchedules)
		if err != nil {
			slog.Error("Scheduler tick failed", "err", err)
			return
		}

		changed := false
		for _, sched := range schedules {
			func() {
				defer func() {
					if r := recover(); r != nil {
						slog.Error("Scheduler tick failed for schedule", "id", ordjson.GetStr(sched, "id"), "panic", r)
					}
				}()
				if ordjson.GetStr(sched, "group") == "__trash__" {
					if sched.Get("next_run_at") != nil {
						sched.Set("next_run_at", nil)
						changed = true
					}
					return
				}
				if !ordjson.GetBool(sched, "enabled") {
					return
				}
				c, err := ParseCron(ordjson.GetStr(sched, "cron"))
				if err != nil {
					slog.Error("Scheduler tick failed for schedule", "id", ordjson.GetStr(sched, "id"), "err", err)
					return
				}
				nextRun, hasNext := ordjson.GetFloat(sched, "next_run_at")
				if !hasNext {
					if nxt, ok := c.NextAfter(now); ok {
						sched.Set("next_run_at", ordjson.Number(float64(nxt.UnixNano())/1e9))
						changed = true
					}
					return
				}
				if nextRun > nowTS {
					return
				}
				if s.scheduleBusy(sched) {
					return
				}
				runID := s.FireSchedule(sched)
				if runID != "" {
					sched.Set("last_run_at", ordjson.Number(nowTS))
					sched.Set("last_run_id", runID)
					sched.Set("last_status", nil)
					fired = append(fired, firedRun{ScheduleID: ordjson.GetStr(sched, "id"), RunID: runID})
				}
				if nxt, ok := c.NextAfter(now); ok {
					sched.Set("next_run_at", ordjson.Number(float64(nxt.UnixNano())/1e9))
				} else {
					sched.Set("next_run_at", nil)
				}
				changed = true
			}()
		}
		if changed {
			if err := s.db.Save(store.ColSchedules, schedules); err != nil {
				slog.Error("Scheduler tick failed to save schedules", "err", err)
			}
		}
	})
	return fired
}

// SkipMissed recomputes stale next_run_at values without firing, so a
// due time that passed while the server was down is skipped and the
// next occurrence is scheduled instead. Called on server start.
func (s *Scheduler) SkipMissed(now time.Time) {
	nowTS := float64(now.UnixNano()) / 1e9
	s.db.WithCollection(store.ColSchedules, func() {
		schedules, err := s.db.Load(store.ColSchedules)
		if err != nil {
			return
		}

		changed := false
		for _, sched := range schedules {
			if ordjson.GetStr(sched, "group") == "__trash__" {
				if sched.Get("next_run_at") != nil {
					sched.Set("next_run_at", nil)
					changed = true
				}
				continue
			}
			if !ordjson.GetBool(sched, "enabled") {
				continue
			}
			nextRun, hasNext := ordjson.GetFloat(sched, "next_run_at")
			if hasNext && nextRun > nowTS {
				continue
			}
			c, err := ParseCron(ordjson.GetStr(sched, "cron"))
			if err != nil {
				continue
			}
			if nxt, ok := c.NextAfter(now); ok {
				sched.Set("next_run_at", ordjson.Number(float64(nxt.UnixNano())/1e9))
				changed = true
			}
		}
		if changed {
			if err := s.db.Save(store.ColSchedules, schedules); err != nil {
				slog.Warn("Cannot save schedules", "err", err)
			}
		}
	})
}

type firedRun struct {
	ScheduleID string
	RunID      string
}

func orDefaultStr(s, fallback string) string {
	if s == "" {
		return fallback
	}
	return s
}
