import logging
import re

import pytest
from logging.handlers import RotatingFileHandler

from launcher.api import logs

BACKUP_RE = re.compile(r"^server\.log\.\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(-\d+)?$")


@pytest.fixture
def log_file(tmp_path, monkeypatch):
    """Point config.DATA_DIR at a tmp dir so config.log_file() lands there."""
    import launcher.config as config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return tmp_path / "server.log"


def append(path, text):
    with path.open("a", encoding="utf-8") as f:
        f.write(text)


def test_missing_log_file_returns_empty_reset(log_file):
    result = logs.handle_list()
    assert result == {"entries": [], "next_offset": 0, "reset": True}


def test_empty_log_file_returns_empty_reset(log_file):
    log_file.touch()
    result = logs.handle_list()
    assert result["entries"] == []
    assert result["next_offset"] == 0
    assert result["reset"] is True


def test_tail_returns_last_n_lines_and_file_size_offset(log_file):
    append(log_file, "".join(f"line {i}\n" for i in range(1, 11)))
    result = logs.handle_list(lines=3)
    assert result["entries"] == ["line 8", "line 9", "line 10"]
    assert result["reset"] is True
    assert result["next_offset"] == log_file.stat().st_size


def test_tail_returns_everything_when_file_is_short(log_file):
    append(log_file, "a\nb\nc\n")
    result = logs.handle_list(lines=10)
    assert result["entries"] == ["a", "b", "c"]


def test_lines_param_accepts_strings_and_clamps_invalid_values(log_file):
    append(log_file, "a\nb\nc\n")
    assert logs.handle_list(lines="2")["entries"] == ["b", "c"]
    assert logs.handle_list(lines=0)["entries"] == ["c"]
    assert logs.handle_list(lines=-5)["entries"] == ["c"]
    assert logs.handle_list(lines=999999)["entries"] == ["a", "b", "c"]
    assert logs.handle_list(lines="bogus")["entries"] == ["a", "b", "c"]


def test_incremental_poll_returns_only_new_lines(log_file):
    append(log_file, "first\nsecond\n")
    full = logs.handle_list()
    assert full["reset"] is True

    append(log_file, "third\nfourth\n")
    inc = logs.handle_list(after=full["next_offset"])
    assert inc["entries"] == ["third", "fourth"]
    assert inc["reset"] is False
    assert inc["next_offset"] == log_file.stat().st_size


def test_incremental_poll_with_no_new_data_returns_empty(log_file):
    append(log_file, "only\n")
    first = logs.handle_list()
    again = logs.handle_list(after=first["next_offset"])
    assert again["entries"] == []
    assert again["reset"] is False
    assert again["next_offset"] == first["next_offset"]


def test_poll_withholds_trailing_partial_line_then_delivers_it(log_file):
    append(log_file, "complete\n")
    first = logs.handle_list()

    append(log_file, "part")
    inc = logs.handle_list(after=first["next_offset"])
    assert inc["entries"] == []
    assert inc["next_offset"] == first["next_offset"]

    append(log_file, "ial line\n")
    inc2 = logs.handle_list(after=inc["next_offset"])
    assert inc2["entries"] == ["partial line"]
    assert inc2["next_offset"] == log_file.stat().st_size


def test_offset_past_file_size_resets_to_tail(log_file):
    append(log_file, "a\nb\nc\n")
    result = logs.handle_list(after=99999)
    assert result["reset"] is True
    assert result["entries"] == ["a", "b", "c"]


def test_invalid_after_param_falls_back_to_tail(log_file):
    append(log_file, "a\nb\n")
    result = logs.handle_list(after="not-a-number")
    assert result["reset"] is True
    assert result["entries"] == ["a", "b"]


def test_windows_line_endings_are_stripped(log_file):
    append(log_file, "one\r\ntwo\r\n")
    result = logs.handle_list()
    assert result["entries"] == ["one", "two"]
    assert result["next_offset"] == log_file.stat().st_size


def test_invalid_utf8_is_replaced_not_raised(log_file):
    with log_file.open("wb") as f:
        f.write(b"ok\n\xff\xfe bad\n")
    result = logs.handle_list()
    assert result["entries"][0] == "ok"
    assert "bad" in result["entries"][1]


def test_poll_offset_across_a_rotation_resets_to_fresh_tail(log_file):
    append(log_file, "".join(f"old {i}\n" for i in range(100)))
    stale = logs.handle_list()
    old_offset = stale["next_offset"]

    # Simulate rotation: the active log file is replaced by a fresh one.
    log_file.write_bytes(b"")
    append(log_file, "fresh line\n")

    result = logs.handle_list(after=old_offset)
    assert result["reset"] is True
    assert result["entries"] == ["fresh line"]
    assert result["next_offset"] == log_file.stat().st_size


def test_setup_file_logging_installs_a_timestamped_rotating_handler(tmp_path, monkeypatch):
    import logging

    import launcher.config as config
    import launcher.server as server

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(server, "LOG_MAX_BYTES", 500)
    monkeypatch.setattr(server, "LOG_BACKUP_COUNT", 2)
    monkeypatch.setattr(server.setup_file_logging, "_done", False, raising=False)

    server.setup_file_logging()
    try:
        rotating = [
            h for h in logging.getLogger().handlers
            if isinstance(h, server.TimestampedRotatingFileHandler)
            and getattr(h, "baseFilename", None) == str(tmp_path / "server.log")
        ]
        assert len(rotating) == 1
        assert rotating[0].maxBytes == 500
        assert rotating[0].backupCount == 2

        logger = logging.getLogger("rotation-test")
        logger.setLevel(logging.DEBUG)
        for _ in range(40):
            logger.info("x" * 40)

        backups = [
            p for p in tmp_path.iterdir()
            if p.name.startswith("server.log.") and BACKUP_RE.match(p.name)
        ]
        assert backups, "records past maxBytes must rotate into datetime-stamped backups"
        assert len(backups) == 2, "only the newest backupCount backups must be kept"
        numeric = [p for p in tmp_path.iterdir() if re.match(r"^server\.log\.\d+$", p.name)]
        assert not numeric, "backups must be datetime-stamped, not numbered"

        active = logs.handle_list()
        assert active["entries"], "the log API must keep working after rotation"
    finally:
        for h in list(logging.getLogger().handlers):
            if getattr(h, "baseFilename", None) == str(tmp_path / "server.log"):
                logging.getLogger().removeHandler(h)
                h.close()
