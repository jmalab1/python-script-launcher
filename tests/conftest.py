import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Redirect every module-level store path to a temp dir.

    The api/runner/storage modules each import their path constants from
    launcher.config at module level, so every copy must be patched.
    Returns a dict of the redirected paths.
    """
    import launcher.config as config
    import launcher.storage as storage
    import launcher.runner as runner
    import launcher.api.history as history
    import launcher.api.profiles as profiles
    import launcher.api.workflows as workflows
    import launcher.api.runs as runs
    import launcher.api.audit as audit

    paths = {
        "profiles": tmp_path / "profiles.json",
        "workflows": tmp_path / "workflows.json",
        "history": tmp_path / "history.json",
        "audit": tmp_path / "audit.json",
    }
    monkeypatch.setattr(config, "WORKFLOWS_FILE", paths["workflows"])
    monkeypatch.setattr(storage, "HISTORY_FILE", paths["history"])
    monkeypatch.setattr(storage, "AUDIT_FILE", paths["audit"])
    monkeypatch.setattr(runner, "PROFILES_FILE", paths["profiles"])
    monkeypatch.setattr(history, "HISTORY_FILE", paths["history"])
    monkeypatch.setattr(profiles, "PROFILES_FILE", paths["profiles"])
    monkeypatch.setattr(workflows, "PROFILES_FILE", paths["profiles"])
    monkeypatch.setattr(workflows, "WORKFLOWS_FILE", paths["workflows"])
    monkeypatch.setattr(runs, "PROFILES_FILE", paths["profiles"])
    monkeypatch.setattr(runs, "HISTORY_FILE", paths["history"])
    monkeypatch.setattr(audit, "AUDIT_FILE", paths["audit"])
    monkeypatch.setattr(audit, "PROFILES_FILE", paths["profiles"])
    monkeypatch.setattr(audit, "WORKFLOWS_FILE", paths["workflows"])
    return paths


@pytest.fixture
def new_run():
    """Create an active run entry in launcher.runner and clean up after."""
    import launcher.runner as runner

    def _new(run_id):
        runner.active_runs[run_id] = {
            "output": [],
            "workflow_log": [],
            "status": "running",
            "returncode": None,
            "failed": False,
        }
        return run_id

    runner.active_runs.clear()
    yield _new
    runner.active_runs.clear()
