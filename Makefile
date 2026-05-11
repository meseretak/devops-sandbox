.PHONY: up down create destroy logs health simulate clean build

SHELL := /bin/bash
ROOT  := $(shell pwd)

# ── Start platform ────────────────────────────────────────────────────────────
up:
	@echo "Starting DevOps Sandbox Platform..."
	@cp -n .env.example .env 2>/dev/null || true
	@docker network create sandbox-net 2>/dev/null || true
	@docker build -t sandbox-app:latest ./app
	@docker run -d --name sandbox-nginx \
		--network sandbox-net \
		-p 80:80 \
		-v $(ROOT)/nginx/nginx.conf:/etc/nginx/nginx.conf:ro \
		-v $(ROOT)/nginx/conf.d:/etc/nginx/conf.d \
		nginx:alpine 2>/dev/null || echo "Nginx already running"
	@docker run -d --name sandbox-api \
		--network sandbox-net \
		-p 8080:8080 \
		-v $(ROOT):/workspace \
		-w /workspace \
		-e PLATFORM_PORT=8080 \
		python:3.12-alpine sh -c "pip install flask gunicorn -q && python platform/api.py" \
		2>/dev/null || echo "API already running"
	@nohup bash platform/cleanup_daemon.sh > logs/cleanup.log 2>&1 &
	@nohup python3 monitor/health_poller.py > logs/poller.log 2>&1 &
	@echo ""
	@echo "✅ Platform is up!"
	@echo "   Nginx:  http://localhost:80"
	@echo "   API:    http://localhost:8080"
	@echo ""

# ── Stop platform ─────────────────────────────────────────────────────────────
down:
	@echo "Stopping platform and destroying all environments..."
	@for f in envs/env-*.json; do \
		[ -f "$$f" ] && bash platform/destroy_env.sh "$$(basename $$f .json)" || true; \
	done
	@docker stop sandbox-nginx sandbox-api 2>/dev/null || true
	@docker rm   sandbox-nginx sandbox-api 2>/dev/null || true
	@pkill -f cleanup_daemon.sh 2>/dev/null || true
	@pkill -f health_poller.py  2>/dev/null || true
	@echo "✅ Platform stopped."

# ── Build app image ───────────────────────────────────────────────────────────
build:
	docker build -t sandbox-app:latest ./app

# ── Create environment ────────────────────────────────────────────────────────
create:
	@read -p "Environment name [sandbox]: " NAME; \
	 read -p "TTL in seconds [1800]: " TTL; \
	 bash platform/create_env.sh "$${NAME:-sandbox}" "$${TTL:-1800}"

# ── Destroy environment ───────────────────────────────────────────────────────
destroy:
ifndef ENV
	$(error ENV is required. Usage: make destroy ENV=env-abc123)
endif
	bash platform/destroy_env.sh $(ENV)

# ── Tail logs ─────────────────────────────────────────────────────────────────
logs:
ifndef ENV
	$(error ENV is required. Usage: make logs ENV=env-abc123)
endif
	@LOG=logs/$(ENV)/app.log; \
	 [ -f "$$LOG" ] || LOG=logs/archived/$(ENV)/app.log; \
	 [ -f "$$LOG" ] && tail -f "$$LOG" || echo "No logs found for $(ENV)"

# ── Health status ─────────────────────────────────────────────────────────────
health:
	@echo "=== Environment Health Status ==="
	@for f in envs/env-*.json; do \
		[ -f "$$f" ] || continue; \
		ID=$$(python3 -c "import json; d=json.load(open('$$f')); print(d['id'])"); \
		NAME=$$(python3 -c "import json; d=json.load(open('$$f')); print(d['name'])"); \
		STATUS=$$(python3 -c "import json; d=json.load(open('$$f')); print(d['status'])"); \
		TTL_LEFT=$$(python3 -c "import json,time; d=json.load(open('$$f')); print(max(0,d['expires_at']-int(time.time())))"); \
		echo "  $$ID ($$NAME) — $$STATUS — TTL: $${TTL_LEFT}s remaining"; \
		HLOG=logs/$$ID/health.log; \
		[ -f "$$HLOG" ] && tail -1 "$$HLOG" | python3 -c "import json,sys; d=json.load(sys.stdin); print('    Last check: HTTP',d['status'],'(',d['latency'],'ms)')" || true; \
	done

# ── Simulate outage ───────────────────────────────────────────────────────────
simulate:
ifndef ENV
	$(error ENV is required. Usage: make simulate ENV=env-abc123 MODE=crash)
endif
ifndef MODE
	$(error MODE is required. Usage: make simulate ENV=env-abc123 MODE=crash)
endif
	bash platform/simulate_outage.sh --env $(ENV) --mode $(MODE)

# ── Clean all state ───────────────────────────────────────────────────────────
clean:
	@echo "Wiping all state, logs, and archives..."
	@for f in envs/env-*.json; do \
		[ -f "$$f" ] && bash platform/destroy_env.sh "$$(basename $$f .json)" 2>/dev/null || true; \
	done
	@rm -rf logs/* envs/*
	@echo "✅ Clean complete."
