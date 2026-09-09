package config

import (
	"os"
	"path/filepath"
	"testing"
)

// envDataDir points LAUNCHER_DATA_DIR at a fresh temp dir for one test.
func envDataDir(t *testing.T) string {
	t.Helper()
	dir := filepath.Join(t.TempDir(), "data")
	t.Setenv("LAUNCHER_DATA_DIR", dir)
	return dir
}

func TestLoadSettingsDefaultsWhenFileMissing(t *testing.T) {
	envDataDir(t)

	got := LoadSettings()
	if got.RuntimePath != "" {
		t.Errorf("RuntimePath = %q, want empty for a fresh install", got.RuntimePath)
	}
}

func TestSaveAndLoadSettingsRoundTrip(t *testing.T) {
	dir := envDataDir(t)

	want := Settings{RuntimePath: "/opt/python/bin/python3"}
	if err := SaveSettings(want); err != nil {
		t.Fatalf("SaveSettings: %v", err)
	}

	if got := LoadSettings(); got.RuntimePath != want.RuntimePath {
		t.Errorf("LoadSettings = %+v, want %+v", got, want)
	}

	// The file must be private: it lives in a shared per-user dir, and
	// there is no reason for anyone but the owner to read it.
	info, err := os.Stat(SettingsPath())
	if err != nil {
		t.Fatalf("settings file missing after save: %v", err)
	}
	if perm := info.Mode().Perm(); perm != 0o600 {
		t.Errorf("settings file mode = %o, want 600", perm)
	}
	if filepath.Dir(SettingsPath()) != dir {
		t.Errorf("settings file outside LAUNCHER_DATA_DIR: %s", SettingsPath())
	}
}

func TestSaveSettingsLeavesNoTempFile(t *testing.T) {
	envDataDir(t)

	if err := SaveSettings(Settings{RuntimePath: "x"}); err != nil {
		t.Fatalf("SaveSettings: %v", err)
	}
	if _, err := os.Stat(SettingsPath() + ".tmp"); !os.IsNotExist(err) {
		t.Errorf("temp file left behind: %v", err)
	}
}

func TestLoadSettingsCorruptFileFallsBackToDefaults(t *testing.T) {
	dir := envDataDir(t)
	if err := os.MkdirAll(dir, 0o750); err != nil {
		t.Fatalf("mkdir data dir: %v", err)
	}

	if err := os.WriteFile(SettingsPath(), []byte("{not json"), 0o600); err != nil {
		t.Fatalf("write corrupt settings: %v", err)
	}

	if got := LoadSettings(); got.RuntimePath != "" {
		t.Errorf("LoadSettings = %+v, want defaults on corrupt file", got)
	}
}

func TestSaveSettingsOverwritesPreviousValue(t *testing.T) {
	envDataDir(t)

	if err := SaveSettings(Settings{RuntimePath: "/first"}); err != nil {
		t.Fatalf("first SaveSettings: %v", err)
	}
	if err := SaveSettings(Settings{RuntimePath: "/second"}); err != nil {
		t.Fatalf("second SaveSettings: %v", err)
	}

	if got := RuntimePathSetting(); got != "/second" {
		t.Errorf("RuntimePathSetting = %q, want /second", got)
	}
}
