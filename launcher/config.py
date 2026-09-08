from pathlib import Path

PORT = 8765
DATA_DIR = Path(__file__).parent.parent / "data"
PROFILES_FILE = DATA_DIR / "profiles.json"
WORKFLOWS_FILE = DATA_DIR / "workflows.json"
HISTORY_FILE = DATA_DIR / "history.json"
AUDIT_FILE = DATA_DIR / "audit.json"
STATIC_DIR = Path(__file__).parent.parent / "static"
INDEX_FILE = Path(__file__).parent.parent / "index.html"
