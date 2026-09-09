// Package api implements the HTTP surface, a route-by-route port of the
// Python server.py and launcher/api modules so the existing frontend
// keeps working unchanged.
package api

import (
	"io"
	"log/slog"
	"net/http"
	"strconv"
	"strings"

	"launchcontrol/internal/compress"
	"launchcontrol/internal/ordjson"
	"launchcontrol/internal/runner"
	"launchcontrol/internal/scheduler"
	"launchcontrol/internal/store"
	"launchcontrol/internal/web"
)

// API serves every /api route plus the embedded frontend.
type API struct {
	DB      *store.DB
	Runs    *runner.Manager
	Sched   *scheduler.Scheduler
	DataDir string
	LogPath string // the server log the Logs panel tails
}

// New wires an API server from its collaborators.
func New(db *store.DB, runs *runner.Manager, sched *scheduler.Scheduler, dataDir, logPath string) *API {
	return &API{DB: db, Runs: runs, Sched: sched, DataDir: dataDir, LogPath: logPath}
}

// Handler returns the top-level HTTP handler.
func (a *API) Handler() http.Handler {
	mux := http.NewServeMux()
	// Go's ServeMux registers "/" as a catch-all; the api router decides
	// method and shape itself, mirroring the Python if/elif chains.
	mux.HandleFunc("/", a.route)
	return mux
}

// ServeHTTP implements http.Handler by delegating to the router.
func (a *API) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	a.route(w, r)
}

func (a *API) route(w http.ResponseWriter, r *http.Request) {
	path := r.URL.Path
	defer func() {
		// The Python server catches handler exceptions and answers 500;
		// recover does the same so a buggy handler cannot kill a
		// request with the default panic response alone.
		if rec := recover(); rec != nil {
			slog.Error("Panic handling request", "path", path, "panic", rec)
			http.Error(w, "Internal Server Error", http.StatusInternalServerError)
		}
	}()

	switch {
	case path == "/" || path == "/index.html":
		if r.Method != http.MethodGet {
			http.NotFound(w, r)
			return
		}
		web.IndexHandler()(w, r)
		return
	case path == "/static/" || strings.HasPrefix(path, "/static/"):
		if r.Method != http.MethodGet {
			http.NotFound(w, r)
			return
		}
		web.StaticHandler().ServeHTTP(w, r)
		return
	}

	if strings.HasPrefix(path, "/api/") {
		switch r.Method {
		case http.MethodGet:
			a.get(w, r, path)
		case http.MethodPost:
			a.post(w, r, path)
		case http.MethodDelete:
			a.delete(w, r, path)
		default:
			http.NotFound(w, r)
		}
		return
	}
	http.NotFound(w, r)
}

// get mirrors do_GET's dispatch order.
func (a *API) get(w http.ResponseWriter, r *http.Request, path string) {
	q := r.URL.Query()
	switch {
	case path == "/api/browse":
		dirPath := q.Get("path")
		if dirPath == "" {
			dirPath = homeDir()
		}
		a.writeJSON(w, r, a.BrowseDirectory(dirPath), http.StatusOK)

	case path == "/api/filedialog":
		// The native file-picker (Tk/zenity/kdialog) was dropped in the
		// Go port; the /api/browse explorer covers it. The response
		// shape matches the Python "no dialog available" error so the
		// frontend degrades gracefully.
		a.writeJSON(w, r, response("error", "No file dialog available"), http.StatusOK)

	case path == "/api/script_exists":
		a.writeJSON(w, r, a.ScriptExists(q.Get("path")), http.StatusOK)

	case path == "/api/profiles":
		a.writeJSONRecords(w, r, mustLoad(a.DB, store.ColProfiles))

	case path == "/api/workflows":
		a.writeJSONRecords(w, r, mustLoad(a.DB, store.ColWorkflows))

	case path == "/api/schedules":
		a.writeJSONRecords(w, r, a.listSchedules())

	case path == "/api/schedules/preview":
		result, status := a.SchedulePreview(q.Get("cron"))
		a.writeJSON(w, r, result, status)

	case path == "/api/history":
		a.writeJSON(w, r, a.historyList(r), http.StatusOK)

	case strings.HasPrefix(path, "/api/history/"):
		entryKey := lastSegment(path)
		entry := a.historyDetail(entryKey, q.Get("type"))
		if entry == nil {
			a.writeJSON(w, r, response("error", "Not found"), http.StatusNotFound)
			return
		}
		a.writeJSON(w, r, entry, http.StatusOK)

	case path == "/api/audit":
		a.writeJSON(w, r, a.auditList(r), http.StatusOK)

	case strings.HasPrefix(path, "/api/audit/"):
		entryID := lastSegment(path)
		entry := a.auditDetail(entryID)
		if entry == nil {
			a.writeJSON(w, r, response("error", "Not found"), http.StatusNotFound)
			return
		}
		a.writeJSON(w, r, entry, http.StatusOK)

	case path == "/api/runs":
		a.writeJSON(w, r, a.Runs.PollAll(), http.StatusOK)

	case strings.HasPrefix(path, "/api/runs/"):
		runID := lastSegment(path)
		result := a.Runs.Poll(runID)
		if result == nil {
			a.writeJSON(w, r, response("error", "Run not found"), http.StatusNotFound)
			return
		}
		a.writeJSON(w, r, result, http.StatusOK)

	case path == "/api/logs":
		a.writeJSON(w, r, a.TailLogs(q.Get("lines"), nonEmpty(q.Get("after"))), http.StatusOK)

	default:
		http.Error(w, "Not Found", http.StatusNotFound)
	}
}

// post mirrors do_POST's dispatch order.
func (a *API) post(w http.ResponseWriter, r *http.Request, path string) {
	body, err := io.ReadAll(io.LimitReader(r.Body, 10<<20))
	if err != nil {
		a.writeJSON(w, r, response("error", "Invalid JSON"), http.StatusBadRequest)
		return
	}
	data := ordjson.New()
	if len(body) > 0 {
		parsed, perr := ordjson.Parse(body)
		if perr != nil {
			a.writeJSON(w, r, response("error", "Invalid JSON"), http.StatusBadRequest)
			return
		}
		if m, ok := parsed.(*ordjson.OMap); ok {
			data = m
		}
	}

	switch {
	case path == "/api/profiles":
		a.writeJSON(w, r, a.ProfileCreate(data), http.StatusOK)

	case path == "/api/profiles/reorder":
		a.writeJSON(w, r, a.ProfileReorder(data), http.StatusOK)

	case hasSuffixPath(path, "/api/profiles/", "/duplicate"):
		dup, found := a.ProfileDuplicate(trimSuffixPath(path, "/api/profiles/", "/duplicate"))
		if !found {
			a.writeJSON(w, r, response("error", "Not found"), http.StatusNotFound)
			return
		}
		a.writeJSON(w, r, dup, http.StatusOK)

	case hasSuffixPath(path, "/api/profiles/", "/restore"):
		restored, found := a.ProfileRestore(trimSuffixPath(path, "/api/profiles/", "/restore"))
		if !found {
			a.writeJSON(w, r, response("error", "Not found"), http.StatusNotFound)
			return
		}
		a.writeJSON(w, r, restored, http.StatusOK)

	case path == "/api/workflows":
		a.writeJSON(w, r, a.WorkflowCreate(data), http.StatusOK)

	case path == "/api/workflows/reorder":
		a.writeJSON(w, r, a.WorkflowReorder(data), http.StatusOK)

	case hasSuffixPath(path, "/api/workflows/", "/duplicate"):
		dup, found := a.WorkflowDuplicate(trimSuffixPath(path, "/api/workflows/", "/duplicate"))
		if !found {
			a.writeJSON(w, r, response("error", "Not found"), http.StatusNotFound)
			return
		}
		a.writeJSON(w, r, dup, http.StatusOK)

	case hasSuffixPath(path, "/api/workflows/", "/restore"):
		restored, found := a.WorkflowRestore(trimSuffixPath(path, "/api/workflows/", "/restore"))
		if !found {
			a.writeJSON(w, r, response("error", "Not found"), http.StatusNotFound)
			return
		}
		a.writeJSON(w, r, restored, http.StatusOK)

	case hasSuffixPath(path, "/api/schedules/", "/duplicate"):
		dup, apiErr := a.ScheduleDuplicate(trimSuffixPath(path, "/api/schedules/", "/duplicate"))
		if apiErr != nil {
			a.writeJSON(w, r, apiErr, http.StatusNotFound)
			return
		}
		a.writeJSON(w, r, dup, http.StatusOK)

	case hasSuffixPath(path, "/api/schedules/", "/restore"):
		restored, apiErr := a.ScheduleRestore(trimSuffixPath(path, "/api/schedules/", "/restore"))
		if apiErr != nil {
			a.writeJSON(w, r, apiErr, http.StatusNotFound)
			return
		}
		a.writeJSON(w, r, restored, http.StatusOK)

	case path == "/api/schedules":
		sched, apiErr := a.ScheduleCreate(data)
		if apiErr != nil {
			a.writeJSON(w, r, apiErr, http.StatusBadRequest)
			return
		}
		a.writeJSON(w, r, sched, http.StatusOK)

	case hasSuffixPath(path, "/api/schedules/", "/toggle"):
		toggled, apiErr := a.ScheduleToggle(trimSuffixPath(path, "/api/schedules/", "/toggle"))
		if apiErr != nil {
			a.writeJSON(w, r, apiErr, http.StatusNotFound)
			return
		}
		a.writeJSON(w, r, toggled, http.StatusOK)

	case hasSuffixPath(path, "/api/schedules/", "/run_now"):
		result, apiErr := a.ScheduleRunNow(trimSuffixPath(path, "/api/schedules/", "/run_now"))
		if apiErr != nil {
			a.writeJSON(w, r, apiErr, http.StatusBadRequest)
			return
		}
		a.writeJSON(w, r, result, http.StatusOK)

	case path == "/api/history/bulk":
		a.writeJSON(w, r, a.HistoryBulkDelete(data), http.StatusOK)

	case path == "/api/run/profile":
		result, status := a.RunProfile(data)
		a.writeJSON(w, r, result, status)

	case path == "/api/run/workflow":
		result, status := a.RunWorkflow(data)
		a.writeJSON(w, r, result, status)

	case hasSuffixPath(path, "/api/runs/", "/cancel"):
		result, status := a.CancelRun(trimSuffixPath(path, "/api/runs/", "/cancel"))
		a.writeJSON(w, r, result, status)

	default:
		http.Error(w, "Not Found", http.StatusNotFound)
	}
}

// delete mirrors do_DELETE's dispatch order.
func (a *API) delete(w http.ResponseWriter, r *http.Request, path string) {
	switch {
	case hasSuffixPath(path, "/api/profiles/", "/permanent"):
		a.writeJSON(w, r, a.ProfilePermanentDelete(trimSuffixPath(path, "/api/profiles/", "/permanent")), http.StatusOK)

	case strings.HasPrefix(path, "/api/profiles/"):
		a.writeJSON(w, r, a.ProfileDelete(lastSegment(path)), http.StatusOK)

	case hasSuffixPath(path, "/api/workflows/", "/permanent"):
		a.writeJSON(w, r, a.WorkflowPermanentDelete(trimSuffixPath(path, "/api/workflows/", "/permanent")), http.StatusOK)

	case strings.HasPrefix(path, "/api/workflows/"):
		a.writeJSON(w, r, a.WorkflowDelete(lastSegment(path)), http.StatusOK)

	case hasSuffixPath(path, "/api/schedules/", "/permanent"):
		_, apiErr := a.SchedulePermanentDelete(trimSuffixPath(path, "/api/schedules/", "/permanent"))
		if apiErr != nil {
			a.writeJSON(w, r, apiErr, http.StatusNotFound)
			return
		}
		a.writeJSON(w, r, response("ok", true), http.StatusOK)

	case strings.HasPrefix(path, "/api/schedules/"):
		result, apiErr := a.ScheduleDelete(lastSegment(path))
		if apiErr != nil {
			a.writeJSON(w, r, apiErr, http.StatusNotFound)
			return
		}
		a.writeJSON(w, r, result, http.StatusOK)

	case path == "/api/history":
		a.writeJSON(w, r, a.HistoryClear(), http.StatusOK)

	case strings.HasPrefix(path, "/api/history/"):
		a.writeJSON(w, r, a.HistoryDelete(lastSegment(path)), http.StatusOK)

	default:
		http.Error(w, "Not Found", http.StatusNotFound)
	}
}

// writeJSON serializes with ordjson (order- and literal-preserving) and
// gzips large responses when the client accepts it.
func (a *API) writeJSON(w http.ResponseWriter, r *http.Request, v any, status int) {
	body, err := ordjson.Marshal(v)
	if err != nil {
		slog.Error("Failed to serialize JSON response", "err", err)
		http.Error(w, "Internal Server Error", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	if compress.WantsGzip(r.Header.Get("Accept-Encoding")) && compress.ShouldCompress("application/json", len(body)) {
		body = compress.GzipBytes(body)
		w.Header().Set("Content-Encoding", "gzip")
		w.Header().Set("Vary", "Accept-Encoding")
	}
	w.Header().Set("Content-Length", strconv.Itoa(len(body)))
	w.WriteHeader(status)
	w.Write(body)
}

func (a *API) writeJSONRecords(w http.ResponseWriter, r *http.Request, records []*ordjson.OMap) {
	arr := make([]any, len(records))
	for i, rec := range records {
		arr[i] = rec
	}
	a.writeJSON(w, r, arr, http.StatusOK)
}

// --- small shared helpers ---

func response(key string, v any) *ordjson.OMap {
	return ordjson.New().Set(key, v)
}

func lastSegment(path string) string {
	for i := len(path) - 1; i >= 0; i-- {
		if path[i] == '/' {
			return path[i+1:]
		}
	}
	return path
}

func hasSuffixPath(path, prefix, suffix string) bool {
	return len(path) > len(prefix)+len(suffix) &&
		len(path) >= len(prefix)+len(suffix) &&
		path[:len(prefix)] == prefix && path[len(path)-len(suffix):] == suffix
}

func trimSuffixPath(path, prefix, suffix string) string {
	return path[len(prefix) : len(path)-len(suffix)]
}

func nonEmpty(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}
