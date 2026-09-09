# Project Instructions

## Project quirks — read this first

This is a **portable Go web launcher** that must run on any system — no install step, no platform assumptions.

### Portability

- The app (`cmd/launcher/`, `internal/`, `assets.go`, `index.html`, `static/`) must be fully portable across Linux, macOS, and Windows.
- **Dependencies must be pure Go** (no cgo) so `CGO_ENABLED=0` cross-compilation stays a one-command build for every target.
- Never use platform-specific code without a build-tagged file (see `internal/runner/sysproc_*.go` and `internal/api/fs_drives_*.go` for the pattern).
- All paths must use `filepath.Join` (no hardcoded `/` or `\` separators).
- The server auto-opens a browser on Windows and pauses "Press Enter" on port conflict — keep these guards in place.

### The bundled Python runtime

- Release builds (`make go-release*`) embed a CPython 3.12 archive (`-tags embedded`); on first run it extracts into `data/runtime/`.
- **Dev builds** (`make go-build`) have no runtime and fall back to a `python3`/`python` on PATH — handy for development, but tests must never assume one exists for non-runner packages.
- `internal/pythonrt` owns extraction + interpreter lookup; the runner only consumes `Interpreter()`.
- `make fetch-runtimes` re-downloads the archives into `build/runtimes/` (gitignored).

### Data compatibility is sacred

- `internal/store` reads and writes the same `data/launcher.db` schema the earlier Python app used. Do not change the schema or the JSON blob format.
- Every stored record is an `internal/ordjson.OMap` — **object key order and numeric literals must survive round trips** (the run panel renders workflow steps via `Object.entries`, and audit hashes are computed over exact bytes).
- Audit hashes must stay byte-compatible with Python's `json.dumps(entry, sort_keys=True, ensure_ascii=False)`; the fixtures under `internal/store/testdata/` prove it. Regenerate with `python3 scripts/dev/gen_audit_fixtures.py` if the canonical serializer changes (it must not, silently).

### Parity fixtures

- `internal/scheduler/testdata/cron_fixtures.json` locks the cron engine to the original Python behaviour (fire times, error messages, descriptions). Regenerate with `python3 scripts/dev/gen_cron_fixtures.py` (runs in UTC; the Go test pins its zone to match).
- `tests/e2e/` drives the real UI in Chromium against the compiled server. It passes both on this platform and (via CI) against the release binaries.

## Comments & clarity — write for a junior dev

- Every code comment, docstring, and commit message must be concise and plain-English — a junior dev should understand it on first read.
- Comment the *why*, not the *what*. Skip comments that just restate the code.
- No jargon, acronyms, or clever shorthand without a brief explanation.
- These same rules apply to edits made to this file (AGENTS.md): keep instructions short, direct, and easy to follow.

## Tests are required

When adding or editing code, always include a unit test (or update existing ones) that covers the change.

- Go unit tests live next to the code (`*_test.go`) and run with:
  `make go-test`
- Race-check before finishing touched concurrency code:
  `go test -race ./...`
- End-to-end tests (Chromium) run with:
  `make test-e2e`  (needs `pip install -r requirements-dev.txt` + `python3 -m playwright install chromium`)
- Test helpers use `t.TempDir()` for scratch files and never mutate global state without cleanup.

## Server restart

- After backend changes, restart the server so changes take effect: `make restart` (runs `go-build` first).

## File ownership

- Run commands as the normal user; do not create files as root (they would block the user from editing them). If root-owned files appear, chown them back with the account that owns `Makefile`.

## Documentation updates

- After completing any change, update the relevant documentation (e.g. `README.md`) to reflect it before finishing.
- This includes new or changed features, commands, config, behavior, or usage instructions.
- Keep docs accurate and in the existing style of the file being edited.
