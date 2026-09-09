package compress

import (
	"bytes"
	"compress/gzip"
	"io"
	"testing"
)

func TestWantsGzip(t *testing.T) {
	cases := []struct {
		accept string
		want   bool
	}{
		{"gzip", true},
		{"GZIP", true},
		{"gzip, deflate, br", true},
		{"br, GZip", true},
		{"", false},
		{"deflate", false},
		{"deflate, br", false},
		{"identity", false},
	}

	for _, c := range cases {
		if got := WantsGzip(c.accept); got != c.want {
			t.Errorf("WantsGzip(%q) = %v, want %v", c.accept, got, c.want)
		}
	}
}

func TestShouldCompress(t *testing.T) {
	cases := []struct {
		contentType string
		size        int
		want        bool
	}{
		// Just below and exactly at the size floor.
		{"text/html", 1023, false},
		{"text/html", 1024, true},

		// Parameters and casing must not matter.
		{"text/html; charset=utf-8", 5000, true},
		{"TEXT/HTML", 5000, true},
		{"Application/JSON; charset=utf-8", 5000, true},

		// Non-compressible types are never compressed.
		{"image/png", 5000, false},
		{"application/octet-stream", 5000, false},
		{"", 5000, false},
	}

	for _, c := range cases {
		if got := ShouldCompress(c.contentType, c.size); got != c.want {
			t.Errorf("ShouldCompress(%q, %d) = %v, want %v", c.contentType, c.size, got, c.want)
		}
	}
}

func TestGzipBytesProducesValidGzip(t *testing.T) {
	body := []byte("the quick brown fox jumps over the lazy dog")

	gz := GzipBytes(body)

	// A gzip stream starts with the 1f 8b magic bytes.
	if len(gz) < 2 || gz[0] != 0x1f || gz[1] != 0x8b {
		t.Fatalf("output is not gzip: first bytes %x", gz[:2])
	}

	r, err := gzip.NewReader(bytes.NewReader(gz))
	if err != nil {
		t.Fatalf("gzip.NewReader: %v", err)
	}
	got, err := io.ReadAll(r)
	if err != nil {
		t.Fatalf("decompress: %v", err)
	}
	if err := r.Close(); err != nil {
		t.Fatalf("reader close: %v", err)
	}

	if !bytes.Equal(got, body) {
		t.Fatalf("decompressed = %q, want %q", got, body)
	}
}

func TestGzipCachedReusesAndRecompresses(t *testing.T) {
	// Unique keys keep tests independent of whatever the cache already
	// holds from other runs in the same process.
	body := bytes.Repeat([]byte("payload-"), 300)

	first := GzipCached("test:key-a", body)
	second := GzipCached("test:key-a", body)

	if !bytes.Equal(first, second) {
		t.Error("second call with unchanged content must return the cached bytes")
	}

	// Same key, different content: the fingerprint changes so the
	// body must be recompressed (and decompress to the new body).
	changed := bytes.Repeat([]byte("changed!"), 300)
	third := GzipCached("test:key-a", changed)

	if bytes.Equal(third, first) {
		t.Error("changed content must produce different compressed bytes")
	}

	r, err := gzip.NewReader(bytes.NewReader(third))
	if err != nil {
		t.Fatalf("gzip.NewReader: %v", err)
	}
	got, err := io.ReadAll(r)
	if err != nil {
		t.Fatalf("decompress: %v", err)
	}
	if !bytes.Equal(got, changed) {
		t.Fatalf("recompressed body decompressed to %q, want the changed body", got)
	}
}

func TestNormalizeType(t *testing.T) {
	cases := []struct {
		in   string
		want string
	}{
		{"text/html; charset=utf-8", "text/html"},
		{"text/html;charset=UTF-8", "text/html"},
		{"  TEXT/HTML  ", "text/html"},
		{"Application/JSON", "application/json"},
		{"text/html", "text/html"},
		{"", ""},
	}

	for _, c := range cases {
		if got := NormalizeType(c.in); got != c.want {
			t.Errorf("NormalizeType(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}
