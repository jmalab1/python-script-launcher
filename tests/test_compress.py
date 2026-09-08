import gzip
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import launcher.compress as compress

# 1. wants_gzip parses Accept-Encoding
assert compress.wants_gzip(None) is False
assert compress.wants_gzip("") is False
assert compress.wants_gzip("br") is False
assert compress.wants_gzip("gzip") is True
assert compress.wants_gzip("deflate, gzip, br") is True
assert compress.wants_gzip("GZIP") is True
print("PASS: wants_gzip detects gzip in Accept-Encoding")

# 2. should_compress gates on type and minimum size
assert compress.should_compress("text/html", 1024) is True
assert compress.should_compress("text/html; charset=utf-8", 5000) is True
assert compress.should_compress("TEXT/CSS", 1024) is True
assert compress.should_compress("image/png", 5000) is False
assert compress.should_compress(None, 5000) is False
assert compress.should_compress("application/json", 1023) is False
print("PASS: should_compress gates on compressible type and minimum size")

# 3. gzip_bytes roundtrip
body = ("hello world " * 200).encode()
assert gzip.decompress(compress.gzip_bytes(body)) == body
print("PASS: gzip_bytes roundtrips")

tmp = Path(tempfile.mkdtemp())
target = tmp / "app.js"
try:
    # 4. gzip_static caches per file
    body = b"console.log('x');" * 100
    target.write_bytes(body)
    first = compress.gzip_static(target, body)
    second = compress.gzip_static(target, body)
    assert second is first, "cache hit should return the cached bytes"
    assert gzip.decompress(first) == body
    print("PASS: gzip_static caches compressed output")

    # 5. changed file re-compresses
    new_body = body + b"new content"
    target.write_bytes(new_body)
    stamp = target.stat().st_mtime_ns + 1_000_000
    os.utime(target, ns=(stamp, stamp))
    fresh = compress.gzip_static(target, new_body)
    assert fresh is not first
    assert gzip.decompress(fresh) == new_body
    print("PASS: gzip_static re-compresses when the file changes")

    # 6. missing file falls back to per-request compression
    fallback = compress.gzip_static(tmp / "missing.js", b"fallback body " * 100)
    assert gzip.decompress(fallback) == b"fallback body " * 100
    print("PASS: gzip_static falls back when the file cannot be stat'd")
finally:
    compress._cache.clear()
    shutil.rmtree(tmp, ignore_errors=True)

print("\nALL TESTS PASSED")
