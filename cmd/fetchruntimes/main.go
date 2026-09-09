// Command fetchruntimes downloads the CPython runtimes that release
// builds embed.
//
// For each target (see targets), the matching "install_only" archive
// from astral-sh/python-build-standalone is fetched, checksum-verified
// against the release's SHA256SUMS, and stored as
// build/runtimes/<target>.tar.gz. `make go-release` embeds one archive
// into each binary via -tags embedded; the Go program extracts it to
// data/runtime/ on first run.
//
// Run with:  go run ./cmd/fetchruntimes [--tag X]
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"

	"launchcontrol/internal/devtools"
)

const repo = "astral-sh/python-build-standalone"

// VERSION is the Python major.minor the archives must match.
const version = "3.12"

// targets maps the archive file name used by the Makefile
// (build/runtimes/<target>.tar.gz) to the platform triple in
// python-build-standalone release asset names.
var targets = map[string]string{
	"linux-amd64":   "x86_64-unknown-linux-gnu",
	"linux-arm64":   "aarch64-unknown-linux-gnu",
	"windows-amd64": "x86_64-pc-windows-msvc",
	"macos-amd64":   "x86_64-apple-darwin",
	"macos-arm64":   "aarch64-apple-darwin",
}

// release is the subset of the GitHub releases API response the tool
// reads.
type release struct {
	TagName string  `json:"tag_name"`
	Assets  []asset `json:"assets"`
}

type asset struct {
	Name               string `json:"name"`
	BrowserDownloadURL string `json:"browser_download_url"`
}

func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, "fetchruntimes:", err)
		os.Exit(1)
	}
}

func run(args []string) error {
	tag := flag.String("tag", "latest", "release tag (default: latest)")
	if err := flag.CommandLine.Parse(args); err != nil {
		return err
	}

	root, err := devtools.RepoRoot()
	if err != nil {
		return err
	}
	outDir := filepath.Join(root, "build", "runtimes")

	return fetchAll("https://api.github.com", *tag, outDir)
}

// fetchAll downloads one archive per target from the given release and
// verifies it against the release's SHA256SUMS. apiBase is where the
// GitHub API lives (split out so tests can point it at a local server).
func fetchAll(apiBase, tag, outDir string) error {
	rel, err := loadRelease(apiBase, tag)
	if err != nil {
		return err
	}
	fmt.Printf("release tag: %s\n", rel.TagName)

	checksums, err := loadChecksums(rel)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(outDir, 0o750); err != nil {
		return err
	}

	names := make([]string, 0, len(targets))
	for name := range targets {
		names = append(names, name)
	}
	sort.Strings(names)

	for _, target := range names {
		if err := fetchOne(rel, checksums, targets[target], filepath.Join(outDir, target+".tar.gz")); err != nil {
			return err
		}
	}

	fmt.Printf("done: %d archives in %s\n", len(targets), outDir)
	return nil
}

// loadRelease queries the GitHub API for the release, either the
// latest one or the given tag.
func loadRelease(apiBase, tag string) (*release, error) {
	url := apiBase + "/repos/" + repo + "/releases/latest"
	if tag != "latest" {
		url = apiBase + "/repos/" + repo + "/releases/tags/" + tag
	}

	var rel release
	if err := getJSON(url, &rel); err != nil {
		return nil, err
	}
	return &rel, nil
}

// loadChecksums turns the release's SHA256SUMS asset into a map from
// file name to hex digest. Lines look like "digest␣␣name"; a leading
// "*" on the name marks binary mode and is ignored.
func loadChecksums(rel *release) (map[string]string, error) {
	var sumsURL string
	for _, a := range rel.Assets {
		if a.Name == "SHA256SUMS" {
			sumsURL = a.BrowserDownloadURL
			break
		}
	}
	if sumsURL == "" {
		return nil, fmt.Errorf("no SHA256SUMS asset in release")
	}

	raw, err := download(sumsURL)
	if err != nil {
		return nil, err
	}
	defer raw.Close()

	body, err := io.ReadAll(raw)
	if err != nil {
		return nil, err
	}

	checksums := make(map[string]string)
	for _, line := range strings.Split(string(body), "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) != 2 {
			return nil, fmt.Errorf("bad SHA256SUMS line: %q", line)
		}
		checksums[strings.TrimPrefix(fields[1], "*")] = fields[0]
	}
	return checksums, nil
}

// pickAsset finds the install_only archive for the given platform
// triple among the release assets.
func pickAsset(assets []asset, triple string) (*asset, error) {
	// The triple is embedded literally (it may itself contain dashes,
	// e.g. x86_64-unknown-linux-gnu).
	pattern := regexp.MustCompile(
		`^cpython-` + regexp.QuoteMeta(version) + `\.\d+(\.\d+)?\+[^-]+-` +
			regexp.QuoteMeta(triple) + `-install_only\.tar\.gz$`)
	for i := range assets {
		if pattern.MatchString(assets[i].Name) {
			return &assets[i], nil
		}
	}

	names := make([]string, 0, len(assets))
	for _, a := range assets {
		names = append(names, a.Name)
	}
	sort.Strings(names)
	if len(names) > 8 {
		names = names[:8]
	}
	return nil, fmt.Errorf("no cpython %s install_only asset for %s; available: %s",
		version, triple, strings.Join(names, ", "))
}

// fetchOne downloads and verifies one archive and writes it to dest.
func fetchOne(rel *release, checksums map[string]string, triple, dest string) error {
	a, err := pickAsset(rel.Assets, triple)
	if err != nil {
		return err
	}
	expected := checksums[a.Name]
	if expected == "" {
		return fmt.Errorf("no checksum for %s", a.Name)
	}

	fmt.Printf("fetch %s -> %s\n", a.Name, filepath.Base(dest))
	data, err := func() ([]byte, error) {
		raw, err := download(a.BrowserDownloadURL)
		if err != nil {
			return nil, err
		}
		defer raw.Close()
		return io.ReadAll(raw)
	}()
	if err != nil {
		return err
	}

	got := sha256.Sum256(data)
	if hex.EncodeToString(got[:]) != expected {
		return fmt.Errorf("checksum mismatch for %s: %x != %s", a.Name, got, expected)
	}

	if err := os.WriteFile(dest, data, 0o600); err != nil {
		return err
	}
	fmt.Printf("  sha256 OK (%d MB)\n", len(data)>>20)
	return nil
}

// download opens a URL with a generous timeout. A User-Agent header is
// required: the GitHub API rejects requests without one.
func download(url string) (io.ReadCloser, error) {
	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "launchctl-fetchruntimes")

	client := &http.Client{Timeout: 10 * time.Minute}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode >= 400 {
		_ = resp.Body.Close()
		return nil, fmt.Errorf("GET %s: status %s", url, resp.Status)
	}
	return resp.Body, nil
}

func getJSON(url string, out any) error {
	raw, err := download(url)
	if err != nil {
		return err
	}
	defer raw.Close()

	body, err := io.ReadAll(raw)
	if err != nil {
		return err
	}
	if err := json.Unmarshal(body, out); err != nil {
		return fmt.Errorf("decoding %s: %w", url, err)
	}
	return nil
}
