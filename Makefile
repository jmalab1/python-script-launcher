.PHONY: start stop restart test test-e2e demo

PIDFILE := .server.pid

start:
	@if [ -f $(PIDFILE) ] && kill -0 $$(cat $(PIDFILE)) 2>/dev/null; then \
		echo "Server already running (PID $$(cat $(PIDFILE)))"; \
	else \
		nohup python3 launcher.py > server.log 2>&1 & \
		pid=$$!; \
		sleep 1; \
		if kill -0 $$pid 2>/dev/null; then \
			echo $$pid > $(PIDFILE); \
			echo "Server started (PID $$pid)"; \
		else \
			rm -f $(PIDFILE); \
			echo "Server failed to start — last lines of server.log:"; \
			tail -n 5 server.log 2>/dev/null || true; \
		fi; \
	fi

stop:
	@if [ -f $(PIDFILE) ]; then \
		pid=$$(cat $(PIDFILE)); \
		if kill $$pid 2>/dev/null; then \
			echo "Server stopped"; \
			rm -f $(PIDFILE); \
		elif kill -0 $$pid 2>/dev/null; then \
			echo "Server PID $$pid belongs to another user — stop it with sudo (keeping $(PIDFILE))"; \
		else \
			echo "Server not running (stale PID $$pid)"; \
			rm -f $(PIDFILE); \
		fi; \
	else \
		echo "No PID file found"; \
	fi

restart: stop start

test:
	python3 -m pytest tests/

test-e2e:
	python3 -m pytest tests/e2e/

demo:
	python3 scripts/dev/make_screencast.py
