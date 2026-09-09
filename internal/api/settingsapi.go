// Settings endpoints for the web UI's Settings page. Currently the only
// setting is the Python runtime location used to run user scripts; the
// packaged runtime stays the fallback when it is not set (see
// pythonrt.Resolve for the full preference order).
package api

import (
	"os"
	"path/filepath"
	"strings"

	"launchcontrol/internal/config"
	"launchcontrol/internal/ordjson"
	"launchcontrol/internal/pythonrt"
)

// runtimeSettingKey is the request/response field name for the runtime
// location, mirroring settings.json's key.
const runtimeSettingKey = "runtime_path"

// ConfigGet answers GET /api/config: both the saved setting and the
// interpreter actually in use, so the Settings page can explain what a
// change would mean before saving.
func (a *API) ConfigGet() *ordjson.OMap {
	effective, _ := pythonrt.Resolve()
	return ordjson.New().
		Set(runtimeSettingKey, config.RuntimePathSetting()).
		Set("effective_interpreter", effective)
}

// ConfigSet answers POST /api/config. An empty runtime_path clears the
// setting (back to the packaged runtime); anything else must point at
// an interpreter file or a Python install/venv directory.
func (a *API) ConfigSet(data *ordjson.OMap) (*ordjson.OMap, int) {
	raw := ordjson.GetStr(data, runtimeSettingKey)
	location := expandHome(strings.TrimSpace(raw))

	if location != "" {
		if _, err := pythonrt.InterpreterFromPath(location); err != nil {
			return ordjson.New().Set("error",
				"Runtime location is not usable: "+err.Error()), 400
		}
	}

	if err := config.SaveSettings(config.Settings{RuntimePath: location}); err != nil {
		return response("error", "Could not save the settings file"), 500
	}

	effective, _ := pythonrt.Resolve()
	return ordjson.New().
		Set(runtimeSettingKey, location).
		Set("effective_interpreter", effective), 200
}

// expandHome resolves a leading ~ to the user's home directory, so a
// path pasted into the Settings page works on every machine.
func expandHome(path string) string {
	if path != "~" && !strings.HasPrefix(path, "~/") && !strings.HasPrefix(path, `~\`) {
		return path
	}
	home, err := os.UserHomeDir()
	if err != nil || home == "" {
		return path
	}
	return filepath.Join(home, path[1:])
}
