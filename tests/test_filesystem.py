import sys
import threading

import pytest

import launcher.api.filesystem as fs


@pytest.fixture
def fs_tree(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "tool.py").write_text("print('x')\n")
    (tmp_path / "wrapper.pyw").write_text("print('y')\n")
    (tmp_path / "notes.txt").write_text("hi")
    return tmp_path


def test_is_python_script_accepts_py_pyw_case_insensitively():
    assert fs.is_python_script("a.py")
    assert fs.is_python_script("A.PY")
    assert fs.is_python_script("a.pyw")
    assert not fs.is_python_script("a.txt")
    assert not fs.is_python_script("a")


def test_browse_directory_lists_parent_plus_entries(fs_tree):
    res = fs.browse_directory(fs_tree)
    assert res["path"] == str(fs_tree.resolve())
    assert res["entries"][0]["name"] == ".."
    names = {e["name"] for e in res["entries"]}
    assert {"sub", "tool.py", "wrapper.pyw", "notes.txt"} <= names
    sub = next(e for e in res["entries"] if e["name"] == "sub")
    assert sub["is_dir"] is True
    py = next(e for e in res["entries"] if e["name"] == "tool.py")
    assert py["is_dir"] is False


def test_browse_directory_errors_on_missing_paths(fs_tree):
    assert "error" in fs.browse_directory(fs_tree / "nope")


def test_browse_directory_only_accepts_python_files_as_selections(fs_tree):
    ok = fs.browse_directory(fs_tree / "tool.py")
    assert ok["selected_file"]["name"] == "tool.py"
    assert ok["selected_file"]["is_dir"] is False
    assert ok["path"] == str(fs_tree.resolve())

    bad = fs.browse_directory(fs_tree / "notes.txt")
    assert "not a Python script" in bad["error"]


def test_script_exists_only_reports_real_files(fs_tree):
    assert fs.script_exists(str(fs_tree / "tool.py")) == {"exists": True}
    assert fs.script_exists(str(fs_tree)) == {"exists": False}
    assert fs.script_exists(str(fs_tree / "nope.py")) == {"exists": False}
    assert fs.script_exists("") == {"exists": False}
    assert fs.script_exists(None) == {"exists": False}


@pytest.mark.skipif(sys.platform == "win32", reason="drives only exist on Windows")
def test_list_drives_returns_nothing_on_posix():
    assert fs.list_drives() == []


def test_tk_dialogs_run_directly_on_the_main_thread(fs_tree, monkeypatch):
    monkeypatch.setattr(fs, "_tk_dialog", lambda: {"path": str(fs_tree / "tool.py")})
    assert fs._execute_dialog(fs._tk_dialog) == {"path": str(fs_tree / "tool.py")}


def test_tk_dialogs_from_worker_threads_are_serviced_by_pump_dialogs(monkeypatch):
    """Regression: Tk must run on the main thread (macOS crashes otherwise),
    so worker threads queue the dialog for server.main()'s pump loop."""
    monkeypatch.setattr(fs, "_tk_dialog", lambda: {"path": "/tmp/tool.py"})
    box = {}

    def worker():
        box["result"] = fs._execute_dialog(fs._tk_dialog)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    fs.pump_dialogs(timeout=5)
    t.join(timeout=5)
    assert not t.is_alive(), "worker must not wait forever for the dialog"
    assert box["result"] == {"path": "/tmp/tool.py"}


def test_pump_dialogs_drains_every_queued_dialog(monkeypatch):
    monkeypatch.setattr(fs, "_tk_dialog", lambda: "dialog")

    results = []

    def worker():
        results.append(fs._run_on_main_thread(fs._tk_dialog))

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(3)]
    for t in threads:
        t.start()
    fs.pump_dialogs(timeout=5)
    for t in threads:
        t.join(timeout=5)
    assert results == ["dialog", "dialog", "dialog"]


def test_open_file_dialog_validates_selection_and_reports_missing_dialogs(fs_tree, monkeypatch):
    monkeypatch.setattr(fs.shutil, "which", lambda name: None)
    monkeypatch.setattr(fs, "_tk_dialog", lambda: {"path": str(fs_tree / "tool.py")})
    assert fs.open_file_dialog() == {"path": str(fs_tree / "tool.py")}

    monkeypatch.setattr(fs, "_tk_dialog", lambda: {"path": str(fs_tree / "notes.txt")})
    assert "not a Python script" in fs.open_file_dialog()["error"]

    monkeypatch.setattr(fs, "_tk_dialog", lambda: {"path": None})
    assert fs.open_file_dialog() == {"path": None}

    monkeypatch.setattr(fs, "_tk_dialog", lambda: None)
    assert "dialog" in fs.open_file_dialog()["error"]

    monkeypatch.setattr(sys, "platform", "win32")
    assert "tkinter" in fs.open_file_dialog()["error"]
