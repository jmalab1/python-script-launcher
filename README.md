# Launch Control

Launch Control is a local web tool for managing and running Python scripts through a browser UI. It ships as a **single compiled binary** with a CPython interpreter built in — no Python installation, no `pip install`, no build step before you run it.

![Launch Control demo](demo/launcher_demo.gif)

## Features

- **Profiles**: Reusable script presets with a name, script path, and arguments. Run with one click.
- **Workflows**: Chain profiles as sequential steps or parallel groups, with configurable error handling.
- **Tags**: Global labels shared by profiles and workflows, each with a pickable color used for chips and filter pills. Apply any number of tags, filter the lists by tag, and manage all tags from one place — deleting a tag simply removes it from the items that use it.
- **Schedules**: Run profiles or workflows automatically on cron-like schedules — every hour, daily at 09:00, weekdays at 08:30, or any 5-field cron expression.
- **Run History**: Full audit log of every run with output capture and status tracking. A run appears here as **Running** as soon as it starts — profile and workflow runs alike — and is updated in place when it finishes. Search and filter by name, status, and date range.
- **Audit**: Complete trail of every profile, workflow, and schedule change. Filter by action, entity type, name, and date range.
- **Server Logs**: Built-in log viewer with live tailing, level highlighting, and text search; the log file rotates automatically.
- **Custom Arguments**: Define typed input fields that appear on profile cards for quick parameter editing.
- **Script Timeout**: Per-profile time limit that kills runaway scripts and marks the run failed.
- **Stop Runs**: Kill a running script or workflow from the run panel; the run is recorded as cancelled with its output so far kept.
- **Output Export**: Download a run's output as a text file from the run panel.
- **Run Panel**: Run output opens in a panel docked to the right side of the screen, sliding in on open and sliding back out on close. Drag the grip pill on its left edge to resize it — the chosen width is remembered for next time. Clicking outside the panel closes it, but clicking another history row just swaps in that run's output. Reopening a still-running run from history switches the panel to live output, so it keeps updating (and its Stop button works) even though the panel was closed meanwhile.
- **Modern UI**: Dark/light theme, drag-to-reorder (editing or re-saving an item keeps its place in the list), responsive layout, terminal-style output viewer. If a run fails to start (for example the script was deleted after the page loaded), the card shows an inline error banner instead of failing silently.

## Quick Start

Grab a binary from `dist/` (built per platform) or build one yourself:

```bash
make go-release-local    # builds dist/launchctl with a bundled Python 3.12
```

Then run it:

```bash
./dist/launchctl
```

Starts at `http://127.0.0.1:8765` on Linux/macOS, detaching into the
background so **closing the terminal does not stop it**. Running the
command again automatically **stops the previous instance and restarts**
(one instance per port — a second `-port` value runs alongside).
`./dist/launchctl -stop` stops it. On Windows it
runs in the foreground and opens the browser automatically, like before.

All state lives in one per-user folder — `~/.local/share/launchctl-data`
on Linux, `~/Library/Application Support/launchctl-data` on macOS,
`%APPDATA%/launchctl-data` on Windows — no matter which copy of the
binary you run or where you launched it from. On first launch the
bundled CPython is extracted into `launchctl-data/runtime/`, so your
scripts run even with no Python installed on the system. Handy flags:

| Flag | Effect |
|---|---|
| (default) | Start detached; a running instance on the same port is stopped and restarted |
| `-stop` | Stop a background instance |
| `-foreground` | Stay attached to the terminal (Ctrl+C quits) |
| `-port N` | Listen on a different port (default 8765) |

## How Script Parameters Work

There are two ways to pass arguments to your scripts.

### Static Arguments

Set fixed arguments that are always sent to the script. In the profile editor, enter one argument per line in the **Arguments** field:

```
--input data.csv
--verbose
--format json
```

These are always appended to the command line when the profile runs. They are not editable at runtime.

### Custom Argument Fields

Define named fields that appear as editable inputs on the profile card. These let you change values at run time without editing the profile.

In the profile editor, click **+ Add Argument Field** to create one. Each field has:

| Field | Description |
|---|---|
| **Flag** | The CLI flag name, e.g. `--name`, `--rows` |
| **Label** | Display label on the card (defaults to the flag name) |
| **Type** | `Text` for string values, `Checkbox` for boolean flags, `Date` for date pickers |
| **Default** | Default value (text fields only) |

When you run the profile, the current values of these fields are passed to the script. For example, given this Python script:

```python
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--name", default="World", help="Name to greet")
parser.add_argument("--count", type=int, default=1, help="Number of greetings")
args = parser.parse_args()

for _ in range(args.count):
    print(f"Hello, {args.name}!")
```

You would create a profile with two custom argument fields:

| Flag | Type | Default |
|---|---|---|
| `--name` | Text | `World` |
| `--count` | Text | `1` |

The profile card then shows text inputs for each, pre-filled with the defaults. Change the values and hit Run.

### Checkbox Arguments

Checkbox fields act as boolean flags. When checked, the flag is included in the command line. When unchecked, it is omitted.

Given a script with a `--verbose` flag:

```python
parser.add_argument("--verbose", action="store_true")
```

Create a custom argument field with flag `--verbose` and type `Checkbox`. When the checkbox is checked on the card, the script receives `--verbose`. When unchecked, it does not.

### Static + Custom Together

You can use both static arguments and custom fields in the same profile. Static arguments are fixed. Custom fields are editable. At runtime, custom field values are placed first, followed by any static arguments:

```
<python runtime> <script> [--custom-field value ...] [static-arg ...]
```

### Arguments in Workflows

When a profile is added to a workflow, its current custom argument values are captured. You can override them per step in the workflow editor without changing the original profile. This lets the same profile run with different parameters in different workflow steps.

## Script Timeouts

Each profile can set a **Timeout (seconds)** in the profile editor — a plain number like `60` or a decimal like `2.5`. Whether the profile is run directly, as a workflow step, or on a schedule, Launch Control kills the script if it is still running after that long. The timed-out run is marked **failed**, and a `Timed out after Ns and was killed` line appears in its output. Leave the field blank to let scripts run indefinitely (the default).

The run panel's **Export** button downloads the run as a timestamped `.txt` file. For a workflow, the file combines the workflow progress log with every step's output, each under its own headed section; for a profile run it is the script's output (with the command that ran).

## Stopping a Run

While a profile or workflow is still running, the run panel shows a **Stop** button next to **Close**. Confirming it kills the running script right away — for a workflow, the current step is killed and the remaining steps are skipped. The run is recorded as **cancelled** (not failed) in Run History, with a `Cancelled by user.` line at the end of its output; output produced before the stop is kept and can still be exported. Cancelled is also an option in the history status filter.

## Scheduling Runs

The **Schedules** panel runs profiles or workflows automatically while Launch Control is running — for example "run this script every hour".

### Creating a Schedule

Click **New Schedule** (or **Edit** on an existing card) and pick:

1. **What should run** — a profile or a workflow (trashed items are not selectable).
2. **Label** (optional) — shown on the schedule card; defaults to the target's name.
3. **Schedule** — either a friendly preset or a custom cron expression, with a live preview of the next few run times.
4. **Enabled** — disabled schedules do nothing until re-enabled.

### Presets

Pick a preset kind and fill in the values — the compiled cron expression and the next few run times are previewed live as you type.

| Preset | Options | Compiles to | Example |
|---|---|---|---|
| **Repeat every...** | any number 1–59 | `*/N * * * *` | every 7 minutes |
| (unit: hours) | any number 1–23 | `0 */N * * *` | every 3 hours |
| (unit: days) | any number 1–31, at a time | `M H */N * *` | every 2 days at 06:30 |
| **Daily at a time** | any HH:MM | `M H * * *` | daily at 09:00 |
| **Weekly on days at a time** | any day combination | `M H * * D,D,...` | Mondays & Fridays at 08:00 |
| **Monthly on a day at a time** | day 1–31, any HH:MM | `M H D * *` | the 15th at 08:30 |

Repeat counts are free number inputs clamped to valid cron ranges (a "minute" repeat can't exceed 59, and so on). Monthly schedules skip months that lack the chosen day (e.g. Feb 30); day repeats count from the 1st of the month.

### Custom Cron

Advanced users can enter any 5-field cron expression:

```
minute hour day-of-month month day-of-week
```

- Fields accept `*`, lists (`1,5`), ranges (`9-17`), and steps (`*/15`, `8-18/2`, `10/5`).
- Day-of-week: `0` and `7` are Sunday, `1`–`6` are Monday–Saturday.
- Classic cron semantics: when both day-of-month and day-of-week are restricted, the schedule fires when **either** matches.

### Behaviour

- Times are **local wall-clock time**, minute granularity. On DST change days a scheduled wall-clock time may be skipped or run twice, like a real cron.
- **Missed runs are skipped**: if Launch Control is not running when a run is due, the next run happens at the next normal occurrence.
- **No overlap**: a schedule will not start a new run while its previous run is still active; the run starts on the next tick once the previous one finishes (ticks are every 5 seconds).
- **Run now** fires a schedule immediately without changing its cadence; the firing is recorded in the **Audit** panel.
- **Duplicate** copies a schedule as `<name> (copy)` with the same cron and target; the copy starts enabled with fresh last-run info and appears in the **Audit** panel.
- Scheduled runs use the profile's stored argument values (as shown on the card) and appear in **Run History** with a "Scheduled" badge. Profile and workflow cards show a clock badge while an enabled schedule exists.
- Moving a profile or workflow to the trash pauses its schedule (the card shows "Target in trash"); restoring resumes it. **Permanently deleting** a target deletes its schedules.
- Schedules can be trashed (moved to a collapsible Trash section), restored, or permanently deleted — just like profiles and workflows. Trashed schedules stop firing and are hidden from the main list and tag filter.
- Schedules inherit the tags of their target profile/workflow. Tag filter pills on the Schedules panel let you narrow the list by inherited tag.

## Searching History and Audit

Both **Run History** panels (Profile and Workflow) and the **Audit** panel have a filter bar above the table:

- **Name search**: case-insensitive substring match, applied as you type.
- **Status** (Run History only): Running, Completed, Failed, or Cancelled.
- **Action / Entity** (Audit only): filter on what happened and to what (including `Run now` firings and `Schedules`).
- **Date range**: From/To day pickers; both ends of the range are inclusive. Run History matches on the run's start time — the same time the **Time** column shows — so a long-running run is grouped under the day it started. Audit matches on when the change happened.

Filters combine (AND), reset the list to page 1, and clear with the **Clear** button. The list request carries them as query parameters: `name`, `status` (history), `action`/`entity` (audit), `since` and `until` (epoch seconds).

## Configuration

The server reads a few settings as flags and environment variables:

| Setting | Default | Description |
|---|---|---|
| `-port` flag | `8765` | Server listen port (bound to 127.0.0.1; `-stop`/`-foreground` also built in) |
| `LAUNCHER_DATA_DIR` | `launchctl-data/` in the OS user-data dir | Where the database, logs, and extracted Python runtime live |
| log rotation | 2 MB, 3 backups | `launchctl-data/server.log` rotates automatically; the **Logs** panel tails it |

Override the data directory for tests, shared locations, or a portable stick:

```bash
LAUNCHER_DATA_DIR=/tmp/demo dist/launchctl -port 9001
```

## Project Structure

```
cmd/launcher/            # Entry point: flags, browser opening, shutdown
assets.go                # Embeds index.html + static/ into the binary
internal/
  api/                   # HTTP routes and handlers (profiles, workflows,
                         #   schedules, runs, history, audit, logs, browse)
  applog/                # Rotating server log with timestamped backups
  compress/              # Gzip responses with an internal cache
  config/                # Settings and data-dir resolution
  ordjson/               # Order-preserving JSON objects (Python-dict parity)
  pythonrt/              # Bundled CPython: extraction and interpreter lookup
  runner/                # Script execution, timeouts, cancel, workflow engine
  scheduler/             # Cron parser, next-run scanner, tick loop
  store/                 # SQLite persistence (legacy *.json migration included)
  web/                   # Embedded-asset serving (index + static)
go.mod / go.sum          # Go module (only pure-Go dependencies)
index.html               # Main SPA shell
static/                  # Frontend assets (Preact components, vendored libs)
scripts/testing/         # Example scripts for exercising the launcher
scripts/dev/             # Dev tooling (runtime fetcher, browser check,
                         #   screencast recorder)
tests/e2e/               # Playwright end-to-end browser tests
data/                    # Runtime data (gitignored)
```

## Example Scripts

The `scripts/testing/` directory holds example scripts for exercising the launcher:

| Script | Purpose | Key Arguments |
|---|---|---|
| `test_script.py` | Basic greeting | `--name` |
| `generate_report.py` | Report generation | `--format`, `--output` |
| `process_data.py` | Data processing | `--input`, `--clean` |
| `fetch_data.py` | Data fetching | `--source`, `--rows` |
| `send_email.py` | Email simulation | `--to`, `--subject` |
| `backup.py` | File backup | `--dir`, `--compress` |
| `unstable_task.py` | Random failures | `--fail-rate` |

## Building From Source

Requires Go 1.24+ (pure-Go dependencies; no cgo). Dev dependency tools for
the e2e suite/demorecorder (Python) live in `requirements-dev.txt`.

| Command | What it does |
|---|---|
| `make go-build` | Dev binary (uses a system `python3` for scripts) |
| `make go-test` | Go unit test suite |
| `make go-fmt` | Format all Go code with gofmt |
| `make test-e2e` | Playwright suite against the built binary |
| `make go-release-local` | Release binary with embedded CPython for this machine |
| `make go-release` | Release binaries for linux, windows, macos (amd64 + arm64) |
| `make start` / `make stop` | Start the server in the background / stop it |
| `make demo` | Record the demo screencast into `demo/` |

## Requirements

A compiled binary needs nothing installed — even Python comes bundled.
Development needs Go (1.24+) for the app itself; the e2e tests and demo
recorder additionally need `pip install -r requirements-dev.txt`.
