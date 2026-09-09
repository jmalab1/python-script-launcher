// User-editable settings that live outside the launcher database.
//
// The database schema is frozen for compatibility with the earlier
// Python app, so new settings go into their own small JSON file in the
// data directory instead: settings.json. It is read fresh on every use
// so changes saved through the Settings page take effect without a
// server restart.
package config

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sync"
)

// Settings holds the user-editable options kept in settings.json.
type Settings struct {
	// RuntimePath is the Python interpreter (or a Python install/venv
	// directory) to run user scripts with. Empty means "use the
	// packaged runtime".
	RuntimePath string `json:"runtime_path"`
}

// settingsMu guards settings.json against concurrent reads and writes.
var settingsMu sync.Mutex

// SettingsPath is the settings file inside DataDir.
func SettingsPath() string { return filepath.Join(DataDir(), "settings.json") }

// LoadSettings reads settings.json. A missing (or unreadable) file
// yields the defaults rather than an error: everything in settings has
// a safe fallback, and a corrupt file must not stop the app from
// starting.
func LoadSettings() Settings {
	var s Settings
	settingsMu.Lock()
	defer settingsMu.Unlock()

	raw, err := os.ReadFile(SettingsPath())
	if err != nil {
		return s
	}
	// Ignore decode errors the same way: keep the defaults.
	_ = json.Unmarshal(raw, &s)
	return s
}

// SaveSettings writes settings.json, replacing the file atomically so a
// half-written file (crash mid-save) can never be read back.
func SaveSettings(s Settings) error {
	settingsMu.Lock()
	defer settingsMu.Unlock()

	raw, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return err
	}

	path := SettingsPath()
	if err := os.MkdirAll(filepath.Dir(path), 0o750); err != nil {
		return err
	}

	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, raw, 0o600); err != nil {
		return err
	}
	if err := os.Rename(tmp, path); err != nil {
		_ = os.Remove(tmp)
		return err
	}
	return nil
}

// RuntimePathSetting returns the configured runtime path ("" when
// unset). It is the short form LoadSettings provides for callers that
// only need the one field.
func RuntimePathSetting() string {
	return LoadSettings().RuntimePath
}
