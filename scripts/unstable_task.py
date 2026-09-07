#!/usr/bin/env python3
"""Simulates a task that might fail randomly."""
import time
import random
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--fail-rate", type=float, default=0.3, help="Chance of failure (0-1)")
args = parser.parse_args()

print("[unstable_task] Starting risky operation...")
time.sleep(1)

if random.random() < args.fail_rate:
    print("[unstable_task] ERROR: Operation failed!")
    exit(1)

print("[unstable_task] Operation completed successfully.")
