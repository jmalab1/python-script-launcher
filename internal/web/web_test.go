package web

import (
	"bytes"
	"compress/gzip"
	"io"
	"io/fs"
	"net/http/httptest"
	"strconv"
	"testing"

	assets "launchcontrol"
)

// decompressGzipBody inflates a gzipped response body so tests can
// compare it against the original asset bytes.
func decompressGzipBody(t *testing.T, body []byte) []byte {
	t.Helper()
	r, err := gzip.NewReader(bytes.NewReader(body))
	if err != nil {
		t.Fatalf("gzip.NewReader: %v", err)
	}
	out, err := io.ReadAll(r)
	if err != nil {
		t.Fatalf("decompress: %v", err)
	}
	if err := r.Close(); err != nil {
		t.Fatalf("reader close: %v", err)
	}
	return out
}

func TestIndexHandlerServesPlainHTML(t *testing.T) {
	req := httptest.NewRequest("GET", "/", nil)
	rec := httptest.NewRecorder()

	IndexHandler()(rec, req)

	res := rec.Result()
	if res.StatusCode != 200 {
		t.Fatalf("status = %d, want 200", res.StatusCode)
	}
	if got := res.Header.Get("Content-Type"); got != "text/html" {
		t.Errorf("Content-Type = %q, want text/html", got)
	}
	if got := res.Header.Get("Content-Encoding"); got != "" {
		t.Errorf("Content-Encoding = %q, want none without Accept-Encoding", got)
	}

	body, err := io.ReadAll(res.Body)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(body, assets.IndexHTML()) {
		t.Error("plain response body must equal the embedded index.html")
	}
	if got := res.Header.Get("Content-Length"); got != strconv.Itoa(len(assets.IndexHTML())) {
		t.Errorf("Content-Length = %q, want %d", got, len(assets.IndexHTML()))
	}
}

func TestIndexHandlerServesGzipWhenAccepted(t *testing.T) {
	// index.html is bigger than the 1KB compress floor.
	if len(assets.IndexHTML()) <= 1024 {
		t.Skipf("embedded index.html is only %d bytes; gzip test needs >1024", len(assets.IndexHTML()))
	}

	req := httptest.NewRequest("GET", "/index.html", nil)
	req.Header.Set("Accept-Encoding", "gzip")
	rec := httptest.NewRecorder()

	IndexHandler()(rec, req)

	res := rec.Result()
	if got := res.Header.Get("Content-Encoding"); got != "gzip" {
		t.Fatalf("Content-Encoding = %q, want gzip", got)
	}
	if got := res.Header.Get("Vary"); got != "Accept-Encoding" {
		t.Errorf("Vary = %q, want Accept-Encoding", got)
	}
	if got := res.Header.Get("Content-Type"); got != "text/html" {
		t.Errorf("Content-Type = %q, want text/html", got)
	}

	body, err := io.ReadAll(res.Body)
	if err != nil {
		t.Fatal(err)
	}
	if got := res.Header.Get("Content-Length"); got != strconv.Itoa(len(body)) {
		t.Errorf("Content-Length = %q, want %d", got, len(body))
	}
	if got := decompressGzipBody(t, body); !bytes.Equal(got, assets.IndexHTML()) {
		t.Error("decompressed body must equal the embedded index.html")
	}
}

func TestStaticHandlerServesEmbeddedFile(t *testing.T) {
	rel := "js/app.js"
	want, err := fs.ReadFile(assets.Static(), rel)
	if err != nil {
		t.Fatalf("test assumes static/%s is embedded: %v", rel, err)
	}

	req := httptest.NewRequest("GET", "/static/"+rel, nil)
	rec := httptest.NewRecorder()

	StaticHandler().ServeHTTP(rec, req)

	res := rec.Result()
	if res.StatusCode != 200 {
		t.Fatalf("status = %d, want 200", res.StatusCode)
	}
	if got := res.Header.Get("Content-Type"); got != "text/javascript" {
		t.Errorf("Content-Type = %q, want text/javascript", got)
	}
	if got := res.Header.Get("Cache-Control"); got != "no-cache" {
		t.Errorf("Cache-Control = %q, want no-cache", got)
	}
	if got := res.Header.Get("Access-Control-Allow-Origin"); got != "*" {
		t.Errorf("Access-Control-Allow-Origin = %q, want *", got)
	}

	body, err := io.ReadAll(res.Body)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(body, want) {
		t.Error("body must equal the embedded static file")
	}
	if got := res.Header.Get("Content-Length"); got != strconv.Itoa(len(want)) {
		t.Errorf("Content-Length = %q, want %d", got, len(want))
	}
}

func TestStaticHandlerGzipsLargeJSWhenAccepted(t *testing.T) {
	rel := "js/app.js"
	want, err := fs.ReadFile(assets.Static(), rel)
	if err != nil {
		t.Fatalf("test assumes static/%s is embedded: %v", rel, err)
	}
	if len(want) <= 1024 {
		t.Skipf("static/%s is only %d bytes; gzip test needs >1024", rel, len(want))
	}

	req := httptest.NewRequest("GET", "/static/"+rel, nil)
	req.Header.Set("Accept-Encoding", "gzip")
	rec := httptest.NewRecorder()

	StaticHandler().ServeHTTP(rec, req)

	res := rec.Result()
	if got := res.Header.Get("Content-Encoding"); got != "gzip" {
		t.Fatalf("Content-Encoding = %q, want gzip", got)
	}
	if got := res.Header.Get("Vary"); got != "Accept-Encoding" {
		t.Errorf("Vary = %q, want Accept-Encoding", got)
	}

	body, err := io.ReadAll(res.Body)
	if err != nil {
		t.Fatal(err)
	}
	if got := decompressGzipBody(t, body); !bytes.Equal(got, want) {
		t.Error("decompressed body must equal the embedded static file")
	}
}

func TestStaticHandlerBlocksPathTraversal(t *testing.T) {
	cases := []struct {
		name string
		url  string
	}{
		{"parent climb to index", "/static/../index.html"},
		{"deep climb", "/static/../../index.html"},
		{"dotdot in the middle", "/static/js/../../../index.html"},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			req := httptest.NewRequest("GET", c.url, nil)
			rec := httptest.NewRecorder()

			StaticHandler().ServeHTTP(rec, req)

			// The cleaned rel path lands on "index.html", which does
			// not exist under static/ — and must never fall back to
			// the real index page.
			if rec.Result().StatusCode != 404 {
				t.Fatalf("status = %d, want 404", rec.Result().StatusCode)
			}
			if bytes.Contains(rec.Body.Bytes(), assets.IndexHTML()) {
				t.Error("traversal response must not contain index.html content")
			}
		})
	}
}

func TestStaticHandlerCleansButServesRealFile(t *testing.T) {
	// Redundant segments that clean away are fine when the target is a
	// real static file.
	rel := "js/app.js"
	want, err := fs.ReadFile(assets.Static(), rel)
	if err != nil {
		t.Fatalf("test assumes static/%s is embedded: %v", rel, err)
	}

	req := httptest.NewRequest("GET", "/static/js/../js/app.js", nil)
	rec := httptest.NewRecorder()

	StaticHandler().ServeHTTP(rec, req)

	if rec.Result().StatusCode != 200 {
		t.Fatalf("status = %d, want 200", rec.Result().StatusCode)
	}
	body, err := io.ReadAll(rec.Result().Body)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(body, want) {
		t.Error("cleaned path must serve the real static file")
	}
}

func TestStaticHandlerMissingFile(t *testing.T) {
	req := httptest.NewRequest("GET", "/static/js/no-such-file.js", nil)
	rec := httptest.NewRecorder()

	StaticHandler().ServeHTTP(rec, req)

	if rec.Result().StatusCode != 404 {
		t.Fatalf("status = %d, want 404", rec.Result().StatusCode)
	}
}

func TestStaticHandlerEmptyRelPath(t *testing.T) {
	cases := []string{"/static/", "/static"}

	for _, url := range cases {
		req := httptest.NewRequest("GET", url, nil)
		rec := httptest.NewRecorder()

		StaticHandler().ServeHTTP(rec, req)

		if rec.Result().StatusCode != 404 {
			t.Errorf("GET %s: status = %d, want 404", url, rec.Result().StatusCode)
		}
	}
}

func TestMimeForKnownAndUnknownExtensions(t *testing.T) {
	for ext, want := range mimeFallbacks {
		got := mimeFor("file" + ext)
		if got != want {
			t.Errorf("mimeFor(\"file%s\") = %q, want %q", ext, got, want)
		}
	}

	// Extension case must not matter, and unknown types fall back to a
	// safe generic type.
	if got := mimeFor("file.JS"); got != "text/javascript" {
		t.Errorf("mimeFor(\"file.JS\") = %q, want text/javascript", got)
	}
	if got := mimeFor("file.unknownext"); got != "application/octet-stream" {
		t.Errorf("mimeFor unknown ext = %q, want application/octet-stream", got)
	}
	if got := mimeFor("noext"); got != "application/octet-stream" {
		t.Errorf("mimeFor(\"noext\") = %q, want application/octet-stream", got)
	}
}
