#!/usr/bin/env python3
"""Example script to test the launcher."""
import sys
import time
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--name", default="World", help="Name to greet")
args = parser.parse_args()

print(f"Hello, {args.name}!")
print(f"Arguments: {sys.argv[1:]}")
print("Starting work...")
for i in range(5):
    print(f"  Step {i+1}/5 complete")
    time.sleep(0.5)
print("Done!")
