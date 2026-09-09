# Demo script that needs a third-party package (requests).
# On the bundled runtime it fails with ModuleNotFoundError;
# once the Settings page points at /tmp/opencode/pydemo/venv it runs.
import sys
from importlib.metadata import version

import requests
# flask is NOT installed system-wide (Ubuntu's /usr/bin/python3 has only
# requests), so this exact line is what fails without the venv runtime.
import flask

URL = "https://httpbin.org/get"


def main():
    print("python:", sys.version.split()[0])
    print("requests:", requests.__version__)
    print("flask:", version("flask"))

    resp = requests.get(URL, timeout=10)
    resp.raise_for_status()

    origin = resp.json().get("origin", "unknown")
    print("fetched", URL, "-> your public IP is", origin)


if __name__ == "__main__":
    main()
