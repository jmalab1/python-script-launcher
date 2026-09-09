package api

import (
	"fmt"
	"time"

	"launchcontrol/internal/ordjson"
	"launchcontrol/internal/store"
)

// stepProfileEntries yields every step entry of a workflow, flattening
// parallel groups, mirroring _step_profile_entries.
func stepProfileEntries(workflow *ordjson.OMap) []*ordjson.OMap {
	var out []*ordjson.OMap
	for _, raw := range ordjson.GetArr(workflow, "steps") {
		step, ok := raw.(*ordjson.OMap)
		if !ok {
			continue
		}
		if ordjson.GetStr(step, "type") == "parallel" {
			for _, rawEntry := range ordjson.GetArr(step, "profiles") {
				if entry, ok := rawEntry.(*ordjson.OMap); ok {
					out = append(out, entry)
				}
			}
		} else {
			out = append(out, step)
		}
	}
	return out
}

// embedProfileSnapshots stores a copy of each step's profile alongside
// it, so a later profile edit does not rewrite the workflow's recorded
// steps (Python's _embed_profile_snapshots).
func (a *API) embedProfileSnapshots(workflow *ordjson.OMap) {
	profiles, err := a.DB.Load(store.ColProfiles)
	if err != nil {
		return
	}

	byID := map[string]*ordjson.OMap{}
	for _, p := range profiles {
		byID[ordjson.GetStr(p, "id")] = p
	}

	for _, entry := range stepProfileEntries(workflow) {
		if entry.Get("profile") != nil {
			continue
		}
		if profile := byID[ordjson.GetStr(entry, "profile_id")]; profile != nil {
			entry.Set("profile", profile.Clone())
		}
	}
}

// WorkflowCreate creates a workflow, or replaces an existing one in
// place, embedding fresh profile snapshots first.
func (a *API) WorkflowCreate(data *ordjson.OMap) *ordjson.OMap {
	var result *ordjson.OMap
	a.DB.WithCollection(store.ColWorkflows, func() {
		workflows, err := a.DB.Load(store.ColWorkflows)
		if err != nil {
			workflows = nil
		}

		workflow := data
		if ordjson.GetStr(workflow, "id") == "" {
			workflow.Set("id", fmt.Sprintf("workflow_%d", time.Now().UnixMilli()))
		}

		existingIdx := -1
		for i, wf := range workflows {
			if ordjson.GetStr(wf, "id") == ordjson.GetStr(workflow, "id") {
				existingIdx = i
				break
			}
		}

		a.embedProfileSnapshots(workflow)

		var before *ordjson.OMap
		if existingIdx >= 0 {
			before = workflows[existingIdx].Clone()
			workflows[existingIdx] = workflow
		} else {
			workflows = append(workflows, workflow)
		}
		a.saveCollection(store.ColWorkflows, workflows)

		action := "updated"
		details := (*ordjson.OMap)(nil)
		if before == nil {
			action = "created"
		} else {
			details = ordjson.New().Set("changed", ordjsonArr(store.ChangedFields(before, workflow)))
		}
		a.DB.RecordAudit(action, "workflow", ordjson.GetStr(workflow, "id"),
			ordjson.GetStr(workflow, "name"), before, workflow.Clone(), details)
		result = workflow
	})
	return result
}

// WorkflowDelete moves a workflow to the trash.
func (a *API) WorkflowDelete(workflowID string) *ordjson.OMap {
	ok := ordjson.New().Set("ok", true)
	a.DB.WithCollection(store.ColWorkflows, func() {
		workflows, err := a.DB.Load(store.ColWorkflows)
		if err != nil {
			return
		}
		for _, wf := range workflows {
			if ordjson.GetStr(wf, "id") != workflowID {
				continue
			}
			before := wf.Clone()
			wf.Set("group", "__trash__")
			a.saveCollection(store.ColWorkflows, workflows)
			a.DB.RecordAudit("deleted", "workflow", workflowID,
				ordjson.GetStr(wf, "name"), before, wf.Clone(), nil)
			return
		}
	})
	return ok
}

// WorkflowRestore pulls a workflow out of the trash.
func (a *API) WorkflowRestore(workflowID string) (*ordjson.OMap, bool) {
	var restored *ordjson.OMap
	found := false
	a.DB.WithCollection(store.ColWorkflows, func() {
		workflows, err := a.DB.Load(store.ColWorkflows)
		if err != nil {
			return
		}
		for _, wf := range workflows {
			if ordjson.GetStr(wf, "id") != workflowID || ordjson.GetStr(wf, "group") != "__trash__" {
				continue
			}
			before := wf.Clone()
			wf.Set("group", "")
			a.saveCollection(store.ColWorkflows, workflows)
			a.DB.RecordAudit("restored", "workflow", workflowID,
				ordjson.GetStr(wf, "name"), before, wf.Clone(), nil)
			restored = wf
			found = true
			return
		}
	})
	return restored, found
}

// WorkflowPermanentDelete removes a workflow for good, deleting its
// schedules with it.
func (a *API) WorkflowPermanentDelete(workflowID string) *ordjson.OMap {
	ok := ordjson.New().Set("ok", true)
	a.DB.WithCollection(store.ColWorkflows, func() {
		workflows, err := a.DB.Load(store.ColWorkflows)
		if err != nil {
			return
		}

		var target *ordjson.OMap
		remaining := make([]*ordjson.OMap, 0, len(workflows))
		for _, wf := range workflows {
			if ordjson.GetStr(wf, "id") == workflowID {
				target = wf
			} else {
				remaining = append(remaining, wf)
			}
		}
		a.saveCollection(store.ColWorkflows, remaining)

		if target != nil {
			var removedSchedules []any
			a.DB.WithCollection(store.ColSchedules, func() {
				schedules, err := a.DB.Load(store.ColSchedules)
				if err != nil {
					return
				}
				for _, s := range schedules {
					if ordjson.GetStr(s, "target_id") == workflowID {
						removedSchedules = append(removedSchedules, s.Get("id"))
					}
				}
				if len(removedSchedules) > 0 {
					kept := schedules[:0]
					for _, s := range schedules {
						if ordjson.GetStr(s, "target_id") != workflowID {
							kept = append(kept, s)
						}
					}
					a.saveCollection(store.ColSchedules, kept)
				}
			})

			details := (*ordjson.OMap)(nil)
			if len(removedSchedules) > 0 {
				details = ordjson.New().Set("schedules_removed", removedSchedules)
			}
			a.DB.RecordAudit("permanently_deleted", "workflow", workflowID,
				ordjson.GetStr(target, "name"), target.Clone(), nil, details)
		}
	})
	return ok
}

// WorkflowDuplicate copies a workflow right after its position,
// refreshing the embedded profile snapshots.
func (a *API) WorkflowDuplicate(workflowID string) (*ordjson.OMap, bool) {
	var dup *ordjson.OMap
	found := false
	a.DB.WithCollection(store.ColWorkflows, func() {
		workflows, err := a.DB.Load(store.ColWorkflows)
		if err != nil {
			return
		}

		index := -1
		for i, wf := range workflows {
			if ordjson.GetStr(wf, "id") == workflowID {
				index = i
				break
			}
		}
		if index < 0 {
			return
		}

		source := workflows[index]
		existingNames := map[string]bool{}
		for _, wf := range workflows {
			existingNames[ordjson.GetStr(wf, "name")] = true
		}

		duplicate := source.Clone()
		duplicate.Set("id", "workflow_"+randHex12())
		a.embedProfileSnapshots(duplicate)
		base := orDefaultStr(ordjson.GetStr(source, "name"), "Workflow")
		name := base + " (copy)"
		for n := 2; existingNames[name]; n++ {
			name = fmt.Sprintf("%s (copy %d)", base, n)
		}
		duplicate.Set("name", name)

		workflows = append(workflows, nil)
		copy(workflows[index+2:], workflows[index+1:])
		workflows[index+1] = duplicate
		a.saveCollection(store.ColWorkflows, workflows)

		a.DB.RecordAudit("created", "workflow", ordjson.GetStr(duplicate, "id"),
			ordjson.GetStr(duplicate, "name"), nil, duplicate.Clone(),
			ordjson.New().Set("duplicate_of", ordjson.GetStr(source, "name")))
		dup = duplicate
		found = true
	})
	return dup, found
}

// WorkflowReorder applies a new id order and audits the change.
func (a *API) WorkflowReorder(data *ordjson.OMap) *ordjson.OMap {
	ok := ordjson.New().Set("ok", true)
	order := ordjson.GetArr(data, "order")
	a.DB.WithCollection(store.ColWorkflows, func() {
		workflows, err := a.DB.Load(store.ColWorkflows)
		if err != nil {
			return
		}

		byID := map[string]*ordjson.OMap{}
		for _, wf := range workflows {
			byID[ordjson.GetStr(wf, "id")] = wf
		}

		ordered := make([]*ordjson.OMap, 0, len(order))
		orderedSet := map[string]bool{}
		for _, raw := range order {
			id, _ := raw.(string)
			if wf, ok2 := byID[id]; ok2 && !orderedSet[id] {
				ordered = append(ordered, wf)
				orderedSet[id] = true
			}
		}

		for _, wf := range workflows {
			if !orderedSet[ordjson.GetStr(wf, "id")] {
				ordered = append(ordered, wf)
			}
		}

		previous := make([]string, len(workflows))
		current := make([]string, len(ordered))
		for i, wf := range workflows {
			previous[i] = ordjson.GetStr(wf, "id")
		}
		for i, wf := range ordered {
			current[i] = ordjson.GetStr(wf, "id")
		}
		a.saveCollection(store.ColWorkflows, ordered)

		if joinStrings(current, ",") != joinStrings(previous, ",") {
			a.DB.RecordAudit("reordered", "workflows", "", "Workflow order", nil, nil,
				ordjson.New().Set("order", ordjsonArr(current)))
		}
	})
	return ok
}
