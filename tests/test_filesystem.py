import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import launcher.api.filesystem as fs

tmp = Path(tempfile.mkdtemp())
(tmp / "sub").mkdir()
(tmp / "tool.py").write_text("print('x')\n")
(tmp / "wrapper.pyw").write_text("print('y')\n")
(tmp / "notes.txt").write_text("hi")

try:
    # 1. is_python_script
    assert fs.is_python_script("a.py")
    assert fs.is_python_script("A.PY")
    assert fs.is_python_script("a.pyw")
    assert not fs.is_python_script("a.txt")
    assert not fs.is_python_script("a")
    print("PASS: is_python_script accepts .py/.pyw case-insensitively")

    # 2. browse a directory
    res = fs.browse_directory(tmp)
    assert res["path"] == str(tmp.resolve())
    assert res["entries"][0]["name"] == ".."
    names = {e["name"] for e in res["entries"]}
    assert {"sub", "tool.py", "wrapper.pyw", "notes.txt"} <= names
    sub = next(e for e in res["entries"] if e["name"] == "sub")
    assert sub["is_dir"] is True
    py = next(e for e in res["entries"] if e["name"] == "tool.py")
    assert py["is_dir"] is False
    print("PASS: browse_directory lists parent plus entries")

    # 3. missing path
    assert "error" in fs.browse_directory(tmp / "nope")
    print("PASS: browse_directory errors on missing paths")

    # 4. selecting a file directly
    ok = fs.browse_directory(tmp / "tool.py")
    assert ok["selected_file"]["name"] == "tool.py"
    assert ok["selected_file"]["is_dir"] is False
    assert ok["path"] == str(tmp.resolve())
    bad = fs.browse_directory(tmp / "notes.txt")
    assert "not a Python script" in bad["error"]
    print("PASS: browse_directory only accepts Python files as selections")

    # 5. script_exists
    assert fs.script_exists(str(tmp / "tool.py")) == {"exists": True}
    assert fs.script_exists(str(tmp)) == {"exists": False}
    assert fs.script_exists(str(tmp / "nope.py")) == {"exists": False}
    assert fs.script_exists("") == {"exists": False}
    assert fs.script_exists(None) == {"exists": False}
    print("PASS: script_exists only reports real files")

    # 6. list_drives is empty on POSIX
    if sys.platform != "win32":
        assert fs.list_drives() == []
        print("PASS: list_drives returns nothing on POSIX")

    # 7. open_file_dialog validates and reports failures
    orig_which = fs.shutil.which
    orig_tk = fs._tk_dialog
    fs.shutil.which = lambda name: None
    try:
        fs._tk_dialog = lambda: {"path": str(tmp / "tool.py")}
        assert fs.open_file_dialog() == {"path": str(tmp / "tool.py")}

        fs._tk_dialog = lambda: {"path": str(tmp / "notes.txt")}
        assert "not a Python script" in fs.open_file_dialog()["error"]

        fs._tk_dialog = lambda: {"path": None}
        assert fs.open_file_dialog() == {"path": None}

        fs._tk_dialog = lambda: None
        assert "dialog" in fs.open_file_dialog()["error"]

        orig_platform = sys.platform
        sys.platform = "win32"
        try:
            assert "tkinter" in fs.open_file_dialog()["error"]
        finally:
            sys.platform = orig_platform
        print("PASS: open_file_dialog validates selection and reports missing dialogs")
    finally:
        fs.shutil.which = orig_which
        fs._tk_dialog = orig_tk
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\nALL TESTS PASSED")
