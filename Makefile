.PHONY: start stop restart test test-e2e

PIDFILE := .server.pid

start:
	@if [ -f $(PIDFILE) ] && kill -0 $$(cat $(PIDFILE)) 2>/dev/null; then \
		echo "Server already running (PID $$(cat $(PIDFILE)))"; \
	else \
		nohup python3 launcher.py > server.log 2>&1 & echo $$! > $(PIDFILE); \
		echo "Server started (PID $$(cat $(PIDFILE)))"; \
	fi

stop:
	@if [ -f $(PIDFILE) ]; then \
		kill $$(cat $(PIDFILE)) 2>/dev/null && echo "Server stopped" || echo "Server not running"; \
		rm -f $(PIDFILE); \
	else \
		echo "No PID file found"; \
	fi

restart: stop start

test:
	python3 -m pytest tests/

test-e2e:
	python3 -m pytest tests/e2e/
