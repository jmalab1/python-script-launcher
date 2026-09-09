# Project Instructions

## Project quirks — read this first

This is a **portable Go web launcher** that must run on any system — no install step, no platform assumptions.

### Portability

- The app (`cmd/launcher/`, `internal/`, `assets.go`, `index.html`, `static/`) must be fully portable across Linux, macOS, and Windows.
- **Dependencies must be pure Go** (no cgo) so `CGO_ENABLED=0` cross-compilation stays a one-command build for every target.
- Never use platform-specific code without a build-tagged file (see `internal/runner/sysproc_*.go` and `internal/api/fs_drives_*.go` for the pattern).
- All paths must use `filepath.Join` (no hardcoded `/` or `\` separators).
- The server opens the browser on every launch (all platforms; `-foreground`, used by the e2e suite, stays quiet). It also pauses "Press Enter" on port conflict — keep these guards in place.
- Background mode is built into the binary (`internal/daemon`: detach by default on Linux/macOS, `-stop`, `-foreground`). `make start`/`stop` call it; keep `server_main`-style wrapper scripts out. Test data dirs set `LAUNCHER_DATA_DIR` or the e2e suite budget of a free port.

### The bundled Python runtime

- Release builds (`make go-release*`) embed a CPython 3.12 archive (`-tags embedded`); on first run it extracts into `data/runtime/`.
- **Dev builds** (`make go-build`) have no runtime and fall back to a `python3`/`python` on PATH — handy for development, but tests must never assume one exists for non-runner packages.
- `internal/pythonrt` owns extraction + interpreter lookup; the runner only consumes `Interpreter()`.
- `make fetch-runtimes` re-downloads the archives into `build/runtimes/` (gitignored).

### Data compatibility is sacred

- `internal/store` reads and writes the same `launchctl-data/launcher.db` schema the earlier Python app used. Do not change the schema or the JSON blob format.
- Every stored record is an `internal/ordjson.OMap` — **object key order and numeric literals must survive round trips** (the run panel renders workflow steps via `Object.entries`, and audit hashes are computed over exact bytes).
- Audit hashes must stay byte-compatible with Python's `json.dumps(entry, sort_keys=True, ensure_ascii=False)`; the fixtures under `internal/store/testdata/` prove it. Those fixtures are frozen snapshots produced by the archived Python implementation (its sources are gone) — never regenerate or edit the testdata silently.

### Parity fixtures

- `internal/scheduler/testdata/cron_fixtures.json` locks the cron engine to the original Python behaviour (fire times, error messages, descriptions, computed in UTC; the Go test pins its zone to match). Frozen snapshot from the archived Python implementation — do not regenerate.
- `tests/e2e/` drives the real UI in Chromium against the compiled
  server (also verified against the release binary).

## Comments & clarity — write for a junior dev

- Every code comment, docstring, and commit message must be concise and plain-English — a junior dev should understand it on first read.
- Comment the *why*, not the *what*. Skip comments that just restate the code.
- No jargon, acronyms, or clever shorthand without a brief explanation.
- These same rules apply to edits made to this file (AGENTS.md): keep instructions short, direct, and easy to follow.

### Blank lines between code blocks

- Separate logical blocks inside a function body (if/for/switch, and steps like "load", "build", "save") with a blank line.
- Keep tightly associated lines together: a call and the `if err` that checks it, a variable and the block that consumes it, guard clauses with the code they guard.
- `gofmt` (`make go-fmt`) preserves these blank lines, so format after editing.

## Tests are required

When adding or editing code, always include a unit test (or update existing ones) that covers the change.

- Go unit tests live next to the code (`*_test.go`) and run with:
  `make go-test`
- Race-check before finishing touched concurrency code:
  `go test -race ./...`
- End-to-end tests (Chromium, via playwright-go) run with:
  `make test-e2e`
  Install the browser driver once:
  `go run github.com/mxschmitt/playwright-go/cmd/playwright install chromium`
  The suite lives under `tests/e2e/` behind the `e2e` build tag, so plain
  `go test ./...` never touches it.
- Test helpers use `t.TempDir()` for scratch files and never mutate global state without cleanup.

## Server restart

- After backend changes, restart the server so changes take effect: `make restart`.
- `make restart` does NOT rebuild by itself — it stops and starts `dist/launchctl` as-is, and `make start` skips the build when the binary exists. Always pair code edits with an explicit `make go-build` first (or use `make go-build && make restart`).
- This applies to frontend files too: `index.html` and everything under `static/` are embedded into the binary at build time, so editing JS/HTML does nothing until the binary is rebuilt and the server restarted (then hard-refresh the browser).
- A quick end-to-end sanity check after UI changes: `make check-browser` (or `make test-e2e` for the full suite).

## File ownership

- Run commands as the normal user; do not create files as root (they would block the user from editing them). If root-owned files appear, chown them back with the account that owns `Makefile`.

## Documentation updates

- After completing any change, update the relevant documentation (e.g. `README.md`) to reflect it before finishing.
- This includes new or changed features, commands, config, behavior, or usage instructions.
- Keep docs accurate and in the existing style of the file being edited.
