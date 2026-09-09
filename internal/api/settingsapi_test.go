package api

import (
	"os"
	"path/filepath"
	"testing"

	"launchcontrol/internal/config"
	"launchcontrol/internal/ordjson"
)

// callConfig sends a JSON body ("" for a bare GET) to /api/config and
// decodes the object response.
func callConfig(t *testing.T, a *API, method, body string) (int, map[string]any) {
	t.Helper()
	status, parsed := call(t, a, method, "/api/config", body)
	om, ok := parsed.(*ordjson.OMap)
	if !ok {
		t.Fatalf("response for %s /api/config is not an object: %T", method, parsed)
	}
	decoded := map[string]any{}
	for _, key := range om.Keys() {
		decoded[key] = om.Get(key)
	}
	return status, decoded
}

func TestConfigGetDefaultsToEmptyRuntimePath(t *testing.T) {
	t.Setenv("LAUNCHER_DATA_DIR", t.TempDir())
	a := newTestAPI(t)

	status, resp := callConfig(t, a, "GET", "")
	if status != 200 {
		t.Fatalf("status = %d, want 200", status)
	}
	if resp["runtime_path"] != "" {
		t.Errorf("runtime_path = %v, want empty", resp["runtime_path"])
	}
	if resp["effective_interpreter"] == "" {
		t.Error("effective_interpreter missing from the response")
	}
}

func TestConfigSetAcceptsValidRuntime(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("LAUNCHER_DATA_DIR", dir)

	exe := filepath.Join(dir, "venv", "bin", "python3")
	if err := os.MkdirAll(filepath.Dir(exe), 0o750); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	if err := os.WriteFile(exe, []byte("#!/bin/sh\n"), 0o755); err != nil {
		t.Fatalf("write: %v", err)
	}

	a := newTestAPI(t)
	status, resp := callConfig(t, a, "POST", `{"runtime_path":"`+filepath.Join(dir, "venv")+`"}`)
	if status != 200 {
		t.Fatalf("status = %d, resp %v", status, resp)
	}
	venv := filepath.Join(dir, "venv")
	if resp["runtime_path"] != venv {
		t.Errorf("runtime_path = %v, want %q", resp["runtime_path"], venv)
	}
	if resp["effective_interpreter"] != exe {
		t.Errorf("effective_interpreter = %v, want %q", resp["effective_interpreter"], exe)
	}
	if got := config.RuntimePathSetting(); got != venv {
		t.Errorf("setting on disk = %q, want %q", got, venv)
	}
}

func TestConfigSetRejectsUnusableRuntime(t *testing.T) {
	t.Setenv("LAUNCHER_DATA_DIR", t.TempDir())
	a := newTestAPI(t)

	status, resp := callConfig(t, a, "POST", `{"runtime_path":"/no/such/python"}`)
	if status != 400 {
		t.Fatalf("status = %d, want 400", status)
	}
	if resp["error"] == "" {
		t.Error("error message missing from the response")
	}
	// A rejected save must not touch the stored setting.
	if got := config.RuntimePathSetting(); got != "" {
		t.Errorf("setting on disk = %q, want it untouched", got)
	}
}

func TestConfigSetEmptyClearsSetting(t *testing.T) {
	t.Setenv("LAUNCHER_DATA_DIR", t.TempDir())
	a := newTestAPI(t)

	dir := t.TempDir()
	exe := filepath.Join(dir, "python3")
	if err := os.WriteFile(exe, []byte("#!/bin/sh\n"), 0o755); err != nil {
		t.Fatalf("write: %v", err)
	}
	if _, resp := callConfig(t, a, "POST", `{"runtime_path":"`+exe+`"}`); resp["error"] != nil {
		t.Fatalf("save failed: %v", resp)
	}

	status, resp := callConfig(t, a, "POST", `{"runtime_path":""}`)
	if status != 200 {
		t.Fatalf("status = %d, want 200", status)
	}
	if got := config.RuntimePathSetting(); got != "" {
		t.Errorf("setting on disk = %q, want it cleared", got)
	}
	if resp["runtime_path"] != "" {
		t.Errorf("runtime_path = %v, want empty", resp["runtime_path"])
	}
}

func TestExpandHomeResolvesLeadingTilde(t *testing.T) {
	home, err := os.UserHomeDir()
	if err != nil || home == "" {
		t.Skip("no home directory to expand against")
	}

	if got := expandHome("~"); got != home {
		t.Errorf("expandHome(~) = %q, want %q", got, home)
	}
	if got := expandHome("~/py/bin/python3"); got != filepath.Join(home, "py/bin/python3") {
		t.Errorf("expandHome(~/...) = %q", got)
	}
	if got := expandHome("/plain/path"); got != "/plain/path" {
		t.Errorf("expandHome(plain) = %q, want it unchanged", got)
	}
}
