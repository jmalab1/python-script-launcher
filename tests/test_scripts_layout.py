"""Tests for the layout of the scripts/ directory.

scripts/ holds only subdirectories: everything that the launcher runs as an
example lives in scripts/testing/ (it is all demo material for exercising the
app), and dev tooling lives in scripts/dev/. Pinning this down keeps the top
level clean so new folders have an obvious home.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

TESTING_SCRIPTS = [
    "backup.py",
    "fetch_data.py",
    "generate_report.py",
    "process_data.py",
    "send_email.py",
    "test_script.py",
    "unstable_task.py",
]


def test_all_example_scripts_live_in_scripts_testing():
    for name in TESTING_SCRIPTS:
        assert (SCRIPTS / "testing" / name).is_file(), f"{name} is missing from scripts/testing/"


def test_no_scripts_are_left_at_the_top_level():
    assert list(SCRIPTS.glob("*.py")) == [], "top-level scripts/ should only hold testing/ and dev/"


def test_dev_tooling_lives_in_scripts_dev():
    screencast = SCRIPTS / "dev" / "make_screencast.py"
    assert screencast.is_file(), "make_screencast.py is missing from scripts/dev/"


def test_every_example_script_is_a_valid_python_file():
    # Catches typos from edits without running the scripts (they sleep by design).
    for path in (SCRIPTS / "testing").glob("*.py"):
        compile(path.read_text(), str(path), "exec")


def test_screencast_seeds_from_the_testing_scripts():
    # The demo builds its profiles from the example scripts, so it must point
    # at scripts/testing/ after the split.
    src = (SCRIPTS / "dev" / "make_screencast.py").read_text()
    assert 'ROOT / "scripts" / "testing"' in src, "demo must seed from scripts/testing/"
