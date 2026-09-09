// Package web serves the embedded frontend over HTTP with the same
// behaviours as the Python server: gzip when accepted, cache-busting
// headers on static files, and a strict path-traversal guard.
package web

import (
	"io/fs"
	"net/http"
	"path"
	"strconv"
	"strings"

	assets "launchcontrol"
	"launchcontrol/internal/compress"
)

// mimeFallbacks cover the types used by the frontend. mime.TypeByExtension
// can return platform-dependent results (and nothing on some systems), so
// the frontend's known extensions are pinned here.
var mimeFallbacks = map[string]string{
	".html":  "text/html",
	".css":   "text/css",
	".js":    "text/javascript",
	".mjs":   "text/javascript",
	".json":  "application/json",
	".svg":   "image/svg+xml",
	".png":   "image/png",
	".jpg":   "image/jpeg",
	".ico":   "image/x-icon",
	".woff":  "font/woff",
	".woff2": "font/woff2",
	".ttf":   "font/ttf",
	".map":   "application/json",
}

func mimeFor(name string) string {
	if t := mimeFallbacks[strings.ToLower(path.Ext(name))]; t != "" {
		return t
	}
	return "application/octet-stream"
}

// IndexHandler serves the SPA shell at / and /index.html.
func IndexHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		writeMaybeGzipped(w, r, "index.html", "text/html", assets.IndexHTML())
	}
}

// StaticHandler serves files from the embedded static/ tree under /static/.
func StaticHandler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		rel := strings.TrimPrefix(r.URL.Path, "/static/")
		rel = path.Clean("/" + rel)[1:] // strip any traversal attempts
		if rel == "" || rel == "." {
			http.NotFound(w, r)
			return
		}

		data, err := fs.ReadFile(assets.Static(), rel)
		if err != nil {
			http.NotFound(w, r)
			return
		}

		ctype := mimeFor(rel)
		w.Header().Set("Cache-Control", "no-cache")
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Content-Type", ctype)
		writeMaybeGzipped(w, r, "static/"+rel, ctype, data)
	})
}

func writeMaybeGzipped(w http.ResponseWriter, r *http.Request, key, contentType string, body []byte) {
	if compress.WantsGzip(r.Header.Get("Accept-Encoding")) &&
		compress.ShouldCompress(contentType, len(body)) {
		body = compress.GzipCached(key, body)
		w.Header().Set("Content-Encoding", "gzip")
		w.Header().Set("Vary", "Accept-Encoding")
	}

	w.Header().Set("Content-Length", strconv.Itoa(len(body)))
	// Response-body write errors mean the client hung up; nothing to do.
	// #nosec G705 -- body is embedded asset content, served with a fixed
	// Content-Type, and the requested rel path was cleaned above.
	_, _ = w.Write(body)
}
