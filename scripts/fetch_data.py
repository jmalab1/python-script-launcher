#!/usr/bin/env python3
"""Simulates fetching data from a source."""
import time
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--source", default="api", help="Data source name")
parser.add_argument("--rows", type=int, default=10, help="Number of rows to fetch")
args = parser.parse_args()

print(f"[fetch_data] Connecting to {args.source}...")
time.sleep(1)
print(f"[fetch_data] Fetching {args.rows} rows...")
time.sleep(1)
print(f"[fetch_data] Done. Retrieved {args.rows} records.")
