// Package compress provides on-the-fly gzip for text responses, mirroring
// the Python implementation: only compress when the client accepts gzip,
// the content type is compressible and the body is big enough to be worth
// the CPU. Static files get an in-memory gzip cache keyed by (mtime, size)
// so repeated requests don't re-compress; embedded files use a cache keyed
// by content hash since they never change.
package compress

import (
	"bytes"
	"compress/gzip"
	"hash/fnv"
	"net/textproto"
	"strings"
	"sync"
)

var compressible = map[string]bool{
	"text/html":             true,
	"text/css":              true,
	"text/javascript":       true,
	"application/javascript": true,
	"application/json":      true,
}

const minSize = 1024
const level = 6

// WantsGzip reports whether the Accept-Encoding header includes gzip.
func WantsGzip(acceptEncoding string) bool {
	return strings.Contains(strings.ToLower(acceptEncoding), "gzip")
}

// ShouldCompress reports whether a body of the given type and size is
// worth compressing.
func ShouldCompress(contentType string, size int) bool {
	base := strings.TrimSpace(strings.ToLower(strings.Split(contentType, ";")[0]))
	return size >= minSize && compressible[base]
}

// GzipBytes compresses body at the standard level.
func GzipBytes(body []byte) []byte {
	var buf bytes.Buffer
	w, _ := gzip.NewWriterLevel(&buf, level)
	w.Write(body)
	w.Close()
	return buf.Bytes()
}

type cacheEntry struct {
	key  uint64
	data []byte
}

var (
	cache     = map[string]cacheEntry{}
	cacheLock sync.Mutex
)

// GzipCached compresses body once per key (e.g. "static/js/app.js"),
// re-compressing only when the fingerprint changes. For embedded assets
// the fingerprint is a content hash, so the cache stays valid forever.
func GzipCached(key string, body []byte) []byte {
	h := fnv.New64a()
	h.Write(body)
	stamp := h.Sum64()
	cacheLock.Lock()
	cached, ok := cache[key]
	cacheLock.Unlock()
	if ok && cached.key == stamp {
		return cached.data
	}
	data := GzipBytes(body)
	cacheLock.Lock()
	cache[key] = cacheEntry{key: stamp, data: data}
	cacheLock.Unlock()
	return data
}

// NormalizeType trims parameters ("text/html; charset=utf-8" ->
// "text/html") in the same casing style the Python code compared.
func NormalizeType(contentType string) string {
	return textproto.TrimString(strings.ToLower(strings.Split(contentType, ";")[0]))
}
