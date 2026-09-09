package api

import (
	"fmt"
	"net/http"

	"launchcontrol/internal/ordjson"
	"launchcontrol/internal/store"
)

// RunProfile starts a profile run; returns the body and HTTP status.
func (a *API) RunProfile(data *ordjson.OMap) (*ordjson.OMap, int) {
	profileID := ordjson.GetStr(data, "profile_id")
	profiles, err := a.DB.Load(store.ColProfiles)
	if err != nil {
		profiles = nil
	}

	var profile *ordjson.OMap
	for _, p := range profiles {
		if ordjson.GetStr(p, "id") == profileID {
			profile = p
			break
		}
	}
	if profile == nil {
		return ordjson.New().Set("error", "Profile not found"), http.StatusNotFound
	}

	var argValues *ordjson.OMap
	if av := ordjson.GetMap(data, "arg_values"); av != nil {
		argValues = av
	}

	extraArgs := toStringSliceAny(ordjson.GetArr(data, "args"))
	runID, errStr := a.Runs.StartProfileRun(profile, argValues, extraArgs, "manual", nil)
	if errStr != "" {
		return ordjson.New().Set("error", errStr), http.StatusBadRequest
	}
	return ordjson.New().Set("run_id", runID), http.StatusOK
}

// RunWorkflow starts a workflow run.
func (a *API) RunWorkflow(data *ordjson.OMap) (*ordjson.OMap, int) {
	workflowID := ordjson.GetStr(data, "workflow_id")
	workflows, err := a.DB.Load(store.ColWorkflows)
	if err != nil {
		workflows = nil
	}

	var workflow *ordjson.OMap
	for _, w := range workflows {
		if ordjson.GetStr(w, "id") == workflowID {
			workflow = w
			break
		}
	}
	if workflow == nil {
		return ordjson.New().Set("error", "Workflow not found"), http.StatusNotFound
	}
	runID := a.Runs.StartWorkflowRun(workflow, "manual", nil)
	return ordjson.New().Set("run_id", runID), http.StatusOK
}

// CancelRun stops a running run.
func (a *API) CancelRun(runID string) (*ordjson.OMap, int) {
	if !a.Runs.CancelRun(runID) {
		return ordjson.New().Set("error", "Run not found or already finished"), http.StatusNotFound
	}
	return ordjson.New().Set("ok", true), http.StatusOK
}

// toStringSliceAny converts a JSON array into plain argv strings.
func toStringSliceAny(arr []any) []string {
	out := make([]string, 0, len(arr))
	for _, v := range arr {
		out = append(out, pythonStr(v))
	}
	return out
}

// pythonStr mirrors Python's str() for the value shapes the frontend
// sends along with run requests (strings, numbers, booleans).
func pythonStr(v any) string {
	switch x := v.(type) {
	case string:
		return x
	case bool:
		if x {
			return "True"
		}
		return "False"
	default:
		return fmt.Sprint(v)
	}
}
