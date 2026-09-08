# Project Instructions

## Tests are required

When adding or editing code, always include a unit test (or update existing ones) that covers the change.

- Tests live in `tests/` and are plain script-style asserts (no pytest).
- Run the full suite with:
  `python3 tests/test_workflows.py && python3 tests/test_workflow_execute.py && python3 tests/test_workflow_steps.py`
- Tests isolate state by redirecting module-level paths (e.g. `workflows.WORKFLOWS_FILE`, `runner.PROFILES_FILE`, `storage.HISTORY_FILE`) to a temp dir — follow that pattern for new tests.
- After any change, run the affected test file(s) and confirm they pass before finishing.
