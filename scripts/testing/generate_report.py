#!/usr/bin/env python3
"""Simulates generating a report."""
import time
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--format", default="pdf", choices=["pdf", "csv", "html"], help="Output format")
parser.add_argument("--output", default="report", help="Output filename")
args = parser.parse_args()

print(f"[generate_report] Creating {args.format} report...")
time.sleep(1)
print(f"[generate_report] Adding charts and tables...")
time.sleep(1)
print(f"[generate_report] Saving as {args.output}.{args.format}")
time.sleep(1)
print(f"[generate_report] Report generated successfully.")
