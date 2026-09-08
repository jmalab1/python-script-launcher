# Feature Suggestions

## High Priority

- **Search/filter on History and Audit panels** — filter by name, date range, status, or action type. Lists grow indefinitely and become hard to navigate without this.

## Medium Priority

- **Export/import profiles and workflows** — save as JSON files for sharing between instances or backing up configurations.
- **Environment variable support** — define `KEY=value` pairs on profiles that are passed to the subprocess via `env`.
- **Run scheduling** — cron-like periodic execution for profiles (e.g., "run this script every hour").
- **Concurrent run limits** — configurable cap on how many scripts can run simultaneously.
- **Script timeout** — kill long-running scripts after a configurable duration.

## Low Priority

- **Keyboard shortcuts** — `Ctrl+N` new profile, `Ctrl+R` run selected, `Esc` close modals.
- **Profile grouping** — organize profiles into tags.
- **Template variables** — `{date}`, `{timestamp}`, `{random}` placeholders in argument fields.
- **Workflow conditional steps** — skip a step based on the previous step's output or exit code.
- **Export run output** — save script output to a file from the run modal.
- **Log rotation** — cap `server.log` size or auto-rotate.
- **Browser notifications** — desktop notification when a workflow completes.
- **Confirmation before running** — optional "are you sure?" for profiles with destructive arguments.
