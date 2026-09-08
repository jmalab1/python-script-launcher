import gzip
import os

import pytest

import launcher.compress as compress


@pytest.fixture(autouse=True)
def clean_gzip_cache():
    compress._cache.clear()
    yield
    compress._cache.clear()


def test_wants_gzip_detects_gzip_in_accept_encoding():
    assert compress.wants_gzip(None) is False
    assert compress.wants_gzip("") is False
    assert compress.wants_gzip("br") is False
    assert compress.wants_gzip("gzip") is True
    assert compress.wants_gzip("deflate, gzip, br") is True
    assert compress.wants_gzip("GZIP") is True


def test_should_compress_gates_on_compressible_type_and_minimum_size():
    assert compress.should_compress("text/html", 1024) is True
    assert compress.should_compress("text/html; charset=utf-8", 5000) is True
    assert compress.should_compress("TEXT/CSS", 1024) is True
    assert compress.should_compress("image/png", 5000) is False
    assert compress.should_compress(None, 5000) is False
    assert compress.should_compress("application/json", 1023) is False


def test_gzip_bytes_roundtrips():
    body = ("hello world " * 200).encode()
    assert gzip.decompress(compress.gzip_bytes(body)) == body


def test_gzip_static_caches_compressed_output(tmp_path):
    target = tmp_path / "app.js"
    body = b"console.log('x');" * 100
    target.write_bytes(body)

    first = compress.gzip_static(target, body)
    second = compress.gzip_static(target, body)
    assert second is first, "cache hit should return the cached bytes"
    assert gzip.decompress(first) == body


def test_gzip_static_recompresses_when_the_file_changes(tmp_path):
    target = tmp_path / "app.js"
    body = b"console.log('x');" * 100
    target.write_bytes(body)
    first = compress.gzip_static(target, body)

    new_body = body + b"new content"
    target.write_bytes(new_body)
    stamp = target.stat().st_mtime_ns + 1_000_000
    os.utime(target, ns=(stamp, stamp))
    fresh = compress.gzip_static(target, new_body)
    assert fresh is not first
    assert gzip.decompress(fresh) == new_body


def test_gzip_static_falls_back_when_the_file_cannot_be_statted(tmp_path):
    fallback = compress.gzip_static(tmp_path / "missing.js", b"fallback body " * 100)
    assert gzip.decompress(fallback) == b"fallback body " * 100
