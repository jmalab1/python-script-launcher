package pythonrt

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"fmt"
	"os"
	"path/filepath"
	"sort"
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

// makeGzipTar packs a list of (name, data) entries into a gzip'd tar,
// like a miniature install_only archive.
func makeGzipTar(t *testing.T, entries map[string]string) *gzip.Reader {
	t.Helper()
	var buf bytes.Buffer
	gzw := gzip.NewWriter(&buf)
	tw := tar.NewWriter(gzw)
	for _, name := range sortedKeys(entries) {
		data := entries[name]
		if err := tw.WriteHeader(&tar.Header{Name: name, Mode: 0o644, Size: int64(len(data))}); err != nil {
			t.Fatal(err)
		}
		if _, err := tw.Write([]byte(data)); err != nil {
			t.Fatal(err)
		}
	}
	tw.Close()
	gzw.Close()
	gz, err := gzip.NewReader(&buf)
	if err != nil {
		t.Fatal(err)
	}
	return gz
}

func sortedKeys(m map[string]string) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

// TestExtractTarRejectsOverrideContract verifies the sum-of-entries cap
// stops an archive that unpacks more than allowed (decompression bomb).
func TestExtractTarRejectsBomb(t *testing.T) {
	oldCap := maxExtractedBytes
	maxExtractedBytes = 2048
	defer func() { maxExtractedBytes = oldCap }()

	entries := map[string]string{}
	for i := 0; i < 3; i++ {
		entries[fmt.Sprintf("python/lib/file%d.bin", i)] = strings.Repeat("x", 1024)
	}
	dir := t.TempDir()
	gz := makeGzipTar(t, entries)
	if err := extractTar(gz, dir); err == nil {
		t.Fatal("expected the total-size cap to reject oversized archives")
	}
	deep, err := os.ReadDir(filepath.Join(dir, "lib"))
	if err != nil {
		t.Fatalf("lib dir missing: %v", err)
	}
	if len(deep) == 3 {
		t.Error("cap did not stop the extraction early")
	}
}

// TestExtractTarSymlinkEscape verifies an archive cannot use a symlink
// to point outside the extraction dir.
func TestExtractTarSymlinkEscape(t *testing.T) {
	dir := t.TempDir()
	var buf bytes.Buffer
	gzw := gzip.NewWriter(&buf)
	tw := tar.NewWriter(gzw)
	if err := tw.WriteHeader(&tar.Header{Name: "python/bin/evil", Typeflag: tar.TypeSymlink, Linkname: "/etc/passwd"}); err != nil {
		t.Fatal(err)
	}
	tw.Close()
	gzw.Close()
	gz, err := gzip.NewReader(&buf)
	if err != nil {
		t.Fatal(err)
	}

	if err := extractTar(gz, dir); err != nil {
		t.Fatalf("extraction returned an error, expected silent skip: %v", err)
	}
	if _, err := os.Lstat(filepath.Join(dir, "bin/evil")); err == nil {
		t.Error("absolute symlink target was created inside the dir")
	}
}
