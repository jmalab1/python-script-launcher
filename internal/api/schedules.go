package api

import (
	"fmt"
	"strings"
	"time"

	"launchcontrol/internal/ordjson"
	"launchcontrol/internal/scheduler"
	"launchcontrol/internal/store"
)

// previewCount is how many upcoming fire times the editor shows.
const previewCount = 3

// findTarget looks up a schedule's target profile or workflow.
func (a *API) findTarget(targetType, targetID string) *ordjson.OMap {
	column := store.ColProfiles
	if targetType == "workflow" {
		column = store.ColWorkflows
	}

	items, err := a.DB.Load(column)
	if err != nil {
		return nil
	}
	for _, item := range items {
		if ordjson.GetStr(item, "id") == targetID {
			return item
		}
	}
	return nil
}

// auditName is the display name used in audit entries: the schedule's
// own label when set, otherwise its target's name.
func (a *API) auditName(schedule *ordjson.OMap) string {
	if name := ordjson.GetStr(schedule, "name"); name != "" {
		return name
	}
	target := a.findTarget(orDefaultStr(ordjson.GetStr(schedule, "target_type"), "profile"), ordjson.GetStr(schedule, "target_id"))
	if target != nil {
		return ordjson.GetStr(target, "name")
	}
	return ""
}

// listSchedules enriches every schedule with the fields the UI shows:
// target_name, target_trashed and a human description of the cron.
func (a *API) listSchedules() []*ordjson.OMap {
	schedules, err := a.DB.Load(store.ColSchedules)
	if err != nil {
		return nil
	}
	out := make([]*ordjson.OMap, 0, len(schedules))
	for _, s := range schedules {
		out = append(out, a.enrichSchedule(s))
	}
	return out
}

func (a *API) enrichSchedule(schedule *ordjson.OMap) *ordjson.OMap {
	out := schedule.Clone()
	target := a.findTarget(orDefaultStr(ordjson.GetStr(schedule, "target_type"), "profile"), ordjson.GetStr(schedule, "target_id"))
	if target != nil {
		out.Set("target_name", ordjson.GetStr(target, "name"))
		out.Set("target_trashed", ordjson.GetStr(target, "group") == "__trash__")
	} else {
		out.Set("target_name", nil)
		out.Set("target_trashed", false)
	}

	cron := ordjson.GetStr(schedule, "cron")
	if cron == "" {
		out.Set("description", "")
	} else {
		out.Set("description", scheduler.DescribeCron(cron))
	}
	return out
}

// validateSchedule checks a create/update request; returns the error
// message or "".
func (a *API) validateSchedule(data *ordjson.OMap) string {
	cron := ordjson.GetStr(data, "cron")
	if _, err := scheduler.ParseCron(cron); err != nil {
		return "Invalid cron expression: " + err.Error()
	}
	targetType := orDefaultStr(ordjson.GetStr(data, "target_type"), "profile")
	if targetType != "profile" && targetType != "workflow" {
		return "target_type must be 'profile' or 'workflow'"
	}
	target := a.findTarget(targetType, ordjson.GetStr(data, "target_id"))
	if target == nil {
		return "Target not found"
	}
	if ordjson.GetStr(target, "group") == "__trash__" {
		return "Target is in the trash"
	}
	return ""
}

// nextRunAt computes the next fire time for a cron expression as an
// epoch float, or nil when it can never fire.
func nextRunAt(cronExpr string) any {
	c, err := scheduler.ParseCron(cronExpr)
	if err != nil {
		return nil
	}
	nxt, ok := c.NextAfter(time.Now())
	if !ok {
		return nil
	}
	return ordjson.Number(epochSeconds(nxt))
}

func epochSeconds(t time.Time) float64 {
	return float64(t.UnixNano()) / 1e9
}

// ScheduleCreate creates or updates a schedule.
func (a *API) ScheduleCreate(data *ordjson.OMap) (*ordjson.OMap, *ordjson.OMap) {
	if msg := a.validateSchedule(data); msg != "" {
		return nil, ordjson.New().Set("error", msg)
	}
	var result *ordjson.OMap
	var apiErr *ordjson.OMap
	a.DB.WithCollection(store.ColSchedules, func() {
		schedules, err := a.DB.Load(store.ColSchedules)
		if err != nil {
			apiErr = ordjson.New().Set("error", "Cannot load schedules")
			return
		}

		var existing *ordjson.OMap
		for _, s := range schedules {
			if ordjson.GetStr(s, "id") == ordjson.GetStr(data, "id") {
				existing = s
				break
			}
		}

		var schedule *ordjson.OMap
		if existing != nil {
			schedule = existing.Clone()
		} else {
			schedule = ordjson.New().
				Set("id", "sched_"+randHex12()).
				Set("created_at", ordjson.Number(nowSeconds())).
				Set("last_run_at", nil).
				Set("last_run_id", nil).
				Set("last_status", nil).
				Set("next_run_at", nil)
		}

		schedule.Set("name", strings.TrimSpace(ordjson.GetStr(data, "name")))
		targetType := orDefaultStr(ordjson.GetStr(data, "target_type"), "profile")
		schedule.Set("target_type", targetType)
		schedule.Set("target_id", data.Get("target_id"))
		schedule.Set("cron", strings.TrimSpace(ordjson.GetStr(data, "cron")))
		enabled := true
		if v, ok := data.GetOK("enabled"); ok {
			enabled = ordjson.GetBool(data, "enabled") || v == true
		}
		schedule.Set("enabled", enabled)

		cronChanged := existing == nil || ordjson.GetStr(existing, "cron") != ordjson.GetStr(schedule, "cron")
		if enabled {
			if cronChanged || existing == nil || existing.Get("next_run_at") == nil {
				schedule.Set("next_run_at", nextRunAt(ordjson.GetStr(schedule, "cron")))
			} else {
				schedule.Set("next_run_at", existing.Get("next_run_at"))
			}
		} else {
			schedule.Set("next_run_at", nil)
		}

		kept := make([]*ordjson.OMap, 0, len(schedules)+1)
		for _, s := range schedules {
			if ordjson.GetStr(s, "id") != ordjson.GetStr(schedule, "id") {
				kept = append(kept, s)
			}
		}
		kept = append(kept, schedule)
		a.saveCollection(store.ColSchedules, kept)

		action := "updated"
		details := (*ordjson.OMap)(nil)
		if existing == nil {
			action = "created"
		} else {
			details = ordjson.New().Set("changed", ordjsonArr(store.ChangedFields(existing, schedule)))
		}
		a.DB.RecordAudit(action, "schedule", ordjson.GetStr(schedule, "id"),
			a.auditName(schedule), existing, schedule.Clone(), details)
		result = schedule
	})
	return result, apiErr
}

// ScheduleToggle enables/disables a schedule.
func (a *API) ScheduleToggle(scheduleID string) (*ordjson.OMap, *ordjson.OMap) {
	var result *ordjson.OMap
	var apiErr *ordjson.OMap
	a.DB.WithCollection(store.ColSchedules, func() {
		schedules, err := a.DB.Load(store.ColSchedules)
		if err != nil {
			apiErr = ordjson.New().Set("error", "Schedule not found")
			return
		}

		var target *ordjson.OMap
		for _, s := range schedules {
			if ordjson.GetStr(s, "id") == scheduleID {
				target = s
				break
			}
		}
		if target == nil {
			apiErr = ordjson.New().Set("error", "Schedule not found")
			return
		}

		before := target.Clone()
		target.Set("enabled", !ordjson.GetBool(target, "enabled"))
		if ordjson.GetBool(target, "enabled") {
			target.Set("next_run_at", nextRunAt(ordjson.GetStr(target, "cron")))
		} else {
			target.Set("next_run_at", nil)
		}
		a.saveCollection(store.ColSchedules, schedules)

		a.DB.RecordAudit("updated", "schedule", scheduleID, a.auditName(target),
			before, target.Clone(),
			ordjson.New().Set("changed", ordjsonArr(store.ChangedFields(before, target))))
		result = target
	})
	return result, apiErr
}

// ScheduleRunNow fires a schedule immediately without touching its
// cadence.
func (a *API) ScheduleRunNow(scheduleID string) (*ordjson.OMap, *ordjson.OMap) {
	var result *ordjson.OMap
	var apiErr *ordjson.OMap
	a.DB.WithCollection(store.ColSchedules, func() {
		schedules, err := a.DB.Load(store.ColSchedules)
		if err != nil {
			apiErr = ordjson.New().Set("error", "Schedule not found")
			return
		}

		var sched *ordjson.OMap
		for _, s := range schedules {
			if ordjson.GetStr(s, "id") == scheduleID {
				sched = s
				break
			}
		}
		if sched == nil {
			apiErr = ordjson.New().Set("error", "Schedule not found")
			return
		}

		runID := a.Sched.FireSchedule(sched)
		if runID == "" {
			apiErr = ordjson.New().Set("error", "Could not start run (target missing or script missing)")
			return
		}

		sched.Set("last_run_at", ordjson.Number(nowSeconds()))
		sched.Set("last_run_id", runID)
		a.saveCollection(store.ColSchedules, schedules)

		a.DB.RecordAudit("run_now", "schedule", scheduleID, a.auditName(sched),
			nil, sched.Clone(), ordjson.New().Set("run_id", runID))
		result = ordjson.New().Set("run_id", runID)
	})
	return result, apiErr
}

// ScheduleDuplicate copies a schedule with fresh run bookkeeping.
func (a *API) ScheduleDuplicate(scheduleID string) (*ordjson.OMap, *ordjson.OMap) {
	var result *ordjson.OMap
	var apiErr *ordjson.OMap
	a.DB.WithCollection(store.ColSchedules, func() {
		schedules, err := a.DB.Load(store.ColSchedules)
		if err != nil {
			apiErr = ordjson.New().Set("error", "Schedule not found")
			return
		}

		var source *ordjson.OMap
		for _, s := range schedules {
			if ordjson.GetStr(s, "id") == scheduleID {
				source = s
				break
			}
		}
		if source == nil {
			apiErr = ordjson.New().Set("error", "Schedule not found")
			return
		}

		existingNames := map[string]bool{}
		for _, s := range schedules {
			existingNames[ordjson.GetStr(s, "name")] = true
		}

		duplicate := source.Clone()
		duplicate.Set("id", "sched_"+randHex12())
		duplicate.Set("created_at", ordjson.Number(nowSeconds()))
		duplicate.Set("last_run_at", nil)
		duplicate.Set("last_run_id", nil)
		duplicate.Set("last_status", nil)

		base := orDefaultStr(ordjson.GetStr(source, "name"), "Schedule")
		name := base + " (copy)"
		for n := 2; existingNames[name]; n++ {
			name = fmt.Sprintf("%s (copy %d)", base, n)
		}
		duplicate.Set("name", name)

		if ordjson.GetBool(duplicate, "enabled") {
			duplicate.Set("next_run_at", nextRunAt(ordjson.GetStr(duplicate, "cron")))
		} else {
			duplicate.Set("next_run_at", nil)
		}

		schedules = append(schedules, duplicate)
		a.saveCollection(store.ColSchedules, schedules)

		a.DB.RecordAudit("created", "schedule", ordjson.GetStr(duplicate, "id"),
			ordjson.GetStr(duplicate, "name"), nil, duplicate.Clone(),
			ordjson.New().Set("duplicate_of", a.auditName(source)))
		result = duplicate
	})
	return result, apiErr
}

// ScheduleDelete moves a schedule to the trash (stops it firing).
func (a *API) ScheduleDelete(scheduleID string) (*ordjson.OMap, *ordjson.OMap) {
	ok := ordjson.New().Set("ok", true)
	a.DB.WithCollection(store.ColSchedules, func() {
		schedules, err := a.DB.Load(store.ColSchedules)
		if err != nil {
			return
		}
		for _, s := range schedules {
			if ordjson.GetStr(s, "id") != scheduleID {
				continue
			}
			before := s.Clone()
			s.Set("group", "__trash__")
			s.Set("next_run_at", nil)
			a.saveCollection(store.ColSchedules, schedules)
			a.DB.RecordAudit("deleted", "schedule", scheduleID, a.auditName(s),
				before, s.Clone(), nil)
			return
		}
	})
	return ok, nil
}

// ScheduleRestore pulls a trashed schedule back into service.
func (a *API) ScheduleRestore(scheduleID string) (*ordjson.OMap, *ordjson.OMap) {
	var result *ordjson.OMap
	var apiErr *ordjson.OMap
	a.DB.WithCollection(store.ColSchedules, func() {
		schedules, err := a.DB.Load(store.ColSchedules)
		if err != nil {
			apiErr = ordjson.New().Set("error", "Schedule not found")
			return
		}

		var target *ordjson.OMap
		for _, s := range schedules {
			if ordjson.GetStr(s, "id") != scheduleID {
				continue
			}
			target = s
			break
		}
		if target == nil || ordjson.GetStr(target, "group") != "__trash__" {
			apiErr = ordjson.New().Set("error", "Schedule not found")
			return
		}

		before := target.Clone()
		target.Set("group", "")
		if ordjson.GetBool(target, "enabled") {
			target.Set("next_run_at", nextRunAt(ordjson.GetStr(target, "cron")))
		}
		a.saveCollection(store.ColSchedules, schedules)

		a.DB.RecordAudit("restored", "schedule", scheduleID, a.auditName(target),
			before, target.Clone(), nil)
		result = target
	})
	return result, apiErr
}

// SchedulePermanentDelete removes a schedule for good.
func (a *API) SchedulePermanentDelete(scheduleID string) (*ordjson.OMap, *ordjson.OMap) {
	a.DB.WithCollection(store.ColSchedules, func() {
		schedules, err := a.DB.Load(store.ColSchedules)
		if err != nil {
			return
		}

		var target *ordjson.OMap
		remaining := make([]*ordjson.OMap, 0, len(schedules))
		for _, s := range schedules {
			if ordjson.GetStr(s, "id") == scheduleID {
				target = s
			} else {
				remaining = append(remaining, s)
			}
		}
		a.saveCollection(store.ColSchedules, remaining)

		if target != nil {
			a.DB.RecordAudit("permanently_deleted", "schedule", scheduleID,
				a.auditName(target), target.Clone(), nil, nil)
		}
	})
	return ordjson.New().Set("ok", true), nil
}

// SchedulePreview returns the next few fire times for the schedule
// editor's live preview.
func (a *API) SchedulePreview(cronExpr string) (*ordjson.OMap, int) {
	c, err := scheduler.ParseCron(cronExpr)
	if err != nil {
		return ordjson.New().Set("error", "Invalid cron expression: "+err.Error()), 400
	}

	now := time.Now()
	upcoming := []any{}
	t := now
	for i := 0; i < previewCount; i++ {
		nxt, ok := c.NextAfter(t)
		if !ok {
			break
		}
		upcoming = append(upcoming, ordjson.New().
			Set("ts", ordjson.Number(epochSeconds(nxt))).
			Set("local", nxt.Format("2006-01-02 15:04")))
		t = nxt
	}
	return ordjson.New().
		Set("cron", cronExpr).
		Set("description", scheduler.DescribeCron(cronExpr)).
		Set("next", upcoming), 200
}

func nowSeconds() float64 {
	return epochSeconds(time.Now())
}
