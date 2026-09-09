package pythonrt

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// makeFakeRuntime builds a tiny archive shaped like an install_only
// distribution: a bin/python3 executable plus a couple of library files.
func makeFakeRuntime(t *testing.T) []byte {
	t.Helper()
	var buf bytes.Buffer
	gz := gzip.NewWriter(&buf)
	tw := tar.NewWriter(gz)
	type entry struct {
		name string
		data string
		mode int64
		link string
	}
	entries := []entry{
		{"python/bin/python3.12", fakeBin, 0o755, ""},
		{"python/lib/python3.12/os.py", "# fake stdlib stub\n", 0o644, ""},
		{"python/LICENSE", "fake license\n", 0o644, ""},
		{"python/bin/nosymlink-target.bin", "x", 0o644, ""},
		{"../evil.txt", "traversal", 0o644, ""},
		{"python/bin/python3", fakeBin, 0o755, "python3.12"},
	}
	for _, e := range entries {
		hdr := &tar.Header{Name: e.name, Mode: e.mode, Size: int64(len(e.data)), Linkname: e.link}
		if e.link != "" {
			hdr.Typeflag = tar.TypeSymlink
			hdr.Size = 0
		}
		if err := tw.WriteHeader(hdr); err != nil {
			t.Fatal(err)
		}
		if e.link == "" {
			if _, err := tw.Write([]byte(e.data)); err != nil {
				t.Fatal(err)
			}
		}
	}
	tw.Close()
	gz.Close()
	return []byte(buf.String())
}

const fakeBin = "#!/bin/sh\necho fake python\n"

// TestExtractRuntimeAndResolve covers ensureExtracted: contents land,
// the interpreter path is right, symlinks/traversal are safe, and the
// second call reuses the extraction instead of redoing it.
func TestExtractRuntimeAndResolve(t *testing.T) {
	t.Setenv("LAUNCHER_DATA_DIR", t.TempDir())
	data := makeFakeRuntime(t)
	dir, err := ensureExtracted(data)
	if err != nil {
		t.Fatalf("ensureExtracted: %v", err)
	}
	if exe := pythonExecutable(dir); !strings.HasSuffix(exe, "bin/python3") {
		t.Errorf("interpreter path = %q", exe)
	}
	bin := filepath.Join(dir, "bin/python3")
	info, err := os.Stat(bin)
	if err != nil {
		t.Fatalf("bin/python3 missing: %v", err)
	}
	if info.Mode().Perm()&0o100 == 0 {
		t.Error("bin/python3 is not executable")
	}
	if _, err := os.Stat(filepath.Join(dir, "lib/python3.12/os.py")); err != nil {
		t.Errorf("library file missing: %v", err)
	}
	// Traversal entries must not escape the target dir.
	if _, err := os.Stat(filepath.Join(filepath.Dir(dir), "evil.txt")); err == nil {
		t.Error("traversal entry escaped the extraction dir")
	}
	// The interpreter symlink was recreated inside the dir.
	if link, err := os.Readlink(bin[:len(bin)-len("python3")] + "python3"); err != nil || link != "python3.12" {
		t.Errorf("symlink wrong: %q (%v)", link, err)
	}
	// Marker file short-circuits a second extraction.
	if _, err := os.Stat(filepath.Join(dir, ".ready")); err != nil {
		t.Errorf("marker missing: %v", err)
	}
	dir2, err := ensureExtracted(data)
	if err != nil || dir2 != dir {
		t.Errorf("second call should reuse the same dir, got %v (%v)", dir2, err)
	}
}

// TestInterpreterFallsBackToSystemPython covers the no-embedded-runtime
// path used in development builds.
func TestInterpreterFallsBackToSystemPython(t *testing.T) {
	path, err := Interpreter()
	if err != nil {
		t.Fatalf("Interpreter: %v", err)
	}
	if !strings.Contains(path, "python3") {
		t.Errorf("unexpected interpreter %q", path)
	}
	// A second call returns the cached result.
	path2, _ := Interpreter()
	if path2 != path {
		t.Errorf("Interpreter not cached: %q vs %q", path2, path)
	}
}
