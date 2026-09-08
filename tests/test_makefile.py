"""Source checks for the Makefile's start/stop robustness.

A server started by another user (e.g. root) used to make `make stop`
report "Server not running" (the failed kill was swallowed) and delete
the PID file, and `make start` reported success even when the process
died immediately.
"""

import re
from pathlib import Path

MAKEFILE = Path(__file__).resolve().parent.parent / "Makefile"


def makefile_src():
    return MAKEFILE.read_text()


def test_stop_distinguishes_a_live_server_it_cannot_kill_from_a_stale_pid():
    src = makefile_src()
    stop = src[src.index("\nstop:"):src.index("\nrestart:")]
    assert re.search(r"elif kill -0 \$\$pid", stop), \
        "stop must check whether the process is still alive before giving up"
    assert "another user" in stop, \
        "a permission-denied kill must be reported, not swallowed as 'not running'"


def test_stop_keeps_the_pidfile_when_the_server_belongs_to_another_user():
    src = makefile_src()
    stop = src[src.index("\nstop:"):src.index("\nrestart:")]
    other_user_branch = stop[stop.index("another user"):stop.index("stale PID")]
    assert "rm -f" not in other_user_branch, \
        "the PID file must survive so start can report 'already running'"


def test_start_verifies_the_process_came_up():
    src = makefile_src()
    start = src[src.index("\nstart:"):src.index("\nstop:")]
    assert re.search(r"sleep \d+", start), "start must wait before checking liveness"
    assert "kill -0 $$pid" in start, "start must confirm the process is alive"
    assert "Server failed to start" in start, "a dead process must not be reported as started"
    assert "tail -n 5 server.log" in start, "the failure must point at server.log"
    assert "rm -f $(PIDFILE)" in start, "a failed start must not leave a stale PID file"
