# Project Instructions

## Project quirks — read this first

This is a **portable Python web launcher** that must run on any system with Python 3 — no install step, no platform assumptions.

### Portability

- The app (`launcher/`, `launcher.py`, `index.html`, `static/`) must be fully portable across Linux, macOS, and Windows.
- Never use platform-specific APIs unless guarded behind `os.name` / `sys.platform` checks.
- All paths must use `pathlib.Path` (no hardcoded `/` or `\` separators).
- The server auto-opens a browser on Windows (`os.name == "nt"`) and prompts for Enter on port conflict — keep these guards in place.

### Dependency policy

- **App code**: Python stdlib only. No third-party imports. No install step. If you need something beyond stdlib, find another way.
- **Unit tests**: May use dev dependencies (tracked in `requirements-dev.txt`, currently just pytest). Never import a dev dependency from app code.
- When adding a new stdlib import, verify it exists in Python 3.8+ (the minimum supported version).
- Frontend (`static/js/`, `index.html`) uses vanilla JS — no npm, no bundler, no transpilation.

## Tests are required

When adding or editing code, always include a unit test (or update existing ones) that covers the change.

- Tests live in `tests/` and use **pytest** (functions + asserts, no classes needed).
- Run the full suite with:
  `python3 -m pytest tests/`
- Isolation conventions:
  - Use the `store` fixture from `tests/conftest.py` — it redirects every module-level path (`workflows.WORKFLOWS_FILE`, `profiles.PROFILES_FILE`, `runner.PROFILES_FILE`, `storage.HISTORY_FILE`, etc.) to a tmp dir. Tests that touch disk or runs must request it.
  - Use pytest's built-in `tmp_path` for scratch files and `monkeypatch` for patching (never leave globals mutated).
  - Use the `new_run` fixture for tests that create `runner.active_runs` entries.
- Frontend (JS) behavior is covered by source-inspection tests (e.g. `test_confirm_modal.py`) that assert on the files in `static/js/components/` — follow that pattern for UI changes.
- After any change, run the full suite and confirm it passes before finishing.

## Server restart

- After changes to backend files (`launcher/`), restart the server so the changes take effect. Run `make restart` from the project root.

## Documentation updates

- After completing any change, update the relevant documentation (e.g. `README.md`) to reflect it before finishing.
- This includes new or changed features, commands, config, behavior, or usage instructions.
- Keep docs accurate and in the existing style of the file being edited.
