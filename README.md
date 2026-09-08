# Python Web Launcher

A local, zero-dependency web tool for managing and running Python scripts through a browser UI. No `pip install`, no database, no build step -- just run it.

## Features

- **Profiles**: Reusable script presets with a name, script path, and arguments. Run with one click.
- **Workflows**: Chain profiles as sequential steps or parallel groups, with configurable error handling.
- **Run History**: Full audit log of every run with output capture and status tracking.
- **Custom Arguments**: Define typed input fields that appear on profile cards for quick parameter editing.
- **Modern UI**: Dark/light theme, drag-to-reorder, responsive layout, terminal-style output viewer.

## Quick Start

```bash
python3 launcher.py
```

Opens at `http://127.0.0.1:8765`. On Windows, the browser opens automatically.

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
| **Type** | `Text` for string values, `Checkbox` for boolean flags |
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
<executable> <script> [--custom-field value ...] [static-arg ...]
```

### Arguments in Workflows

When a profile is added to a workflow, its current custom argument values are captured. You can override them per step in the workflow editor without changing the original profile. This lets the same profile run with different parameters in different workflow steps.

## Configuration

All config lives in `launcher/config.py`:

| Option | Default | Description |
|---|---|---|
| `PORT` | `8765` | Server listen port |
| `DATA_DIR` | `data/` | Where JSON data files are stored |

## Project Structure

```
launcher.py              # Entry point
index.html               # Main SPA shell

launcher/                # Python backend
  server.py              # HTTP server, routing, gzip
  config.py              # Port and file paths
  runner.py              # Script execution, workflow engine
  storage.py             # JSON persistence, history
  compress.py            # Gzip compression with caching
  api/                   # API route handlers
    profiles.py          # Profile CRUD, reorder, duplicate
    workflows.py         # Workflow CRUD, reorder, duplicate
    runs.py              # Run execution and polling
    history.py           # History list, detail, delete
    filesystem.py        # Directory browsing, file dialog

static/                  # Frontend assets
  js/                    # Preact components
  vendor/                # Vendored Preact + Tailwind
  fonts/                 # Inter font

scripts/                 # Example Python scripts
tests/                   # pytest suite (dev-only; app stays stdlib-only)
data/                    # Runtime data (gitignored)
```

## Example Scripts

The `scripts/` directory contains demo scripts:

| Script | Purpose | Key Arguments |
|---|---|---|
| `test_script.py` | Basic greeting | `--name` |
| `generate_report.py` | Report generation | `--format`, `--output` |
| `process_data.py` | Data processing | `--input`, `--clean` |
| `fetch_data.py` | Data fetching | `--source`, `--rows` |
| `send_email.py` | Email simulation | `--to`, `--subject` |
| `backup.py` | File backup | `--dir`, `--compress` |
| `unstable_task.py` | Random failures | `--fail-rate` |

## Running Tests

Tests use pytest (a dev-only dependency; the app itself needs nothing installed):

```bash
python3 -m pytest tests/
```

Run a single file or test:

```bash
python3 -m pytest tests/test_workflows.py
python3 -m pytest tests/test_workflow_execute.py -k parallel
```

## Requirements

Python 3.10+ with only the standard library — no packages needed to run the app. Unit tests additionally need pytest (`pip install pytest` or `pip install -r requirements-dev.txt`).
