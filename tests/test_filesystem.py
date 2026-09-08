import sys

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
