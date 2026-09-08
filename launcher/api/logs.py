"""Tail the server's own log file for the Logs panel.

The handler exposes two read modes via the same endpoint:

- Full tail (no ``after``): the last ``lines`` complete lines, for the
  initial view.
- Incremental (``after``=<byte offset>): only lines appended since that
  offset, so the UI can live-tail cheaply every couple of seconds.

A trailing line that has not been terminated with a newline yet is
withheld and ``next_offset`` only advances past complete lines, so no
partial or duplicated lines ever reach the client. When the file has
shrunken (rotated or truncated) the offset is no longer valid and the
handler falls back to a full tail with ``reset: true``.
"""

from ..config import log_file

DEFAULT_LINES = 500
MAX_LINES = 5000


def handle_list(lines=DEFAULT_LINES, after=None):
    path = log_file()
    try:
        size = path.stat().st_size
    except OSError:
        return {"entries": [], "next_offset": 0, "reset": True}

    try:
        lines = int(lines)
    except (TypeError, ValueError):
        lines = DEFAULT_LINES
    lines = max(1, min(lines, MAX_LINES))

    offset = None
    if after is not None:
        try:
            offset = int(after)
        except (TypeError, ValueError):
            offset = None

    if offset is not None and 0 <= offset <= size:
        return _read_from(path, size, offset)

    return _read_tail(path, size, lines)


def _read_tail(path, size, lines):
    data = _read_bytes(path, 0, size)
    complete, next_offset = _split_complete(data, 0)
    return {"entries": complete[-lines:], "next_offset": next_offset, "reset": True}


def _read_from(path, size, offset):
    data = _read_bytes(path, offset, size - offset)
    complete, next_offset = _split_complete(data, offset)
    return {"entries": complete[-MAX_LINES:], "next_offset": next_offset, "reset": False}


def _read_bytes(path, start, length):
    try:
        with path.open("rb") as f:
            if start:
                f.seek(start)
            return f.read(length) if length > 0 else b""
    except OSError:
        return b""


def _split_complete(data, base):
    """Split a byte chunk into complete lines.

    Returns the decoded lines and the absolute byte offset just past the
    last complete newline. A trailing partial line is withheld.
    """
    last_nl = data.rfind(b"\n")
    if last_nl == -1:
        return [], base
    text = data[: last_nl + 1].decode("utf-8", errors="replace")
    lines = [line[:-1] if line.endswith("\r") else line for line in text.split("\n")[:-1]]
    return lines, base + last_nl + 1
