package main

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// fakeReleaseServer serves a miniature python-build-standalone release:
// one platform archive plus its SHA256SUMS, backed by real gzip/tar
// bytes so the files that land in outDir are genuinely verifiable.
// With corrupt set, the published digest does not match the archive.
func fakeReleaseServer(t *testing.T, corrupt bool) *httptest.Server {
	t.Helper()

	// One asset per platform triple, all pointing at the same tiny
	// archive; the sums file lists every name with its digest.
	archive := buildTinyArchive(t)
	sum := sha256.Sum256(archive)
	digest := hex.EncodeToString(sum[:])
	if corrupt {
		digest = strings.Repeat("0", 64)
	}

	type relAsset struct {
		Name               string `json:"name"`
		BrowserDownloadURL string `json:"browser_download_url"`
	}
	var assets []relAsset
	var sumsLines []string
	for _, triple := range targets {
		name := fmt.Sprintf("cpython-3.12.7+20241016-%s-install_only.tar.gz", triple)
		assets = append(assets, relAsset{Name: name})
		sumsLines = append(sumsLines, fmt.Sprintf("%s  %s", digest, name))
	}
	assets = append(assets, relAsset{Name: "SHA256SUMS"})

	var baseURL string
	mux := http.NewServeMux()
	mux.HandleFunc("/repos/astral-sh/python-build-standalone/releases/latest", func(w http.ResponseWriter, r *http.Request) {
		body := struct {
			TagName string     `json:"tag_name"`
			Assets  []relAsset `json:"assets"`
		}{TagName: "20241016", Assets: assets}
		for i := range body.Assets {
			if body.Assets[i].Name == "SHA256SUMS" {
				body.Assets[i].BrowserDownloadURL = baseURL + "/SHA256SUMS"
			} else {
				body.Assets[i].BrowserDownloadURL = baseURL + "/" + body.Assets[i].Name
			}
		}
		w.Header().Set("Content-Type", "application/json")
		out, err := json.Marshal(body)
		if err != nil {
			t.Fatal(err)
		}
		_, _ = w.Write(out)
	})
	mux.HandleFunc("/SHA256SUMS", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintln(w, strings.Join(sumsLines, "\n"))
	})
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write(archive)
	})

	srv := httptest.NewServer(mux)
	baseURL = srv.URL
	return srv
}

// buildTinyArchive returns a valid gzip-compressed tar with one file.
func buildTinyArchive(t *testing.T) []byte {
	t.Helper()
	var buf bytes.Buffer
	gw := gzip.NewWriter(&buf)
	tw := tar.NewWriter(gw)
	if err := tw.WriteHeader(&tar.Header{Name: "python/bin/python3", Mode: 0o755, Size: 3}); err != nil {
		t.Fatal(err)
	}
	if _, err := tw.Write([]byte("hi\n")); err != nil {
		t.Fatal(err)
	}
	if err := tw.Close(); err != nil {
		t.Fatal(err)
	}
	if err := gw.Close(); err != nil {
		t.Fatal(err)
	}
	return buf.Bytes()
}

func TestFetchAllDownloadsAndVerifies(t *testing.T) {
	srv := fakeReleaseServer(t, false)
	defer srv.Close()

	outDir := t.TempDir()
	if err := fetchAll(srv.URL, "latest", outDir); err != nil {
		t.Fatalf("fetchAll: %v", err)
	}

	// Every target must have landed as a file, each byte-identical to
	// the fake archive.
	archive := buildTinyArchive(t)
	for target := range targets {
		raw, err := os.ReadFile(filepath.Join(outDir, target+".tar.gz"))
		if err != nil {
			t.Fatalf("missing archive for %s: %v", target, err)
		}
		if !bytes.Equal(raw, archive) {
			t.Errorf("archive for %s does not match source bytes", target)
		}
	}
}

func TestFetchAllFailsOnChecksumMismatch(t *testing.T) {
	srv := fakeReleaseServer(t, true)
	defer srv.Close()

	if err := fetchAll(srv.URL, "latest", t.TempDir()); err == nil {
		t.Fatal("expected checksum mismatch error")
	}
}

func TestPickAssetMatchesTriple(t *testing.T) {
	assets := []asset{
		{Name: "cpython-3.12.7+20241016-x86_64-unknown-linux-gnu-install_only.tar.gz", BrowserDownloadURL: "u1"},
		{Name: "cpython-3.12.7+20241016-aarch64-unknown-linux-gnu-install_only.tar.gz", BrowserDownloadURL: "u2"},
		{Name: "cpython-3.13.0+20241016-x86_64-unknown-linux-gnu-install_only.tar.gz", BrowserDownloadURL: "u3"},
	}

	got, err := pickAsset(assets, "x86_64-unknown-linux-gnu")
	if err != nil {
		t.Fatal(err)
	}
	if got.BrowserDownloadURL != "u1" {
		t.Errorf("picked %s, want u1", got.Name)
	}

	if _, err := pickAsset(assets, "x86_64-apple-darwin"); err == nil {
		t.Error("expected error when no asset matches the triple")
	}
}

func TestLoadChecksumsParsesLines(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, "abc  one.tar.gz\n\ndef  *two.tar.gz\n")
	}))
	defer srv.Close()

	rel := &release{Assets: []asset{
		{Name: "SHA256SUMS", BrowserDownloadURL: srv.URL + "/sums"},
	}}
	checksums, err := loadChecksums(rel)
	if err != nil {
		t.Fatal(err)
	}
	if checksums["one.tar.gz"] != "abc" || checksums["two.tar.gz"] != "def" {
		t.Errorf("checksums = %v", checksums)
	}
}

func TestLoadChecksumsBadLineFails(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, "just-one-field\n")
	}))
	defer srv.Close()

	rel := &release{Assets: []asset{
		{Name: "SHA256SUMS", BrowserDownloadURL: srv.URL + "/sums"},
	}}
	if _, err := loadChecksums(rel); err == nil {
		t.Fatal("expected error for malformed sums line")
	}
}

func TestLoadChecksumsFailsWithoutAsset(t *testing.T) {
	if _, err := loadChecksums(&release{}); err == nil {
		t.Fatal("expected error when SHA256SUMS asset is missing")
	}
}
