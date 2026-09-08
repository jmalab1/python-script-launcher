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
