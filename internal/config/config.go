// Package config holds the server's tunable settings and file locations.
//
// Values can be overridden with environment variables so tests and the
// e2e harness can run isolated instances (the Python original hardcoded
// paths relative to the source tree; a compiled binary needs paths that
// work next to the executable).
package config

import (
	"os"
	"path/filepath"
	"runtime"
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

// DataDir returns the directory holding the database, logs and the
// extracted Python runtime.
//
// Resolution order:
//  1. LAUNCHER_DATA_DIR env var (tests and the e2e harness)
//  2. "data" next to the executable (portable single-binary layout)
//  3. "data" in the current directory (go run / development)
func DataDir() string {
	if v := os.Getenv("LAUNCHER_DATA_DIR"); v != "" {
		return v
	}
	if exe, err := os.Executable(); err == nil {
		// Under "go run" the executable lives in a temp dir; using it
		// would scatter data across throwaway folders, so fall through
		// to the working directory instead.
		if dir := filepath.Dir(exe); !isGoRunCache(dir) {
			return filepath.Join(dir, "data")
		}
	}
	return "data"
}

func isGoRunCache(dir string) bool {
	return filepath.Base(filepath.Dir(dir)) == "go-build"
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
