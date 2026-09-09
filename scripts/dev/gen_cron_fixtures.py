#!/usr/bin/env python3
"""Generate cron differential fixtures for the Go port.

Runs the real Python implementation (launcher.scheduler) over a battery
of cron expressions and fixed "now" times, recording next_after,
describe_cron and error messages. The Go test (TestCronParity) asserts
the Go port produces identical results, which locks the port to the
original behaviour including DST quirks.

Run from the repo root:  python3 scripts/dev/gen_cron_fixtures.py
Output: internal/scheduler/testdata/cron_fixtures.json

The fixture is computed in UTC so the Go test can pin its zone the same
way (TZ=UTC here, time.Local = time.UTC in the test).
"""

import os
import sys
import time as _time

os.environ["TZ"] = "UTC"
_time.tzset()

from datetime import datetime  # noqa: E402

sys.path.insert(0, str(os.path.dirname(os.path.abspath(__file__)) + "/../.."))
from launcher.scheduler import parse_cron, next_after, describe_cron  # noqa: E402

CRONS = [
    "* * * * *", "*/7 * * * *", "*/7/2 * * * *", "5/10 * * * *",
    "1-5,10-12/2 * * * *", "0 0 * * *", "30 2 * * *", "0 9 * * 1-5",
    "0 9 * * 0,7", "0 9 * * 7", "30 8 15 * *", "0 0 29 2 *",
    "0 12 */3 * *", "59 23 31 12 *", "0 0 * * 6", "15,45 */2 1,15 1-12 1",
    "10/5 * * * *", "8-18/2 * * * *", "0 0 */10 * *", "* 6-18 * * *",
    "0 22 * * 1-5", "5 4 * * 0", "1 0 1 1 *", "0 */6 */2 * *",
    "0 0 1,15 * *", "30 4 1,8,15,22 * *", "0 0 2-30/7 * *",
    "23 0-20/2 * * *", "0 0 1 1 0", "0 0 31 1 *", "45 23 * * 5",
]

INVALID = [
    "", "  ", "0 0", "0 0 0", "x y", "a b c d e", "60 * * * *",
    "0 24 * * *", "0 0 32 * *", "0 0 * 13 *", "0 0 * * 8", "*/0 * * * *",
    "*/-2 * * * *", "1-0 * * * *", "5-3 * * * *", "60-70 * * * *",
    "0 0 31 2 *", "1,,2 * * * *", ", * * * *", "* * * *", "5/ * * * *",
    "0- * * * *", "-5 * * * *", "0 0 * * 07/9",
]

NOWS = [
    "2026-03-08 01:30",   # US spring-forward day
    "2026-11-01 01:30",   # US fall-back day
    "2026-06-15 10:07",
    "2026-12-31 23:59",
    "2026-01-01 00:00",
    "2028-02-28 12:00",   # the day before a leap day
    "2026-02-28 23:30",
]


def main():
    results = []
    for expr in CRONS + INVALID:
        describe = describe_cron(expr)
        for now_text in NOWS:
            now = datetime.strptime(now_text, "%Y-%m-%d %H:%M")
            row = {"cron": expr, "now": now_text, "describe": describe}
            try:
                parse_cron(expr)
            except ValueError as e:
                row["error"] = str(e)
                results.append(row)
                continue
            nxt = next_after(expr, now)
            row["next"] = nxt.strftime("%Y-%m-%d %H:%M") if nxt else None
            results.append(row)
    out = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "../../internal/scheduler/testdata/cron_fixtures.json",
    )
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json_dump = __import__("json").dumps(results, ensure_ascii=False, indent=1)
        f.write(json_dump)
    print(f"wrote {len(results)} fixtures to {os.path.normpath(out)}")


if __name__ == "__main__":
    main()
