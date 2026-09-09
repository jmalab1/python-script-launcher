// Choosing which interpreter runs user scripts:
//
//  1. a runtime the user picked on the Settings page (an interpreter
//     binary or a Python install/venv directory)
//  2. the packaged runtime bundled with release builds
//  3. a python3/python found on PATH (dev builds)
package pythonrt

import (
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"runtime"

	"launchcontrol/internal/config"
)

// Resolve returns the interpreter to run user scripts with, re-reading
// the settings file on every call so a change on the Settings page
// takes effect on the next run without a server restart. When the
// configured path no longer exists it falls back to the packaged
// runtime (or a system python) and explains why in the server log.
func Resolve() (string, error) {
	if configured := config.RuntimePathSetting(); configured != "" {
		if path, err := InterpreterFromPath(configured); err == nil {
			return path, nil
		} else {
			slog.Warn("Configured runtime is not usable - falling back to the packaged runtime",
				"path", configured, "err", err)
		}
	}
	return Interpreter()
}

// InterpreterFromPath turns a user-entered runtime location into an
// interpreter path. The location may be the interpreter itself or a
// Python install/venv directory (e.g. venv/bin/python3). It must exist
// right now: the caller decides whether that is an error (Settings
// save) or a fallback (Resolve).
func InterpreterFromPath(location string) (string, error) {
	info, err := os.Stat(location)
	if err != nil {
		return "", fmt.Errorf("not found: %w", err)
	}

	if !info.IsDir() {
		return location, nil
	}

	// A directory: probe the usual interpreter spots inside it.
	for _, rel := range dirLayoutCandidates() {
		candidate := filepath.Join(location, rel)
		if info, err := os.Stat(candidate); err == nil && !info.IsDir() {
			return candidate, nil
		}
	}
	return "", fmt.Errorf("no python interpreter found inside %s", location)
}

// dirLayoutCandidates lists where an interpreter can sit inside a
// Python install or virtualenv directory, per platform.
func dirLayoutCandidates() []string {
	if runtime.GOOS == "windows" {
		return []string{
			"python.exe",                           // install layout (python-build-standalone)
			filepath.Join("Scripts", "python.exe"), // venv layout
		}
	}
	return []string{
		filepath.Join("bin", "python3"), // install and venv layout
		filepath.Join("bin", "python"),
	}
}
