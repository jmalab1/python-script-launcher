package api

import (
	"log/slog"
	"os"
	"os/user"
	"path/filepath"
	"sort"
	"strings"

	"launchcontrol/internal/config"
	"launchcontrol/internal/ordjson"
	"launchcontrol/internal/store"
)

func homeDir() string {
	if u, err := user.Current(); err == nil && u.HomeDir != "" {
		return u.HomeDir
	}
	return "."
}

// mustLoad is the list endpoint's tolerant load: the Python handlers
// let storage errors bubble into a 500, so we log and return nothing.
func mustLoad(db *store.DB, collection string) []*ordjson.OMap {
	items, err := db.Load(collection)
	if err != nil {
		slog.Error("Cannot load collection", "collection", collection, "err", err)
		return nil
	}
	return items
}

// isPythonScript reports whether a path ends in .py or .pyw.
func isPythonScript(path string) bool {
	return config.PythonExtensions[strings.ToLower(filepath.Ext(path))]
}

// BrowseDirectory is the /api/browse explorer: it lists a directory's
// contents (with a ".." row, or drives at a filesystem root) and can
// verify a selected Python script. Port of filesystem.browse_directory.
//
// The path comes from the request and is intentionally unrestricted: the
// explorer's job is to let the local user browse the whole filesystem to
// pick their scripts (the app serves 127.0.0.1 only), matching the
// Python original. So gosec's path-traversal taint findings here are a
// design choice, not a bug — see the G703 markers below.
func (a *API) BrowseDirectory(dirPath string) *ordjson.OMap {
	expanded := dirPath
	if expanded == "~" || strings.HasPrefix(expanded, "~/") {
		expanded = filepath.Join(homeDir(), strings.TrimPrefix(strings.TrimPrefix(expanded, "~"), "/"))
	}
	abs, err := filepath.Abs(expanded)
	if err == nil {
		if resolved, lerr := filepath.EvalSymlinks(abs); lerr == nil {
			abs = resolved
		}
	}

	// #nosec G703 -- Root-browsing is the explorer's documented purpose.
	info, err := os.Stat(abs)
	if err != nil {
		return ordjson.New().Set("error", "Path does not exist: "+abs)
	}

	if !info.IsDir() {
		if !isPythonScript(abs) {
			return ordjson.New().Set("error", "\""+filepath.Base(abs)+"\" is not a Python script (.py or .pyw)")
		}
		return ordjson.New().
			Set("path", filepath.Dir(abs)).
			Set("selected_file", ordjson.New().
				Set("name", filepath.Base(abs)).
				Set("path", abs).
				Set("is_dir", false)).
			Set("entries", []any{})
	}

	entries := []any{}
	if filepath.Dir(abs) != abs {
		entries = append(entries, ordjson.New().
			Set("name", "..").
			Set("path", filepath.Dir(abs)).
			Set("is_dir", true))
	} else {
		entries = append(entries, listDrives()...)
	}

	dirEntries, err := os.ReadDir(abs)
	if err != nil {
		return ordjson.New().Set("error", "Permission denied: "+abs)
	}

	names := make([]string, 0, len(dirEntries))
	for _, e := range dirEntries {
		names = append(names, e.Name())
	}

	sort.Strings(names)
	for _, name := range names {
		itemPath := filepath.Join(abs, name)
		isDir := false
		// #nosec G703 -- Root-browsing is the explorer's documented purpose.
		if st, err := os.Stat(itemPath); err == nil {
			isDir = st.IsDir()
		}
		entries = append(entries, ordjson.New().
			Set("name", name).
			Set("path", itemPath).
			Set("is_dir", isDir))
	}
	return ordjson.New().Set("path", abs).Set("entries", entries)
}

// ScriptExists backs the profile editor's live path validation. Like
// BrowseDirectory, the path is intentionally user-supplied.
func (a *API) ScriptExists(scriptPath string) *ordjson.OMap {
	exists := false
	if scriptPath != "" {
		// #nosec G703 -- Root-browsing is the explorer's documented purpose.
		if info, err := os.Stat(scriptPath); err == nil && !info.IsDir() {
			exists = true
		}
	}
	return ordjson.New().Set("exists", exists)
}
