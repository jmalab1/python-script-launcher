#!/usr/bin/env python3
"""Simulates sending an email notification."""
import time
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--to", default="admin@example.com", help="Recipient email")
parser.add_argument("--subject", default="Task Complete", help="Email subject")
args = parser.parse_args()

print(f"[send_email] Composing email to {args.to}...")
time.sleep(0.5)
print(f"[send_email] Subject: {args.subject}")
time.sleep(0.5)
print(f"[send_email] Sending...")
time.sleep(1)
print(f"[send_email] Email sent successfully.")
