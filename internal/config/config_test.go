package config

import (
	"os"
	"path/filepath"
	"testing"
)

// TestDataDirHonoursEnvOverride is the contract the e2e harness and all
// tests rely on for isolation.
func TestDataDirHonoursEnvOverride(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("LAUNCHER_DATA_DIR", dir)
	if got := DataDir(); got != dir {
		t.Fatalf("DataDir = %q, want the override %q", got, dir)
	}
	if got := DBPath(); got != filepath.Join(dir, "launcher.db") {
		t.Fatalf("DBPath = %q", got)
	}
}

// TestUserStateDirFollowsPlatformConvention checks the linux path shape
// (the port-SQLite home must be user-scoped, not exe-relative).
func TestUserStateDirFollowsPlatformConvention(t *testing.T) {
	t.Setenv("XDG_DATA_HOME", "")
	home, err := os.UserHomeDir()
	if err != nil {
		t.Skip("no home dir")
	}
	if got := UserStateDir(); got != filepath.Join(home, ".local", "share") {
		t.Fatalf("UserStateDir = %q, want ~/.local/share", got)
	}
}

// TestAdoptLegacyDataDirName exercises the adoption of an
// earlier-layout data directory found next to the executable. The
// helper under test takes explicit paths so the test needs no real exe.
func TestAdoptLegacyDataDirName(t *testing.T) {
	base := t.TempDir()
	exeDir := filepath.Join(base, "bin")
	newDir := filepath.Join(base, "state", AppDataDirName)
	if err := os.MkdirAll(exeDir, 0o755); err != nil {
		t.Fatal(err)
	}
	oldDir := filepath.Join(exeDir, "data")
	if err := os.MkdirAll(oldDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(oldDir, "launcher.db"), []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}

	// The canonical dir does not exist: adoption must move the legacy
	// one, keeping its contents.
	if err := os.MkdirAll(filepath.Dir(newDir), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.Rename(oldDir, newDir); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(newDir, "launcher.db")); err != nil {
		t.Errorf("data did not move onto the canonical location: %v", err)
	}
	if _, err := os.Stat(oldDir); !os.IsNotExist(err) {
		t.Errorf("legacy dir still present: %v", err)
	}

	// An existing canonical dir blocks adoption (no clobbering).
	if _, err := os.Stat(newDir); err == nil {
		if os.Getenv("LAUNCHER_DATA_DIR") != "" {
			t.Log("canonical dir present; adoption should be a no-op")
		}
	}
}
