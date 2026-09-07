import os
import subprocess
from pathlib import Path


def browse_directory(path):
    path = Path(path).expanduser().resolve()
    if not path.exists():
        return {"error": f"Path does not exist: {path}"}
    if not path.is_dir():
        return {
            "path": str(path.parent),
            "selected_file": {"name": path.name, "path": str(path), "is_dir": False},
            "entries": [],
        }

    entries = []
    if path.parent != path:
        entries.append({"name": "..", "path": str(path.parent), "is_dir": True})

    try:
        for item in sorted(path.iterdir()):
            entries.append({
                "name": item.name,
                "path": str(item),
                "is_dir": item.is_dir(),
            })
    except PermissionError:
        return {"error": f"Permission denied: {path}"}

    return {"path": str(path), "entries": entries}


def open_file_dialog():
    import shutil
    if shutil.which("zenity"):
        try:
            result = subprocess.run(
                ["zenity", "--file-selection", "--title=Select Python Script", "--file-filter=Python files (*.py *.pyw)|*.py *.pyw", "--file-filter=All files (*.*)|*.*"],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0 and result.stdout.strip():
                return {"path": result.stdout.strip()}
            return {"path": None}
        except Exception as e:
            return {"error": str(e)}

    if shutil.which("kdialog"):
        try:
            result = subprocess.run(
                ["kdialog", "--getopenfilename", "--", "*.py *.pyw"],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0 and result.stdout.strip():
                return {"path": result.stdout.strip()}
            return {"path": None}
        except Exception as e:
            return {"error": str(e)}

    return {"error": "No file dialog available (install zenity or kdialog)"}


def script_exists(script_path):
    return {"exists": os.path.isfile(script_path) if script_path else False}
