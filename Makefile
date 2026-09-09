.PHONY: start stop restart go-build go-test go-fmt go-sec hooks test test-e2e demo fetch-runtimes go-release go-release-local go-clean

# Find the Go toolchain: the user's PATH if it has one, otherwise the
# well-known install locations this repo uses (~/.local/go from the
# official tarball). Keeps make working in shells that never sourced
# .bashrc.
GO := $(shell command -v go 2>/dev/null || echo $(HOME)/.local/go/bin/go)

# Same trick as GO: use gosec from PATH, else the well-known ~/go/bin
# spot that `go install` puts it in.
GOSEC := $(shell command -v gosec 2>/dev/null || echo $(HOME)/go/bin/gosec)
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

# Security scan with gosec (see GOSEC above for where it is found). The
# `! -x` guard fails with a friendly message instead of make complaining
# about a missing command. gosec shells out to `go list`, so the Go
# toolchain found by GO must be on PATH too — otherwise gosec silently
# scans zero packages.
go-sec:
	@if [ ! -x "$(GOSEC)" ]; then \
		echo "gosec not found - install with:"; \
		echo "  go install github.com/securego/gosec/v2/cmd/gosec@latest"; \
		exit 1; \
	fi
	PATH="$$(dirname "$(GO)"):$${PATH}" $(GOSEC) -quiet ./...

# The pre-commit framework runs gofmt, gosec and pytest before every
# commit (see .pre-commit-config.yaml). Installs the tool first if pip
# can reach it; `pre-commit install` wires git to run it.
hooks:
	python3 -m pip install --user --break-system-packages -q -r requirements-dev.txt
	python3 -m pre_commit install

# Alias so the old habit still works.
test: go-test

# Playwright end-to-end tests against the compiled server. Needs the
# Chromium driver installed once: go run github.com/mxschmitt/playwright-go/cmd/playwright install chromium
test-e2e:
	$(GO) test -tags e2e -v ./tests/e2e

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
