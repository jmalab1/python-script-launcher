#!/usr/bin/env python3
"""Simulates processing/cleaning data."""
import time
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--input", default="data.csv", help="Input file")
parser.add_argument("--clean", action="store_true", help="Run cleaning step")
args = parser.parse_args()

print(f"[process_data] Reading {args.input}...")
time.sleep(1)
if args.clean:
    print("[process_data] Cleaning data...")
    time.sleep(1)
print("[process_data] Transforming rows...")
time.sleep(1)
print("[process_data] Processing complete.")
