"""Regression tests for the read-only DB ownership repair.

The old code called DB_PATH.chown(...), but pathlib.Path has no chown
method — the resulting AttributeError was not caught, so the server
crashed on startup whenever launcher.db was owned by another user.
"""

import os

import pytest

import launcher.storage as storage


def test_repair_uses_os_chown_with_the_db_path(monkeypatch):
    calls = []

    def fake_chown(path, uid, gid):
        calls.append((path, uid, gid))

    monkeypatch.setattr(os, "chown", fake_chown)
    monkeypatch.setattr(storage.DB_PATH.__class__, "exists",
                        lambda self: True, raising=False)
    storage._repair_db_ownership()
    assert calls == [(storage.DB_PATH, os.getuid(), -1)], calls


def test_repair_never_raises_when_chown_fails(monkeypatch):
    def boom(*args, **kwargs):
        raise PermissionError("not permitted")

    monkeypatch.setattr(os, "chown", boom)
    storage._repair_db_ownership()  # must not raise


def test_repair_is_a_noop_without_posix_apis(monkeypatch):
    calls = []
    monkeypatch.setattr(os, "chown", lambda *a, **k: calls.append(a))
    real_name = os.name
    monkeypatch.setattr(os, "name", "nt")
    try:
        storage._repair_db_ownership()
    finally:
        monkeypatch.setattr(os, "name", real_name)
    assert calls == [], "Windows has no chown; the repair must skip itself"


def test_get_conn_does_not_crash_on_a_read_only_db(store, monkeypatch):
    """Even with the ownership fix blocked, _get_conn must still open."""
    storage.load_json("profiles")  # create the DB file
    monkeypatch.setattr(storage.os, "access", lambda path, mode: False)
    monkeypatch.setattr(storage.os, "chown",
                        lambda *a, **k: (_ for _ in ()).throw(PermissionError))
    conn = storage._get_conn()
    try:
        assert conn.execute("SELECT 1").fetchone()[0] == 1
    finally:
        conn.close()
