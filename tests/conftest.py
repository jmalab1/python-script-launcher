import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _Store:
    """Redirect every module-level store path to a temp SQLite DB.

    The api/runner/storage modules each import their path constants from
    launcher.config at module level, so DB_PATH must be patched.
    Provides seed/read helpers for test data setup.
    """

    def __init__(self, db_path):
        self._db_path = db_path

    def seed(self, table, data):
        """Write a list of dicts into the given collection table."""
        from launcher.storage import save_json
        save_json(table, list(data))

    def read(self, table):
        """Read all rows from the given collection table as a list of dicts."""
        from launcher.storage import load_json
        return load_json(table)


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Redirect every module-level store path to a temp SQLite DB."""
    import launcher.config as config
    import launcher.storage as storage

    db_path = tmp_path / "launcher.db"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "DB_PATH", db_path)
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    storage._db_initialized = False

    s = _Store(db_path)
    yield s


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
