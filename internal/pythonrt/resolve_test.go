package pythonrt

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"launchcontrol/internal/config"
)

// makeInterpreter creates an empty executable file standing in for a
// python binary.
func makeInterpreter(t *testing.T, path string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o750); err != nil {
		t.Fatalf("mkdir %s: %v", filepath.Dir(path), err)
	}
	if err := os.WriteFile(path, []byte("#!/bin/sh\n"), 0o755); err != nil {
		t.Fatalf("write %s: %v", path, err)
	}
}

func TestInterpreterFromPathAcceptsInterpreterFile(t *testing.T) {
	exe := filepath.Join(t.TempDir(), "python3.9")
	makeInterpreter(t, exe)

	got, err := InterpreterFromPath(exe)
	if err != nil {
		t.Fatalf("InterpreterFromPath: %v", err)
	}
	if got != exe {
		t.Errorf("got %q, want %q", got, exe)
	}
}

func TestInterpreterFromPathAcceptsDirectory(t *testing.T) {
	root := t.TempDir()
	makeInterpreter(t, filepath.Join(root, "bin", "python3"))

	got, err := InterpreterFromPath(root)
	if err != nil {
		t.Fatalf("InterpreterFromPath: %v", err)
	}
	if got != filepath.Join(root, "bin", "python3") {
		t.Errorf("got %q, want the interpreter inside the dir", got)
	}
}

func TestInterpreterFromPathRejectsEmptyDirectories(t *testing.T) {
	empty := t.TempDir()

	if _, err := InterpreterFromPath(empty); err == nil {
		t.Error("expected an error for a directory without an interpreter")
	}
}

func TestInterpreterFromPathRejectsMissingPath(t *testing.T) {
	missing := filepath.Join(t.TempDir(), "gone")

	if _, err := InterpreterFromPath(missing); err == nil {
		t.Error("expected an error for a missing path")
	}
}

func TestResolvePrefersConfiguredRuntime(t *testing.T) {
	t.Setenv("LAUNCHER_DATA_DIR", t.TempDir())

	custom := filepath.Join(t.TempDir(), "venv", binPython())
	makeInterpreter(t, custom)
	if err := config.SaveSettings(config.Settings{RuntimePath: custom}); err != nil {
		t.Fatalf("SaveSettings: %v", err)
	}

	got, err := Resolve()
	if err != nil {
		t.Fatalf("Resolve: %v", err)
	}
	if got != custom {
		t.Errorf("Resolve = %q, want the configured runtime %q", got, custom)
	}
}

func TestResolveFallsBackWhenConfiguredRuntimeMissing(t *testing.T) {
	t.Setenv("LAUNCHER_DATA_DIR", t.TempDir())

	if err := config.SaveSettings(config.Settings{RuntimePath: "/no/such/python"}); err != nil {
		t.Fatalf("SaveSettings: %v", err)
	}

	got, err := Resolve()
	if err != nil {
		t.Fatalf("Resolve: %v", err)
	}
	fallback, fallbackErr := Interpreter()
	if fallbackErr != nil {
		t.Fatalf("Interpreter: %v", fallbackErr)
	}
	if got != fallback {
		t.Errorf("Resolve = %q, want the fallback %q", got, fallback)
	}
}

func TestResolveUsesEmptySetting(t *testing.T) {
	t.Setenv("LAUNCHER_DATA_DIR", t.TempDir())

	got, err := Resolve()
	if err != nil {
		t.Fatalf("Resolve: %v", err)
	}
	if strings.Contains(got, "no/such") {
		t.Errorf("Resolve picked up a stale setting: %q", got)
	}
}

// binPython is where dirLayoutCandidates expects an interpreter in a
// venv/install directory, for the platform under test.
func binPython() string {
	if runtime.GOOS == "windows" {
		return filepath.Join("Scripts", "python.exe")
	}
	return filepath.Join("bin", "python3")
}
