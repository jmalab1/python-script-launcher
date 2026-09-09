package config

import (
	"os"
	"path/filepath"
	"runtime"
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

// TestLogFileAndRuntimeDir checks the file layout inside the data dir.
func TestLogFileAndRuntimeDir(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("LAUNCHER_DATA_DIR", dir)

	if got, want := LogFile(), filepath.Join(dir, "server.log"); got != want {
		t.Errorf("LogFile = %q, want %q", got, want)
	}
	if got, want := RuntimeDir(), filepath.Join(dir, "runtime"); got != want {
		t.Errorf("RuntimeDir = %q, want %q", got, want)
	}
}

// exeDir returns the directory holding the test binary; the adoption
// helper looks for legacy data dirs there.
func exeDir(t *testing.T) string {
	t.Helper()
	exe, err := os.Executable()
	if err != nil {
		t.Fatalf("os.Executable: %v", err)
	}
	return filepath.Dir(exe)
}

// createLegacyDir makes an earlier-build data dir next to the test
// binary. It refuses to touch a dir it did not create, and cleans up
// whichever side the dir ends up on (adoption renames it away).
func createLegacyDir(t *testing.T, name string) string {
	t.Helper()
	dir := filepath.Join(exeDir(t), name)
	if _, err := os.Stat(dir); err == nil {
		t.Skipf("%s already exists next to the test binary; not touching it", dir)
	}
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.RemoveAll(dir) })
	return dir
}

// TestAdoptLegacyDataDirMovesData checks the rename: a "data" folder
// left next to the executable by an earlier build becomes the canonical
// data dir, contents intact.
func TestAdoptLegacyDataDirMovesData(t *testing.T) {
	base := t.TempDir()
	datadir := filepath.Join(base, "user-state", AppDataDirName)
	t.Setenv("LAUNCHER_DATA_DIR", datadir)

	legacy := createLegacyDir(t, "data")
	if err := os.MkdirAll(filepath.Join(legacy, "nested"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(legacy, "nested", "launcher.db"), []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}

	adoptLegacyDataDir()

	if _, err := os.Stat(filepath.Join(datadir, "nested", "launcher.db")); err != nil {
		t.Errorf("legacy data did not move onto the canonical location: %v", err)
	}
	if _, err := os.Stat(legacy); !os.IsNotExist(err) {
		t.Errorf("legacy dir should be gone after adoption: %v", err)
	}
}

// TestAdoptLegacyDataDirFallsBackToSecondName covers the second legacy
// layout name ("launchctl-data") when no "data" folder exists.
func TestAdoptLegacyDataDirFallsBackToSecondName(t *testing.T) {
	if _, err := os.Stat(filepath.Join(exeDir(t), "data")); err == nil {
		t.Skip("a data dir also exists next to the test binary; adoption would pick that one")
	}
	base := t.TempDir()
	datadir := filepath.Join(base, AppDataDirName)
	t.Setenv("LAUNCHER_DATA_DIR", datadir)

	legacy := createLegacyDir(t, AppDataDirName)
	if err := os.WriteFile(filepath.Join(legacy, "launcher.db"), []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}

	adoptLegacyDataDir()

	if _, err := os.Stat(filepath.Join(datadir, "launcher.db")); err != nil {
		t.Errorf("legacy launchctl-data dir was not adopted: %v", err)
	}
	if _, err := os.Stat(legacy); !os.IsNotExist(err) {
		t.Errorf("legacy dir should be gone after adoption: %v", err)
	}
}

// TestAdoptLegacyDataDirKeepsExistingDataDir: when the canonical dir is
// already there, adoption must do nothing (live data is never
// clobbered or merged).
func TestAdoptLegacyDataDirKeepsExistingDataDir(t *testing.T) {
	base := t.TempDir()
	datadir := filepath.Join(base, AppDataDirName)
	t.Setenv("LAUNCHER_DATA_DIR", datadir)

	if err := os.MkdirAll(datadir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(datadir, "launcher.db"), []byte("live"), 0o644); err != nil {
		t.Fatal(err)
	}

	legacy := createLegacyDir(t, "data")
	if err := os.WriteFile(filepath.Join(legacy, "old.db"), []byte("old"), 0o644); err != nil {
		t.Fatal(err)
	}

	adoptLegacyDataDir()

	if _, err := os.Stat(filepath.Join(datadir, "launcher.db")); err != nil {
		t.Errorf("existing data dir was disturbed: %v", err)
	}
	if _, err := os.Stat(filepath.Join(datadir, "old.db")); !os.IsNotExist(err) {
		t.Error("legacy files must not be merged into the live data dir")
	}
	if _, err := os.Stat(filepath.Join(legacy, "old.db")); err != nil {
		t.Errorf("legacy dir should stay in place when the data dir exists: %v", err)
	}
}

// TestAdoptLegacyDataDirNoLegacyNoop: with no legacy folder anywhere,
// the canonical dir is simply never created.
func TestAdoptLegacyDataDirNoLegacyNoop(t *testing.T) {
	base := t.TempDir()
	datadir := filepath.Join(base, "user-state", AppDataDirName)
	t.Setenv("LAUNCHER_DATA_DIR", datadir)

	// A leftover legacy dir next to the test binary (from a failed
	// earlier test) would be adopted and break this assertion.
	for _, name := range legacyDataDirNames {
		if _, err := os.Stat(filepath.Join(exeDir(t), name)); err == nil {
			t.Skipf("legacy dir %q exists next to the test binary", name)
		}
	}

	adoptLegacyDataDir()

	if _, err := os.Stat(datadir); !os.IsNotExist(err) {
		t.Errorf("no legacy dir, so the data dir must not be created: %v", err)
	}
}

// TestAdoptLegacyDataDirUnwritableParent: when the parent of the data
// dir cannot be created, adoption gives up and leaves the legacy dir
// untouched.
func TestAdoptLegacyDataDirUnwritableParent(t *testing.T) {
	base := t.TempDir()
	blocker := filepath.Join(base, "blocker")
	if err := os.WriteFile(blocker, []byte("a file, not a dir"), 0o644); err != nil {
		t.Fatal(err)
	}
	t.Setenv("LAUNCHER_DATA_DIR", filepath.Join(blocker, AppDataDirName))

	legacy := createLegacyDir(t, "data")
	adoptLegacyDataDir()

	if _, err := os.Stat(legacy); err != nil {
		t.Errorf("legacy dir should be untouched when the target parent is missing: %v", err)
	}
}

// TestAdoptLegacyDataDirOnce covers the exported entry point: with the
// data dir already in place it must be a harmless no-op.
func TestAdoptLegacyDataDirOnce(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("LAUNCHER_DATA_DIR", dir)

	AdoptLegacyDataDir()

	if _, err := os.Stat(dir); err != nil {
		t.Errorf("existing data dir should be left alone: %v", err)
	}
}

// TestOnWindowsMatchesOS pins the helper to the real platform: the
// auto-browser-open and port-conflict pause in main.go key off this
// value, so it must match runtime.GOOS everywhere.
func TestOnWindowsMatchesOS(t *testing.T) {
	if OnWindows() != (runtime.GOOS == "windows") {
		t.Fatal("OnWindows must report the real GOOS")
	}
}
