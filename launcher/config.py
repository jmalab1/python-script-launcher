import json
import os
import shutil
import sys
import threading
from pathlib import Path

PORT = 8765

# App data folder name inside the OS per-user state location.
_APP_DATA_DIR_NAME = "launchctl-data"

# Legacy data directory names created by earlier builds (next to the
# executable). The first one found is adopted onto the canonical
# per-user location on startup.
_LEGACY_DATA_DIR_NAMES = [_APP_DATA_DIR_NAME, "data"]


def _user_state_dir():
    """Per-user base for app state, following platform conventions.

    Linux:   XDG data home  (or ~/.local/share)
    macOS:   ~/Library/Application Support
    Windows: %APPDATA% (via os.UserConfigDir)
    """
    if os.name == "nt":
        # os.UserConfigDir returns e.g. C:\Users\<user>\AppData\Roaming
        try:
            return Path(os.environ.get("APPDATA", "") or os.path.expanduser("~"))
        except Exception:
            pass
    elif sys.platform == "darwin":
        home = os.path.expanduser("~")
        if home and home != "~":
            return Path(home) / "Library" / "Application Support"
    else:
        xdg = os.environ.get("XDG_DATA_HOME", "")
        if xdg:
            return Path(xdg)
        home = os.path.expanduser("~")
        if home and home != "~":
            return Path(home) / ".local" / "share"
    # Fallback: next to this file (dev/legacy layout).
    return Path(__file__).parent.parent


def _resolve_data_dir():
    """Return the data directory, respecting env override and OS conventions."""
    # 1. Env var override (tests and e2e harness).
    env = os.environ.get("LAUNCHER_DATA_DIR")
    if env:
        return Path(env)
    # 2. OS per-user state location.
    return _user_state_dir() / _APP_DATA_DIR_NAME


def _adopt_legacy_data_dir():
    """Move an earlier-build data dir next to this file to the canonical
    per-user location (best effort, runs once per process)."""
    dest = _resolve_data_dir()
    if dest.exists():
        return
    for name in _LEGACY_DATA_DIR_NAMES:
        src = Path(__file__).parent.parent / name
        if src == dest or not src.is_dir():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(src), str(dest))
            break
        except OSError:
            pass


# Resolve data dir at import time. Legacy adoption runs once.
DATA_DIR = _resolve_data_dir()
_adopt_legacy_data_dir()

DB_PATH = DATA_DIR / "launcher.db"

COL_PROFILES = "profiles"
COL_WORKFLOWS = "workflows"
COL_HISTORY = "history"
COL_AUDIT = "audit"
COL_SCHEDULES = "schedules"

# How often the scheduler thread wakes up to check for due schedules.
SCHEDULER_TICK_SECONDS = 5

STATIC_DIR = Path(__file__).parent.parent / "static"
INDEX_FILE = Path(__file__).parent.parent / "index.html"

# Log rotation for data/server.log: rotate when the active file reaches
# LOG_MAX_BYTES, keep LOG_BACKUP_COUNT rotated copies named
# server.log.<YYYY-MM-DD_HH-MM-SS>. Set LOG_MAX_BYTES to 0 to disable.
LOG_MAX_BYTES = 2_000_000
LOG_BACKUP_COUNT = 3

# User-editable settings stored in settings.json inside DATA_DIR. This
# file is read on every use so changes take effect without a restart.
SETTINGS_PATH = DATA_DIR / "settings.json"
_settings_lock = threading.Lock()


def log_file():
    """Path of the server's own log file.

    Resolved lazily so tests (and the e2e harness) can repoint DATA_DIR
    before any logging happens.
    """
    return DATA_DIR / "server.log"


# ---------------------------------------------------------------------------
# Settings (settings.json)
# ---------------------------------------------------------------------------


def load_settings():
    """Read settings.json. Missing or corrupt file returns defaults."""
    with _settings_lock:
        if not SETTINGS_PATH.exists():
            return {}
        try:
            return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}


def save_settings(settings):
    """Write settings.json atomically."""
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(settings, indent=2)
    with _settings_lock:
        tmp = SETTINGS_PATH.with_suffix(".tmp")
        tmp.write_text(raw, encoding="utf-8")
        tmp.replace(SETTINGS_PATH)


def runtime_path_setting():
    """Return the configured runtime path (empty string when unset)."""
    return load_settings().get("runtime_path", "")


def resolve_python():
    """Return the Python interpreter to use for running scripts.

    Resolution order:
    1. User setting from settings.json (if the path exists).
    2. sys.executable (the interpreter running this server).
    """
    configured = runtime_path_setting()
    if configured:
        path = Path(configured)
        # Accept a direct path to a Python executable.
        if path.is_file():
            return str(path)
        # Accept a venv / install directory and pick the interpreter.
        if path.is_dir():
            if os.name == "nt":
                candidate = path / "Scripts" / "python.exe"
            else:
                candidate = path / "bin" / "python3"
            if candidate.is_file():
                return str(candidate)
    return sys.executable
