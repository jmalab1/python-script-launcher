#!/usr/bin/env python3
"""Download the CPython runtimes that release builds embed.

For each target (see TARGETS), the matching "install_only" archive from
astral-sh/python-build-standalone is fetched, checksum-verified against
the release's SHA256SUMS, and stored as build/runtimes/<target>.tar.gz.
`make go-release` embeds one archive into each binary via -tags embedded;
the Go program extracts it to data/runtime/ on first run.

Run from the repo root:  python3 scripts/dev/fetch_runtimes.py [--tag X]
Requires only the standard library.
"""

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

REPO = "astral-sh/python-build-standalone"
OUT = Path(__file__).resolve().parent.parent.parent / "build" / "runtimes"

# Targets: name -> asset platform triple + arch.
TARGETS = {
    "linux-amd64":  ("x86_64-unknown-linux-gnu", "x86_64"),
    "linux-arm64":  ("aarch64-unknown-linux-gnu", "aarch64"),
    "windows-amd64": ("x86_64-pc-windows-msvc", "x86_64"),
    "macos-amd64":  ("x86_64-apple-darwin", "x86_64"),
    "macos-arm64":  ("aarch64-apple-darwin", "aarch64"),
}

VERSION = "3.12"


def fetch(url):
    with urllib.request.urlopen(url, timeout=120) as resp:
        return resp.read()


def pick_asset(assets, platform_triple):
    """The install_only archive for VERSION and the given triple."""
    pattern = re.compile(
        rf"^cpython-{VERSION}\.\d+(\.\d+)?\+[^-]+-{platform_triple}-install_only\.tar\.gz$"
    )
    names = [a["name"] for a in assets if pattern.match(a["name"])]
    if not names:
        available = ", ".join(sorted(a["name"] for a in assets)[:8])
        raise SystemExit(
            f"no cpython {VERSION} install_only asset for {platform_triple}; available: {available}"
        )
    return names[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="latest", help="release tag (default: latest)")
    args = parser.parse_args()

    release_api = "https://api.github.com/repos/%s/releases%s" % (
        REPO,
        "/latest" if args.tag == "latest" else ("/tags/" + args.tag),
    )
    release = json.loads(fetch(release_api))
    tag = release["tag_name"]
    assets = {a["name"]: a for a in release["assets"]}
    print(f"release tag: {tag}")

    # The release's SHA256SUMS asset maps file name -> digest.
    sums_name = "SHA256SUMS"
    if sums_name not in assets:
        raise SystemExit("no SHA256SUMS asset in release")
    sums_lines = fetch(assets[sums_name]["browser_download_url"]).decode().splitlines()
    checksums = {}
    for line in sums_lines:
        if not line.strip():
            continue
        digest, name = line.split(None, 1)
        checksums[name.strip().lstrip("*")] = digest

    OUT.mkdir(parents=True, exist_ok=True)
    for target, (triple, _arch) in sorted(TARGETS.items()):
        asset_name = pick_asset([{"name": n} for n in assets], triple)
        real_name = asset_name if asset_name in assets else next(
            n for n in assets if n.startswith(asset_name.rsplit("+", 1)[0]) and n.endswith(triple + "-install_only.tar.gz")
        )
        url = assets[real_name]["browser_download_url"]
        expected = checksums.get(real_name)
        if not expected:
            raise SystemExit(f"no checksum for {real_name}")

        dest = OUT / f"{target}.tar.gz"
        print(f"fetch {real_name} -> {dest.name}")
        data = fetch(url)
        got = hashlib.sha256(data).hexdigest()
        if got != expected:
            raise SystemExit(f"checksum mismatch for {real_name}: {got} != {expected}")
        dest.write_bytes(data)
        print(f"  sha256 OK ({len(data) >> 20} MB)")

    print(f"done: {len(TARGETS)} archives in {OUT}")


if __name__ == "__main__":
    main()
