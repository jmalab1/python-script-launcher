#!/usr/bin/env bash
# Check-only gofmt gate for the pre-commit framework: fails listing files
# that are not gofmt-clean instead of rewriting them mid-commit. Locates
# the Go toolchain the same way the Makefile does (PATH first, then the
# well-known install spot).
set -e

GO="$(command -v go 2>/dev/null || echo "$HOME/.local/go/bin/go")"
GOFMT="$(dirname "$GO")/gofmt"

UNFORMATTED="$("$GOFMT" -l .)"
if [ -n "$UNFORMATTED" ]; then
	echo "These files are not gofmt-clean:"
	echo "$UNFORMATTED"
	echo "Fix with: make go-fmt"
	exit 1
fi
