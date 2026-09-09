.PHONY: start stop restart go-build go-test go-fmt test test-e2e demo fetch-runtimes go-release go-release-local go-clean

# Find the Go toolchain: the user's PATH if it has one, otherwise the
# well-known install locations this repo uses (~/.local/go from the
# official tarball). Keeps make working in shells that never sourced
# .bashrc.
GO := $(shell command -v go 2>/dev/null || echo $(HOME)/.local/go/bin/go)
GOOS_TARGETS := linux-amd64 linux-arm64 windows-amd64 macos-amd64 macos-arm64

# start/stop go through the binary's built-in detach mode: it starts
# itself in the background and survives the terminal closing.
start:
	@if [ ! -x dist/launchctl ]; then $(MAKE) -s go-build; fi
	@if [ ! -x dist/launchctl ]; then \
		echo "Build failed - is Go on PATH? (~/.local/go/bin if installed via this repo)"; \
		exit 1; \
	fi
	@dist/launchctl -port 8765

stop:
	@dist/launchctl -stop

restart: stop start

# Go unit tests (the backend's test suite).
go-test:
	$(GO) test ./...

# Format all Go code with gofmt (ships with the Go toolchain, so this
# needs no extra install). Uses `go fmt` so it finds the toolchain the
# same way the other targets do.
go-fmt:
	$(GO) fmt ./...

# Alias so the old habit still works.
test: go-test

# Playwright end-to-end tests against the compiled server.
test-e2e:
	python3 -m pytest tests/e2e/

demo:
	python3 scripts/dev/make_screencast.py

# --- Go build targets ---
# Development build: no embedded Python runtime; user scripts run with a
# python3/python found on PATH.
go-build:
	$(GO) build -o dist/launchctl ./cmd/launcher

# Pull the CPython archives release builds embed (see
# scripts/dev/fetch_runtimes.py).
fetch-runtimes:
	python3 scripts/dev/fetch_runtimes.py

go-clean:
	rm -rf dist internal/pythonrt/runtime.tar.gz

# Copy each platform's runtime archive into the embed slot, build a
# tagged binary for it, then put the next one in place.
go-release: fetch-runtimes go-test
	@set -e; for target in $(GOOS_TARGETS); do \
		os=$${target%%-*}; arch=$${target#*-}; \
		goos=$$(case $$os in linux) echo linux;; windows) echo windows;; macos) echo darwin;; esac); \
		goarch=$$arch; \
		cp build/runtimes/$$target.tar.gz internal/pythonrt/runtime.tar.gz; \
		echo "building dist/launchctl-$$os-$$arch"; \
		CGO_ENABLED=0 GOOS=$$goos GOARCH=$$goarch \
			$(GO) build -trimpath -ldflags "-s -w" -tags embedded \
			-o dist/launchctl-$$os-$$arch ./cmd/launcher; \
	done
	@rm -f internal/pythonrt/runtime.tar.gz

# Build one release binary with the embedded runtime, for the machine
# we are on.
go-release-local: fetch-runtimes
	@set -e; os=$$(case $$(uname -s) in Darwin) echo macos;; *) echo linux;; esac); \
	arch=$$(case $$(uname -m) in aarch64|arm64) echo arm64;; *) echo amd64;; esac); \
	cp build/runtimes/$$os-$$arch.tar.gz internal/pythonrt/runtime.tar.gz; \
	$(GO) build -trimpath -ldflags "-s -w" -tags embedded -o dist/launchctl ./cmd/launcher; \
	rm -f internal/pythonrt/runtime.tar.gz;
