import ctypes
import os
import queue
import shutil
import string
import subprocess
import sys
import threading
from pathlib import Path

_dialog_lock = threading.Lock()
_dialog_queue = queue.Queue()

# How long an HTTP worker waits for the main thread to service a queued
# Tk dialog. Generous: the user may keep the dialog open for a while.
_MAIN_THREAD_DIALOG_TIMEOUT = 600

PYTHON_EXTENSIONS = {".py", ".pyw"}


def is_python_script(path):
    return Path(path).suffix.lower() in PYTHON_EXTENSIONS


def _run_on_main_thread(dialog_fn):
    """Queue a dialog for the main thread and wait for its result."""
    done = threading.Event()
    result = []
    _dialog_queue.put((dialog_fn, done, result))
    if not done.wait(_MAIN_THREAD_DIALOG_TIMEOUT):
        return None
    return result[0] if result else None


def _execute_dialog(dialog_fn):
    """Run a dialog, keeping Tk on the main thread (required on macOS).

    HTTP handlers run on worker threads; subprocess-based dialogs
    (zenity/kdialog) are safe there, but Tk dialogs are queued for the
    main thread's pump loop in server.main(). When already on the main
    thread (tests, or the pump loop itself) the dialog runs directly.
    """
    if dialog_fn is _tk_dialog and threading.current_thread() is not threading.main_thread():
        return _run_on_main_thread(dialog_fn)
    return dialog_fn()


def pump_dialogs(timeout=0.5):
    """Run pending Tk dialogs on the calling thread (the server's main thread).

    Blocks up to `timeout` for the first queued dialog, then drains any
    further queued dialogs without blocking. server.main() calls this in
    a loop so Tk dialogs requested from HTTP worker threads execute on
    the main thread, as macOS requires.
    """
    try:
        dialog_fn, done, result = _dialog_queue.get(timeout=timeout)
    except queue.Empty:
        return
    result.append(dialog_fn())
    done.set()
    while True:
        try:
            dialog_fn, done, result = _dialog_queue.get_nowait()
        except queue.Empty:
            return
        result.append(dialog_fn())
        done.set()


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

        result = _execute_dialog(dialog)
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
