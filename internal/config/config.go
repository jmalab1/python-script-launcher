// Package config holds the server's tunable settings and file locations.
//
// Values can be overridden with environment variables so tests and the
// e2e harness can run isolated instances (the Python original hardcoded
// paths relative to the source tree; a compiled binary needs paths that
// work next to the executable).
package config

import (
	"log/slog"
	"os"
	"path/filepath"
	"runtime"
	"sync"
	"time"
)

// DefaultPort is the port the web UI listens on (bound to 127.0.0.1).
const DefaultPort = 8765

// Collection names, used as SQLite table names and storage keys.
const (
	ColProfiles  = "profiles"
	ColWorkflows = "workflows"
	ColHistory   = "history"
	ColAudit     = "audit"
	ColSchedules = "schedules"
)

// SchedulerTickSeconds is how often the scheduler wakes up to check for
// due schedules.
const SchedulerTickSeconds = 5 * time.Second

// Log rotation for data/server.log: rotate when the active file reaches
// LogMaxBytes, keep LogBackupCount rotated copies named
// server.log.<YYYY-MM-DD_HH-MM-SS>. Set LogMaxBytes to 0 to disable.
const (
	LogMaxBytes    = 2_000_000
	LogBackupCount = 3
)

// AppDataDirName is the folder name used inside the OS's per-user state
// location. One deterministic spot per user, no matter where the binary
// was launched from or which copy of it was used.
const AppDataDirName = "launchctl-data"

// legacyDataDirLayouts are data directories created by earlier builds
// ("data" and "launchctl-data" next to the executable); startup moves
// the first one found onto the canonical per-user location.
var legacyDataDirNames = []string{"data", AppDataDirName}

// DataDir returns the directory holding the database, logs and the
// extracted Python runtime.
//
// Resolution order:
//  1. LAUNCHER_DATA_DIR env var (tests and the e2e harness)
//  2. the OS's per-user state location with AppDataDirName underneath
//     (Linux: XDG data home; macOS: Application Support; Windows:
//     %APPDATA%), so every binary copy shares one home
func DataDir() string {
	if v := os.Getenv("LAUNCHER_DATA_DIR"); v != "" {
		return v
	}
	return filepath.Join(UserStateDir(), AppDataDirName)
}

// UserStateDir is the per-user base for app state, following platform
// conventions. Falls back to the executable's directory (or the current
// one) when neither the OS homes nor the user's home are known.
func UserStateDir() string {
	switch runtime.GOOS {
	case "windows":
		if dir, err := os.UserConfigDir(); err == nil && dir != "" {
			return dir
		}
	case "darwin":
		if home, err := os.UserHomeDir(); err == nil && home != "" {
			return filepath.Join(home, "Library", "Application Support")
		}
	default:
		if xdg := os.Getenv("XDG_DATA_HOME"); xdg != "" {
			return xdg
		}
		if home, err := os.UserHomeDir(); err == nil && home != "" {
			return filepath.Join(home, ".local", "share")
		}
	}
	if exe, err := os.Executable(); err == nil {
		return filepath.Dir(exe)
	}
	return "."
}

// adoptLegacyDataDir moves an earlier-build data directory next to the
// executable onto the canonical per-user location (best effort): only
// when the destination does not exist yet and a legacy directory with
// data is found. Runs once per process.
func adoptLegacyDataDir() {
	datadir := DataDir()
	if _, err := os.Stat(datadir); err == nil {
		return
	}
	for _, legacyName := range legacyDataDirNames {
		legacyPath := ""
		if exe, err := os.Executable(); err == nil {
			legacyPath = filepath.Join(filepath.Dir(exe), legacyName)
		} else {
			legacyPath = legacyName
		}
		if legacyPath == datadir {
			continue
		}
		if info, err := os.Stat(legacyPath); err == nil && info.IsDir() {
			if err := os.MkdirAll(filepath.Dir(datadir), 0o755); err != nil {
				return
			}
			if err := os.Rename(legacyPath, datadir); err == nil {
				slog.Info("Adopted the existing data directory",
					"from", legacyPath, "to", datadir)
				return
			}
		}
	}
}

var adoptOnce sync.Once

// AdoptLegacyDataDir runs the one-time legacy data-dir adoption check.
// Startup calls it before anything else touches the data directory.
func AdoptLegacyDataDir() {
	adoptOnce.Do(adoptLegacyDataDir)
}

// DBPath is the SQLite database file inside DataDir.
func DBPath() string { return filepath.Join(DataDir(), "launcher.db") }

// LogFile is the server's own log file path.
func LogFile() string { return filepath.Join(DataDir(), "server.log") }

// RuntimeDir is where the embedded Python runtime is extracted on
// first run.
func RuntimeDir() string { return filepath.Join(DataDir(), "runtime") }

// PythonExtensions are the script suffixes the file browser accepts.
var PythonExtensions = map[string]bool{".py": true, ".pyw": true}

// OnWindows reports whether we are running on Windows, where the server
// auto-opens the browser and needs the "Press Enter" pause on port
// conflict.
func OnWindows() bool { return runtime.GOOS == "windows" }
