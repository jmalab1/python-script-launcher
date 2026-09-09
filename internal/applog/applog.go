// Package applog wires logging to both stderr and a rotating
// data/server.log, matching the Python handler's behaviour: size-based
// rotation with timestamped backup names, pruned to backupCount copies.
package applog

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"
)

// RotatingWriter is an io.WriteCloser that rotates the active file when
// it exceeds maxSize bytes, naming backups <file>.<YYYY-MM-DD_HH-MM-SS>.
type RotatingWriter struct {
	mu          sync.Mutex
	path        string
	maxSize     int64
	backupCount int
	file        *os.File
	size        int64
}

var backupSuffix = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(-\d+)?$`)

// New opens (or creates) the log file.
func New(path string, maxSize int64, backupCount int) (*RotatingWriter, error) {
	if err := os.MkdirAll(filepath.Dir(path), 0o750); err != nil {
		return nil, err
	}

	// path is the caller-provided server log file (config.LogFile()),
	// not request input.
	f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600) // #nosec G304 -- internal log path
	if err != nil {
		return nil, err
	}

	info, err := f.Stat()
	var size int64
	if err == nil {
		size = info.Size()
	}
	return &RotatingWriter{path: path, maxSize: maxSize, backupCount: backupCount, file: f, size: size}, nil
}

// Write appends to the log, rotating first when the size cap is hit.
func (w *RotatingWriter) Write(p []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.maxSize > 0 && w.size+int64(len(p)) > w.maxSize {
		if err := w.rotateLocked(); err != nil {
			return 0, err
		}
	}

	n, err := w.file.Write(p)
	w.size += int64(n)
	return n, err
}

// Close shuts the file (and rotation) down.
func (w *RotatingWriter) Close() error {
	w.mu.Lock()
	defer w.mu.Unlock()
	return w.file.Close()
}

// rotateLocked closes the active file, renames it with a timestamp
// suffix (uniquified with -N when needed) and prunes the oldest
// backups. Because timestamped names accumulate, pruning runs after
// every rollover.
func (w *RotatingWriter) rotateLocked() error {
	_ = w.file.Close()
	stamp := time.Now().Format("2006-01-02_15-04-05")
	candidate := w.path + "." + stamp
	for n := 1; fileExists(candidate); n++ {
		candidate = fmt.Sprintf("%s.%s-%d", w.path, stamp, n)
	}

	if err := os.Rename(w.path, candidate); err != nil {
		// Keep writing to the same file if the rename failed.
		f, err2 := os.OpenFile(w.path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600) // #nosec G304 -- internal log path
		if err2 != nil {
			return err
		}
		w.file = f
		return nil
	}

	f, err := os.OpenFile(w.path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600) // #nosec G304 -- internal log path
	if err != nil {
		return err
	}
	w.file = f
	w.size = 0
	w.pruneLocked()
	return nil
}

func (w *RotatingWriter) pruneLocked() {
	base := filepath.Base(w.path)
	dir := filepath.Dir(w.path)
	entries, err := os.ReadDir(dir)
	if err != nil {
		return
	}

	var backups []string
	for _, e := range entries {
		name := e.Name()
		if strings.HasPrefix(name, base+".") && backupSuffix.MatchString(strings.TrimPrefix(name, base+".")) {
			backups = append(backups, name)
		}
	}
	sort.Strings(backups)
	excess := len(backups) - w.backupCount
	for i := 0; i < excess; i++ {
		// Old backups are best-effort pruned; a failed delete keeps a
		// file around but harms nothing.
		_ = os.Remove(filepath.Join(dir, backups[i]))
	}
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

// levelNames render the way Python's logging did, because the Logs
// panel highlights on those spellings.
func levelText(l slog.Level) string {
	switch {
	case l >= slog.LevelError:
		return "ERROR"
	case l >= slog.LevelWarn:
		return "WARNING"
	case l >= slog.LevelInfo:
		return "INFO"
	default:
		return "DEBUG"
	}
}

// Setup installs the root slog logger over a stderr+file mirror with
// the Python server's line format, and returns the file writer (nil
// when no file could be opened).
func Setup(path string, maxSize int64, backupCount int) *RotatingWriter {
	if err := os.MkdirAll(filepath.Dir(path), 0o750); err != nil {
		slog.Warn("Could not create data dir for logging", "err", err)
		return nil
	}

	rotator, err := New(path, maxSize, backupCount)
	if err != nil {
		slog.Warn("Could not open log file", "path", path, "err", err)
		return nil
	}

	out := io.MultiWriter(os.Stderr, rotator)
	slog.SetDefault(slog.New(&pythonStyleHandler{w: out}))
	return rotator
}

// pythonStyleHandler renders "2006-01-02 15:04:05 [LEVEL] message"
// exactly like the Python logging config, since the Logs panel's
// highlighting is tuned to that shape.
type pythonStyleHandler struct {
	w io.Writer
}

func (h *pythonStyleHandler) Enabled(context.Context, slog.Level) bool { return true }

func (h *pythonStyleHandler) Handle(_ context.Context, r slog.Record) error {
	var sb strings.Builder
	sb.WriteString(r.Time.Format("2006-01-02 15:04:05"))
	sb.WriteString(" [")
	sb.WriteString(levelText(r.Level))
	sb.WriteString("] ")
	sb.WriteString(r.Message)
	r.Attrs(func(a slog.Attr) bool {
		sb.WriteString(" " + a.Key + "=" + fmt.Sprint(a.Value))
		return true
	})
	sb.WriteString("\n")

	_, err := io.WriteString(h.w, sb.String())
	return err
}

func (h *pythonStyleHandler) WithAttrs([]slog.Attr) slog.Handler { return h }

func (h *pythonStyleHandler) WithGroup(string) slog.Handler { return h }
