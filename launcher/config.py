from pathlib import Path

PORT = 8765
DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "launcher.db"

COL_PROFILES = "profiles"
COL_WORKFLOWS = "workflows"
COL_HISTORY = "history"
COL_AUDIT = "audit"

STATIC_DIR = Path(__file__).parent.parent / "static"
INDEX_FILE = Path(__file__).parent.parent / "index.html"

# Log rotation for data/server.log: rotate when the active file reaches
# LOG_MAX_BYTES, keep LOG_BACKUP_COUNT rotated copies named
# server.log.<YYYY-MM-DD_HH-MM-SS>. Set LOG_MAX_BYTES to 0 to disable.
LOG_MAX_BYTES = 2_000_000
LOG_BACKUP_COUNT = 3


def log_file():
    """Path of the server's own log file.

    Resolved lazily so tests (and the e2e harness) can repoint DATA_DIR
    before any logging happens.
    """
    return DATA_DIR / "server.log"
