// Package pythonrt resolves the interpreter used to run user scripts.
//
// Release builds embed a python-build-standalone distribution for the
// target platform (internal/pythonrt/runtime.tar.gz, populated by the
// build) and extract it to data/runtime on first run, so the user needs
// no Python installed. Development builds without the embedded archive
// fall back to a python3/python found on PATH.
package pythonrt

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"fmt"
	"io"
	"os"
	"os/exec"
	"log/slog"
	"path/filepath"
	"runtime"
	"strings"
	"sync"

	"launchcontrol/internal/config"
)

// RuntimeVersion is stamped onto the extraction directory; bumping it
// (with the archive) triggers a re-extraction.
var RuntimeVersion = "0"

// InstallDir is where the runtime is extracted (under the data dir).
func InstallDir() string { return config.RuntimeDir() }

var (
	resolveOnce sync.Once
	exePath     string
	resolveErr  error
)

// Interpreter resolves the python executable that runs user scripts.
// The first call extracts the embedded runtime if needed; the result is
// cached. An error only occurs when neither the embedded runtime nor a
// system python is available.
func Interpreter() (string, error) {
	resolveOnce.Do(doResolve)
	return exePath, resolveErr
}

func doResolve() {
	if data, ok := embedded(); ok && len(data) > 0 {
		if dir, err := ensureExtracted(data); err == nil {
			exePath = pythonExecutable(dir)
			return
		} else {
			slog.Warn("Embedded Python runtime could not be extracted - falling back to a system interpreter", "err", err)
		}
	}
	// Fallback (and the dev-build path): a system interpreter.
	for _, name := range pythonCandidates() {
		if path, err := execLookPath(name); err == nil {
			exePath = path
			return
		}
	}
	resolveErr = fmt.Errorf("no Python interpreter available (no embedded runtime and no python3/python on PATH)")
}

func pythonCandidates() []string {
	if runtime.GOOS == "windows" {
		return []string{"python", "python3"}
	}
	return []string{"python3", "python"}
}

func execLookPath(name string) (string, error) { return exec.LookPath(name) }

// ensureExtracted unpacks the runtime archive into data/runtime/
// python-<version>, reusing an existing extraction.
func ensureExtracted(data []byte) (string, error) {
	targetDir := filepath.Join(InstallDir(), "python-"+runtimeIdentifier())
	marker := filepath.Join(targetDir, ".ready")
	if _, err := os.Stat(marker); err == nil {
		return targetDir, nil
	}
	if err := os.RemoveAll(targetDir); err != nil {
		return "", err
	}
	gz, err := gzip.NewReader(bytes.NewReader(data))
	if err != nil {
		return "", err
	}
	if err := extractTar(gz, targetDir); err != nil {
		return "", err
	}
	// First run extracts ~60MB; a marker file avoids redoing it.
	if err := os.WriteFile(marker, []byte(runtimeIdentifier()), 0o644); err != nil {
		return "", err
	}
	return targetDir, nil
}

// extractTar unpacks a python-build-standalone install_only archive. It
// guards against path traversal in the archive (no ".." elements) and
// makes the interpreter binaries executable.
func extractTar(gz *gzip.Reader, targetDir string) error {
	tr := tar.NewReader(gz)
	for {
		header, err := tr.Next()
		if err == io.EOF {
			return nil
		}
		if err != nil {
			return err
		}
		name := header.Name
		if parts := strings.SplitN(name, "/", 2); len(parts) == 2 && parts[0] == "python" {
			// install_only archives root everything under python/
			name = parts[1]
		} else if !strings.Contains(name, "/") {
			continue
		}
		clean := filepath.Clean(name)
		if strings.HasPrefix(clean, "..") || filepath.IsAbs(clean) {
			continue
		}
		dest := filepath.Join(targetDir, clean)
		switch header.Typeflag {
		case tar.TypeDir:
			if err := os.MkdirAll(dest, 0o755); err != nil {
				return err
			}
		case tar.TypeReg:
			if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
				return err
			}
			// Bound file size so a malformed archive cannot fill a disk.
			if header.Size > 512<<20 {
				return fmt.Errorf("archive entry %s too large", name)
			}
			out, err := os.OpenFile(dest, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, fileMode(header.Mode))
			if err == nil {
				if _, err := io.Copy(out, tr); err != nil {
					out.Close()
					return err
				}
				out.Close()
			} else {
				return err
			}
		case tar.TypeSymlink:
			// entries like bin/python3 -> python3.12 keep interpreter
			// paths stable. Recreate them, but only when the target
			// stays inside the extraction directory. (Symlink entries
			// may also arrive before their parent directory.)
			target := filepath.Clean(header.Linkname)
			if filepath.IsAbs(target) || strings.HasPrefix(target, ".") {
				continue
			}
			if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
				return err
			}
			os.Remove(dest)
			if err := os.Symlink(target, dest); err != nil {
				return err
			}
		}
	}
}

func fileMode(mode int64) os.FileMode {
	m := os.FileMode(mode & 0o777)
	if m == 0 {
		m = 0o644
	}
	return m
}

// pythonExecutable points at the interpreter inside the extracted
// install: bin/python3 on Unix, python.exe on Windows.
func pythonExecutable(dir string) string {
	if runtime.GOOS == "windows" {
		return filepath.Join(dir, "python.exe")
	}
	// install_only extracts make target dir itself the prefix: bin/ sits
	// directly under it.
	for _, rel := range []string{"bin/python3", "bin/python"} {
		if _, err := os.Stat(filepath.Join(dir, rel)); err == nil {
			return filepath.Join(dir, rel)
		}
	}
	return filepath.Join(dir, "bin/python3")
}

// runtimeIdentifier distinguishes extraction dirs across OS/arch.
func runtimeIdentifier() string {
	arch := runtime.GOARCH
	switch runtime.GOOS {
	case "windows":
		return "windows_" + arch
	case "darwin":
		return "macos_" + arch
	default:
		return "linux_" + arch
	}
}
