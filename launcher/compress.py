"""On-the-fly gzip compression for text-based responses.

Compression is applied only when the client sends `Accept-Encoding: gzip`,
the body is compressible, and it is large enough to be worth the CPU.
Static files get an in-memory gzip cache keyed by (mtime, size) so repeated
requests don't re-compress; dynamic responses (JSON, index) are compressed
per request and never cached.
"""

import gzip
import threading

_COMPRESSIBLE = frozenset({
    "text/html",
    "text/css",
    "text/javascript",
    "application/javascript",
    "application/json",
})
_MIN_SIZE = 1024
_LEVEL = 6

_cache = {}
_cache_lock = threading.Lock()


def wants_gzip(accept_encoding):
    return "gzip" in (accept_encoding or "").lower()


def should_compress(content_type, size):
    base = (content_type or "").split(";")[0].strip().lower()
    return size >= _MIN_SIZE and base in _COMPRESSIBLE


def gzip_bytes(body):
    return gzip.compress(body, _LEVEL)


def gzip_static(path, body):
    """gzip `body` with a per-file cache (re-compresses when the file changes)."""
    try:
        st = path.stat()
        stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        return gzip_bytes(body)
    key = str(path)
    with _cache_lock:
        cached = _cache.get(key)
        if cached and cached[0] == stamp:
            return cached[1]
    data = gzip.compress(body, _LEVEL)
    with _cache_lock:
        _cache[key] = (stamp, data)
    return data
