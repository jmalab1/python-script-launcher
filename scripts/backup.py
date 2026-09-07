#!/usr/bin/env python3
"""Simulates backing up files."""
import time
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--dir", default="/data", help="Directory to backup")
parser.add_argument("--compress", action="store_true", help="Compress backup")
args = parser.parse_args()

print(f"[backup] Scanning {args.dir}...")
time.sleep(1)
print(f"[backup] Copying files...")
time.sleep(1)
if args.compress:
    print(f"[backup] Compressing...")
    time.sleep(1)
print(f"[backup] Backup complete.")
