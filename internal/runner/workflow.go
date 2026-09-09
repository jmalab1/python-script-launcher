package runner

import (
	"os"
	"strconv"
	"sync"
	"time"

	"launchcontrol/internal/ordjson"
	"launchcontrol/internal/store"
)

// StartProfileRun launches a profile run in a background goroutine.
// Shared by the web UI and the scheduler so both produce identical
// registry entries and history records. Returns the run id, or an
// error message when the script is missing.
func (m *Manager) StartProfileRun(profile *ordjson.OMap, argValues *ordjson.OMap, extraArgs []string, trigger string, schedule *ordjson.OMap) (string, string) {
	scriptPath := ordjson.GetStr(profile, "script_path")
	if !fileExists(scriptPath) {
		return "", "Script not found: " + scriptPath
	}

	builtArgs := BuildCustomArgs(ordjson.GetArr(profile, "custom_args"), argValues)
	fullArgs := append(append(toStringSlice(ordjson.GetArr(profile, "args")), builtArgs...), extraArgs...)
	command := m.BuildCommand(scriptPath, fullArgs)

	startedAt := nowSeconds()
	m.Prune()

	runID := ""
	m.mu.Lock()
	m.counter++
	runID = "prof_" + milliStamp(startedAt) + "_" + itoa(m.counter)
	r := &Run{
		ID:      runID,
		Status:  "running",
		Output:  []string{},
		Trigger: trigger,
		Command: command,
	}
	if schedule != nil {
		r.ScheduleID = ordjson.GetStr(schedule, "id")
		r.ScheduleName = ordjson.GetStr(schedule, "name")
	}
	m.runs[runID] = r
	m.mu.Unlock()

	profileName := orDefault(ordjson.GetStr(profile, "name"), "Unnamed")
	opts := store.HistoryEntryOptions{
		Command: command,
		Trigger: trigger,
	}
	if schedule != nil {
		opts.ScheduleID = ordjson.GetStr(schedule, "id")
		opts.ScheduleName = ordjson.GetStr(schedule, "name")
	}
	// Record the run up front (status: running), the same way workflow
	// runs are recorded, so it is visible in history while it runs and
	// is not lost entirely if the server dies before the script ends.
	m.db.SaveHistory(runID, profileName, "profile", "running", nil, []string{}, startedAt, opts)

	go func() {
		timeout := ParseTimeout(profile.Get("timeout"))
		m.runScript(m.get(runID), scriptPath, fullArgs, nil, timeout, nil)
		m.mu.Lock()
		r := m.runs[runID]
		var status string
		switch {
		case r == nil:
			m.mu.Unlock()
			return
		case r.Cancelled:
			// A cancelled run was stopped on purpose, so it is not failed
			// even though its killed script exits non-zero.
			status = "cancelled"
		case r.ReturnCode != nil && *r.ReturnCode != 0:
			status = "failed"
		default:
			status = "completed"
		}
		r.Status = status
		r.FinishedAt = nowSeconds()
		outputCopy := append([]string(nil), r.Output...)
		returnCode := 0
		if r.ReturnCode != nil {
			returnCode = *r.ReturnCode
		}
		timedOut := r.TimedOut
		m.mu.Unlock()

		updated := m.db.UpdateHistory(runID, store.HistoryUpdate{
			Status:     &status,
			ReturnCode: returnCodePtr(returnCode),
			Output:     outputCopy,
			TimedOut:   timedOut,
		})
		if !updated {
			// The up-front entry was deleted while the run was in
			// progress (e.g. the user cleared history), so write a fresh
			// one rather than losing the result.
			m.db.SaveHistory(runID, profileName, "profile", status, ordjson.Number(float64(returnCode)), outputCopy, startedAt, store.HistoryEntryOptions{
				Command:  command,
				Trigger:  trigger,
				TimedOut: timedOut,
			})
		}
	}()
	return runID, ""
}

// StartWorkflowRun launches a workflow run in a background goroutine.
// The workflow is assumed to exist (callers resolve it from storage).
func (m *Manager) StartWorkflowRun(workflow *ordjson.OMap, trigger string, schedule *ordjson.OMap) string {
	startedAt := nowSeconds()
	m.Prune()

	runID := ""
	m.mu.Lock()
	m.counter++
	runID = "wf_" + milliStamp(startedAt) + "_" + itoa(m.counter)
	r := &Run{
		ID:      runID,
		Status:  "starting",
		Output:  []string{},
		Trigger: trigger,
	}
	if schedule != nil {
		r.ScheduleID = ordjson.GetStr(schedule, "id")
		r.ScheduleName = ordjson.GetStr(schedule, "name")
	}
	m.runs[runID] = r
	m.mu.Unlock()

	go m.ExecuteWorkflow(workflow, runID, startedAt, trigger, schedule)
	return runID
}

// ExecuteWorkflow runs a workflow: sequential steps one after another,
// parallel groups concurrently, with the Python engine's error-handling
// and bookkeeping semantics.
func (m *Manager) ExecuteWorkflow(workflow *ordjson.OMap, runID string, startedAt float64, trigger string, schedule *ordjson.OMap) {
	profiles, err := m.db.Load(store.ColProfiles)
	if err != nil {
		profiles = nil
	}

	profileMap := map[string]*ordjson.OMap{}
	for _, p := range profiles {
		profileMap[ordjson.GetStr(p, "id")] = p
	}

	steps := ordjson.GetArr(workflow, "steps")
	continueOnError := ordjson.GetBool(workflow, "continue_on_error")
	name := orDefault(ordjson.GetStr(workflow, "name"), "Unnamed")

	r := m.get(runID)
	if r == nil {
		return
	}
	m.mu.Lock()
	r.WorkflowLog = []string{"Starting workflow: " + name}
	r.Status = "running"
	workflowLog := append([]string(nil), r.WorkflowLog...)
	m.mu.Unlock()

	opts := store.HistoryEntryOptions{
		WorkflowLog: workflowLog,
		Steps:       ordjson.New(),
		Trigger:     trigger,
	}
	if schedule != nil {
		opts.ScheduleID = ordjson.GetStr(schedule, "id")
		opts.ScheduleName = ordjson.GetStr(schedule, "name")
	}
	// Record the run up front so it stays visible in history (status:
	// running) even if the run panel is closed before it finishes.
	m.db.SaveHistory(runID, name, "workflow", "running", nil, nil, startedAt, opts)

	for _, rawStep := range steps {
		if m.isCancelled(runID) {
			break
		}
		step, _ := rawStep.(*ordjson.OMap)
		stepType := "sequential"
		if step != nil {
			stepType = orDefault(ordjson.GetStr(step, "type"), "sequential")
		}

		if stepType == "parallel" {
			group := []*ordjson.OMap{}
			if step != nil {
				for _, entry := range ordjson.GetArr(step, "profiles") {
					if e, ok := entry.(*ordjson.OMap); ok {
						group = append(group, e)
					}
				}
			}
			if len(group) == 0 {
				continue
			}

			names := []string{}
			for _, p := range group {
				prof := resolveProfile(profileMap, p)
				profileName := "?"
				if prof != nil {
					profileName = orDefault(ordjson.GetStr(prof, "name"), ordjson.GetStr(p, "profile_id"))
				} else {
					profileName = orDefault(ordjson.GetStr(p, "profile_id"), "?")
				}
				names = append(names, profileName)
			}
			m.mu.Lock()
			r.WorkflowLog = append(r.WorkflowLog,
				"[PARALLEL] Running "+itoa(len(group))+" steps: "+joinStrings(names, ", "))
			m.mu.Unlock()

			var wg sync.WaitGroup
			for _, profileEntry := range group {
				profile := resolveProfile(profileMap, profileEntry)
				if profile == nil {
					m.mu.Lock()
					r.WorkflowLog = append(r.WorkflowLog, "[SKIP] Profile not found: "+ordjson.GetStr(profileEntry, "profile_id"))
					if !continueOnError {
						r.Failed = true
					}
					m.mu.Unlock()
					if !continueOnError {
						break
					}
					continue
				}
				wg.Add(1)
				go func(profile *ordjson.OMap, profileEntry *ordjson.OMap) {
					defer wg.Done()
					m.runStep(profile, toStringSlice(ordjson.GetArr(profileEntry, "args")), runID, continueOnError,
						ordjson.GetMap(profileEntry, "arg_values"))
				}(profile, profileEntry)
			}
			wg.Wait()

			m.mu.Lock()
			cancelled := r.Cancelled
			failed := r.Failed
			m.mu.Unlock()
			if cancelled {
				break
			}
			if !continueOnError && failed {
				break
			}
		} else {
			profile := resolveProfile(profileMap, step)
			if profile == nil {
				m.mu.Lock()
				r.WorkflowLog = append(r.WorkflowLog, "[SKIP] Profile not found: "+ordjson.GetStr(step, "profile_id"))
				if !continueOnError {
					r.Failed = true
				}
				m.mu.Unlock()
				if !continueOnError {
					break
				}
				continue
			}

			m.runStep(profile, toStringSlice(ordjson.GetArr(step, "args")), runID, continueOnError,
				ordjson.GetMap(step, "arg_values"))
			m.mu.Lock()
			cancelled := r.Cancelled
			failed := r.Failed
			m.mu.Unlock()
			if cancelled {
				break
			}
			if !continueOnError && failed {
				break
			}
		}
	}

	m.mu.Lock()
	// A cancelled run is stopped on purpose, so it must not be reported
	// as failed even though its last step exited non-zero.
	var status string
	switch {
	case r.Cancelled:
		status = "cancelled"
	case r.Failed:
		status = "failed"
	default:
		status = "completed"
	}
	r.Status = status
	r.FinishedAt = nowSeconds()
	r.WorkflowLog = append(r.WorkflowLog, "Workflow "+status)
	finalLog := append([]string(nil), r.WorkflowLog...)
	finalSteps := r.Steps
	timedOut := r.TimedOut
	m.mu.Unlock()

	m.db.UpdateHistory(runID, store.HistoryUpdate{
		Status:      &status,
		Output:      finalLog,
		WorkflowLog: finalLog,
		Steps:       finalSteps,
		TimedOut:    timedOut,
	})
}

// runStep executes one profile step, mirroring _run_step: it records
// the step in the steps map, streams output, and appends progress to
// the workflow log.
func (m *Manager) runStep(profile *ordjson.OMap, extraArgs []string, runID string, continueOnError bool, argOverrides *ordjson.OMap) {
	scriptPath := ordjson.GetStr(profile, "script_path")
	stepName := orDefault(ordjson.GetStr(profile, "name"), "Unnamed")

	r := m.get(runID)
	if r == nil {
		return
	}
	m.mu.Lock()
	n, displayName := r.nextStepName(stepName)
	m.mu.Unlock()

	if !fileExists(scriptPath) {
		m.mu.Lock()
		step := ordjson.New().
			Set("output", []any{}).
			Set("status", "failed").
			Set("returncode", ordjson.Number(float64(-1))).
			Set("step", n)
		if r.Steps == nil {
			r.Steps = ordjson.New()
		}
		r.Steps.Set(displayName, step)
		r.WorkflowLog = append(r.WorkflowLog,
			"[SKIP] Step "+itoa(n)+" ("+stepName+"): script not found: "+scriptPath)
		// Mirror the missing-profile behavior: with continue_on_error the
		// step is skipped and the run can still complete.
		if !continueOnError {
			r.Failed = true
		}
		m.mu.Unlock()
		return
	}

	builtArgs := BuildCustomArgs(ordjson.GetArr(profile, "custom_args"), argOverrides)
	args := append(append([]string{}, builtArgs...), extraArgs...)
	cmd := m.BuildCommand(scriptPath, args)

	m.mu.Lock()
	stepOut := []string{}
	step := ordjson.New().
		Set("output", []any{}).
		Set("status", "running").
		Set("returncode", nil).
		Set("step", n).
		Set("command", toStringsAny(cmd))
	if r.Steps == nil {
		r.Steps = ordjson.New()
	}
	r.Steps.Set(displayName, step)
	r.WorkflowLog = append(r.WorkflowLog, "[RUN] Step "+itoa(n)+": "+stepName)
	r.CurrentStep = displayName
	m.mu.Unlock()

	result := 0
	timeout := ParseTimeout(profile.Get("timeout"))
	m.runScript(r, scriptPath, args, &result, timeout, &stepOut)

	m.mu.Lock()
	// Write streamed output into the step record.
	step.Set("output", toStringsAny(stepOut))
	rc := result
	step.Set("returncode", ordjson.Number(float64(rc)))
	switch {
	case rc == 0:
		step.Set("status", "completed")
		r.WorkflowLog = append(r.WorkflowLog, "[DONE] Step "+itoa(n)+" ("+stepName+") completed successfully")
	case r.Cancelled:
		// The process was killed by a cancel request, not by its own
		// failure, so the step is recorded as cancelled.
		step.Set("status", "cancelled")
		r.WorkflowLog = append(r.WorkflowLog, "[CANCEL] Step "+itoa(n)+" ("+stepName+") was stopped")
	default:
		step.Set("status", "failed")
		r.Failed = true
		r.WorkflowLog = append(r.WorkflowLog, "[FAIL] Step "+itoa(n)+" ("+stepName+") exited with code "+itoa(rc))
		if !continueOnError {
			r.WorkflowLog = append(r.WorkflowLog, "[ABORT] Workflow stopped due to error.")
		}
	}
	m.mu.Unlock()
}

// --- poll snapshots ---

// stepToJSON renders one step the way the run panel expects.
func stepToJSON(step *ordjson.OMap) *ordjson.OMap {
	out := ordjson.New()
	for _, k := range step.Keys() {
		v := step.Get(k)
		if k == "output" {
			if arr, ok := v.([]any); ok {
				cp := make([]any, len(arr))
				copy(cp, arr)
				out.Set(k, cp)
				continue
			}
		}
		out.Set(k, v)
	}
	return out
}

// snapshot renders a run for the poll endpoints. Everything mutable is
// copied: the HTTP goroutine serializes the result outside m.mu while
// run goroutines keep appending to the real output.
func (m *Manager) snapshot(r *Run) *ordjson.OMap {
	out := ordjson.New()
	out.Set("output", toStringsAny(r.Output))
	out.Set("workflow_log", toStringsAny(r.WorkflowLog))
	out.Set("status", r.Status)
	if r.ReturnCode != nil {
		out.Set("returncode", ordjson.Number(float64(*r.ReturnCode)))
	} else {
		out.Set("returncode", nil)
	}
	steps := ordjson.New()
	if r.Steps != nil {
		for _, k := range r.Steps.Keys() {
			if s, ok := r.Steps.Get(k).(*ordjson.OMap); ok {
				steps.Set(k, stepToJSON(s))
			}
		}
	}
	out.Set("steps", steps)
	if r.CurrentStep != "" {
		out.Set("current_step", r.CurrentStep)
	} else {
		out.Set("current_step", nil)
	}
	if len(r.Command) > 0 {
		out.Set("command", toStringsAny(r.Command))
	} else {
		out.Set("command", nil)
	}
	out.Set("timed_out", r.TimedOut)
	out.Set("cancelled", r.Cancelled)
	return out
}

// Poll returns one run's poll view, or nil when the run is unknown
// (pruned already).
func (m *Manager) Poll(runID string) *ordjson.OMap {
	m.mu.Lock()
	r, ok := m.runs[runID]
	if !ok {
		m.mu.Unlock()
		return nil
	}
	snap := m.snapshot(r)
	m.mu.Unlock()
	return snap
}

// PollAll returns every run's poll view, keyed by run id.
func (m *Manager) PollAll() *ordjson.OMap {
	m.Prune()
	m.mu.Lock()
	defer m.mu.Unlock()
	all := ordjson.New()
	for _, r := range m.runs {
		all.Set(r.ID, m.snapshot(r))
	}
	return all
}

// IsRunning reports whether the given run is still active. The
// scheduler uses it to avoid overlapping a schedule's runs.
func (m *Manager) IsRunning(runID string) bool {
	m.mu.Lock()
	defer m.mu.Unlock()
	r, ok := m.runs[runID]
	return ok && r.Status == "running"
}

// --- small helpers ---

func (m *Manager) get(runID string) *Run {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.runs[runID]
}

func (m *Manager) isCancelled(runID string) bool {
	m.mu.Lock()
	defer m.mu.Unlock()
	r, ok := m.runs[runID]
	return ok && r.Cancelled
}

// resolveProfile prefers a step's embedded profile snapshot (saved with
// the workflow) over the live profile, like _resolve_profile.
func resolveProfile(profileMap map[string]*ordjson.OMap, entry *ordjson.OMap) *ordjson.OMap {
	if entry == nil {
		return nil
	}
	if snapshot := ordjson.GetMap(entry, "profile"); snapshot != nil {
		return snapshot
	}
	return profileMap[ordjson.GetStr(entry, "profile_id")]
}

func fileExists(path string) bool {
	info, err := os.Stat(path)
	return err == nil && !info.IsDir()
}

func nowSeconds() float64 {
	return float64(time.Now().UnixNano()) / 1e9
}

func milliStamp(seconds float64) string {
	return strconv.FormatInt(int64(seconds*1000), 10)
}

func itoa(n int) string {
	return strconv.Itoa(n)
}

func orDefault(s, fallback string) string {
	if s == "" {
		return fallback
	}
	return s
}

func toStringSlice(arr []any) []string {
	out := make([]string, 0, len(arr))
	for _, v := range arr {
		out = append(out, stringify(v))
	}
	return out
}

func toStringsAny(lines []string) []any {
	out := make([]any, len(lines))
	for i, l := range lines {
		out[i] = l
	}
	return out
}

func joinStrings(parts []string, sep string) string {
	out := ""
	for i, p := range parts {
		if i > 0 {
			out += sep
		}
		out += p
	}
	return out
}

func returnCodePtr(n int) *int { return &n }
