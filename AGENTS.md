# Project Instructions

## Dependency policy

- The app (`launcher/`, `launcher.py`, `index.html`, `static/`) must run **standalone**: Python stdlib only, no third-party imports, no install step.
- Unit tests are local-only and **may** use outside dev dependencies (tracked in `requirements-dev.txt`, currently just pytest). Never import a dev dependency from app code.

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
