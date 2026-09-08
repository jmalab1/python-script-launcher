import ctypes
import os
import shutil
import string
import subprocess
import sys
import threading
from pathlib import Path

_dialog_lock = threading.Lock()

PYTHON_EXTENSIONS = {".py", ".pyw"}


def is_python_script(path):
    return Path(path).suffix.lower() in PYTHON_EXTENSIONS


def browse_directory(path):
    path = Path(path).expanduser().resolve()
    if not path.exists():
        return {"error": f"Path does not exist: {path}"}
    if not path.is_dir():
        if not is_python_script(path):
            return {"error": f'"{path.name}" is not a Python script (.py or .pyw)'}
        return {
            "path": str(path.parent),
            "selected_file": {"name": path.name, "path": str(path), "is_dir": False},
            "entries": [],
        }

    entries = []
    if path.parent != path:
        entries.append({"name": "..", "path": str(path.parent), "is_dir": True})
    else:
        entries.extend(list_drives())

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


def list_drives():
    if os.name != "nt":
        return []
    try:
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    except Exception:
        return []
    drives = []
    for i, letter in enumerate(string.ascii_uppercase):
        if bitmask >> i & 1:
            drives.append({"name": f"{letter}:", "path": f"{letter}:\\", "is_dir": True})
    return drives


def _tk_dialog():
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            path = filedialog.askopenfilename(
                title="Select Python Script",
                parent=root,
                filetypes=[("Python files", "*.py *.pyw"), ("All files", "*.*")],
            )
        finally:
            root.destroy()
        return {"path": path or None}
    except Exception:
        return None


def _zenity_dialog():
    try:
        result = subprocess.run(
            ["zenity", "--file-selection", "--title=Select Python Script", "--file-filter=Python files (*.py *.pyw)|*.py *.pyw", "--file-filter=All files (*.*)|*.*"],
            capture_output=True, text=True, timeout=120,
        )
    except Exception:
        return None
    if result.returncode == 0 and result.stdout.strip():
        return {"path": result.stdout.strip()}
    return {"path": None}


def _kdialog_dialog():
    try:
        result = subprocess.run(
            ["kdialog", "--getopenfilename", "--", "*.py *.pyw"],
            capture_output=True, text=True, timeout=120,
        )
    except Exception:
        return None
    if result.returncode == 0 and result.stdout.strip():
        return {"path": result.stdout.strip()}
    return {"path": None}


def script_exists(script_path):
    return {"exists": os.path.isfile(script_path) if script_path else False}


def open_file_dialog():
    with _dialog_lock:
        if sys.platform in ("win32", "darwin"):
            dialog = _tk_dialog
        else:
            dialog = None
            for name, fn in (("zenity", _zenity_dialog), ("kdialog", _kdialog_dialog)):
                if shutil.which(name):
                    dialog = fn
                    break
            if dialog is None:
                dialog = _tk_dialog

        result = dialog()
        if result is not None:
            selected = result.get("path")
            if selected and not is_python_script(selected):
                return {"error": f'"{Path(selected).name}" is not a Python script (.py or .pyw)'}
            return result

        if sys.platform == "win32":
            return {"error": "File dialog unavailable (tkinter is required; reinstall Python with tcl/tk enabled)"}
        if sys.platform == "darwin":
            return {"error": "File dialog unavailable (tkinter is required)"}
        return {"error": "No file dialog available (install zenity or kdialog)"}
