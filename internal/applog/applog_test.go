package applog

import (
	"bytes"
	"context"
	"log/slog"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
)

// backupNames lists the rotated backups (timestamp-suffixed files) that
// currently sit next to the active log.
func backupNames(t *testing.T, dir, base string) []string {
	t.Helper()
	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Fatal(err)
	}

	var names []string
	for _, e := range entries {
		name := e.Name()
		if strings.HasPrefix(name, base+".") && backupSuffix.MatchString(strings.TrimPrefix(name, base+".")) {
			names = append(names, name)
		}
	}
	return names
}

func TestNewCreatesMissingDirsAndAppends(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "nested", "server.log")

	w, err := New(path, 0, 0)
	if err != nil {
		t.Fatal(err)
	}
	defer w.Close()

	if _, err := w.Write([]byte("first\n")); err != nil {
		t.Fatal(err)
	}
	// A second writer on the same path must append, not truncate.
	w2, err := New(path, 0, 0)
	if err != nil {
		t.Fatal(err)
	}
	defer w2.Close()
	if _, err := w2.Write([]byte("second\n")); err != nil {
		t.Fatal(err)
	}

	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if got := string(data); got != "first\nsecond\n" {
		t.Fatalf("log content = %q, want %q", got, "first\nsecond\n")
	}
}

func TestWriteRotatesWhenMaxSizeExceeded(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "server.log")

	w, err := New(path, 10, 5)
	if err != nil {
		t.Fatal(err)
	}
	defer w.Close()

	// First write fits; the second one crosses the cap and must roll
	// the first write's content into a timestamped backup.
	if _, err := w.Write([]byte("aaaaaaaaaa")); err != nil {
		t.Fatal(err)
	}
	if _, err := w.Write([]byte("bbbbbbbbbb")); err != nil {
		t.Fatal(err)
	}

	backups := backupNames(t, dir, "server.log")
	if len(backups) != 1 {
		t.Fatalf("got %d backups (%v), want 1", len(backups), backups)
	}
	if !backupSuffix.MatchString(strings.TrimPrefix(backups[0], "server.log.")) {
		t.Fatalf("backup name %q does not match the timestamp suffix pattern", backups[0])
	}

	backupData, err := os.ReadFile(filepath.Join(dir, backups[0]))
	if err != nil {
		t.Fatal(err)
	}
	if string(backupData) != "aaaaaaaaaa" {
		t.Fatalf("backup content = %q, want the pre-rotation write", backupData)
	}

	active, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if string(active) != "bbbbbbbbbb" {
		t.Fatalf("active log content = %q, want only the post-rotation write", active)
	}
}

func TestWriteDoesNotRotateWhenMaxSizeZero(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "server.log")

	w, err := New(path, 0, 5)
	if err != nil {
		t.Fatal(err)
	}
	defer w.Close()

	// maxSize 0 disables the size cap entirely.
	for i := 0; i < 10; i++ {
		if _, err := w.Write([]byte(strings.Repeat("x", 100))); err != nil {
			t.Fatal(err)
		}
	}

	if backups := backupNames(t, dir, "server.log"); len(backups) != 0 {
		t.Fatalf("got backups %v, want none with maxSize 0", backups)
	}
}

func TestRotateUniquifiesSameSecondBackupName(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "server.log")

	// Two rotations inside the same second produce identical timestamp
	// candidates, so the second must get a -1 suffix instead of
	// overwriting the first backup.
	w, err := New(path, 10, 5)
	if err != nil {
		t.Fatal(err)
	}
	defer w.Close()

	if _, err := w.Write([]byte(strings.Repeat("a", 8))); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 2; i++ {
		if _, err := w.Write([]byte(strings.Repeat("b", 8))); err != nil {
			t.Fatal(err)
		}
	}

	backups := backupNames(t, dir, "server.log")
	if len(backups) != 2 {
		t.Fatalf("got backups %v, want 2", backups)
	}

	stamped := 0
	uniquified := 0
	for _, name := range backups {
		suffix := strings.TrimPrefix(name, "server.log.")
		switch {
		case regexp.MustCompile(`^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$`).MatchString(suffix):
			stamped++
		case regexp.MustCompile(`^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}-1$`).MatchString(suffix):
			uniquified++
		}
	}
	if stamped != 1 || uniquified != 1 {
		t.Fatalf("backups %v: want one plain timestamp and one -1 uniquified name", backups)
	}

	// The -1 backup holds the middle write; the plain one the first.
	first, err := os.ReadFile(filepath.Join(dir, backups[0]))
	if err != nil {
		t.Fatal(err)
	}
	if string(first) != strings.Repeat("a", 8) {
		t.Fatalf("first backup content = %q", first)
	}
}

func TestPruneKeepsOnlyBackupCountNewest(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "server.log")

	w, err := New(path, 10, 2)
	if err != nil {
		t.Fatal(err)
	}
	defer w.Close()

	// Rotate five times; pruning runs after every rollover, so only
	// the two newest backups may survive.
	if _, err := w.Write([]byte("seed")); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 5; i++ {
		if _, err := w.Write([]byte(strings.Repeat("b", 10))); err != nil {
			t.Fatal(err)
		}
	}

	// Backup names sort chronologically (fixed-width stamps, -N only
	// breaks same-second ties), so exactly the backupCount newest survive.
	backups := backupNames(t, dir, "server.log")
	if len(backups) != 2 {
		t.Fatalf("got %d backups (%v), want 2 after pruning", len(backups), backups)
	}

	// Both survivors must still be readable, and the active log holds
	// only the last write.
	for _, name := range backups {
		if _, err := os.ReadFile(filepath.Join(dir, name)); err != nil {
			t.Fatalf("kept backup %s unreadable: %v", name, err)
		}
	}
	active, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if string(active) != strings.Repeat("b", 10) {
		t.Fatalf("active log content = %q", active)
	}
}

func TestCloseStopsWrites(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "server.log")

	w, err := New(path, 0, 0)
	if err != nil {
		t.Fatal(err)
	}
	if err := w.Close(); err != nil {
		t.Fatalf("Close = %v", err)
	}

	if _, err := w.Write([]byte("nope")); err == nil {
		t.Fatal("Write after Close should fail")
	}
}

func TestSetupWritesPythonStyleLines(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "sub", "server.log")

	// Setup replaces the default logger: put the old one back so other
	// tests are not affected.
	prev := slog.Default()
	t.Cleanup(func() { slog.SetDefault(prev) })

	w := Setup(path, 0, 0)
	if w == nil {
		t.Fatal("Setup returned nil writer")
	}
	defer w.Close()

	slog.Info("hello", "k", "v")

	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}

	line := string(bytes.TrimRight(data, "\n"))
	re := regexp.MustCompile(`^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[INFO\] hello k=v$`)
	if !re.MatchString(line) {
		t.Fatalf("log line %q does not match the Python format", line)
	}
}

func TestSetupReturnsNilWhenDirCannotBeCreated(t *testing.T) {
	dir := t.TempDir()
	blocker := filepath.Join(dir, "file")
	if err := os.WriteFile(blocker, []byte("x"), 0o600); err != nil {
		t.Fatal(err)
	}

	prev := slog.Default()
	t.Cleanup(func() { slog.SetDefault(prev) })

	// A regular file sits where Setup needs a directory.
	if got := Setup(filepath.Join(blocker, "server.log"), 0, 0); got != nil {
		t.Fatalf("Setup = %v, want nil for an unusable path", got)
	}
}

func TestPythonStyleHandlerLevelsAndAttrs(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(&pythonStyleHandler{w: &buf})

	logger.Debug("d")
	logger.Info("i")
	logger.Warn("w")
	logger.Error("e")

	want := []string{"[DEBUG] d", "[INFO] i", "[WARNING] w", "[ERROR] e"}
	for _, fragment := range want {
		if !strings.Contains(buf.String(), fragment) {
			t.Errorf("output %q missing %q", buf.String(), fragment)
		}
	}
	if !strings.HasSuffix(buf.String(), "\n") {
		t.Error("records must end with a newline")
	}
}

func TestPythonStyleHandlerBasics(t *testing.T) {
	h := &pythonStyleHandler{w: &bytes.Buffer{}}

	if !h.Enabled(context.Background(), slog.LevelDebug) {
		t.Error("handler must enable every level")
	}
	if h.WithAttrs([]slog.Attr{slog.String("a", "b")}) != slog.Handler(h) {
		t.Error("WithAttrs must return the same handler")
	}
	if h.WithGroup("g") != slog.Handler(h) {
		t.Error("WithGroup must return the same handler")
	}
}
