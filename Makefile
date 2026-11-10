# fihi-chifae — Makefile (enterprise, POSIX, Windows Git Bash compatible)
# Usage: make <target>  |  make help
# Requires: python (3.10+), pip, git, docker (compose v2). Optional: railway CLI

PY            ?= python
PIP           ?= $(PY) -m pip
PORT          ?= 8000
HOST          ?= 0.0.0.0

.DEFAULT_GOAL := help
.PHONY: help install launch dev up down logs ps test lint format format-check security audit bandit pip-audit clean docker-build docker-scan deploy deploy-railway backup perf

help: ## Show this help
	@echo "fihi-chifae — available targets:"
	@$(PY) -c "import re, pathlib; print('\n'.join(re.findall(r'^([a-zA-Z0-9_.-]+):.*?## (.+)', pathlib.Path('Makefile').read_text(encoding='utf-8'), re.M)))" 2>nul || grep -E '^[a-zA-Z0-9_.-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ── setup ───────────────────────────────────────────────────────────────
install: ## Install runtime + dev deps (venv recommended)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt
	@echo "✔ deps installed"

# ── launch ──────────────────────────────────────────────────────────────
up: ## Start the whole stack (frontend, backend, mysql, storage, search, fluentd) -> http://localhost:8080
	@test -f .env || (cp .env.example .env && echo "created .env from .env.example: set its passwords/keys")
	docker compose up -d --build

down: ## Stop the stack (data volumes are kept)
	docker compose down

logs: ## Collected log files (Fluentd), newest backend lines
	docker compose exec fluentd sh -c 'ls /fluentd/log; zcat /fluentd/log/docker.*backend*/*.gz 2>/dev/null | tail -20'

ps: ## Stack status + memory per container
	docker compose ps
	docker stats --no-stream --format "table {{.Name}}	{{.MemUsage}}	{{.CPUPerc}}"

launch: ## Launch the backend alone (needs MySQL, see .env)
	@echo "→ http://$(HOST):$(PORT)  (Ctrl+C to stop)"
	$(PY) server.py --host $(HOST) --port $(PORT)

dev: ## Launch the backend and open the browser
	$(PY) server.py --host $(HOST) --port $(PORT) --open

# ── quality ─────────────────────────────────────────────────────────────
lint: ## Lint (ruff)
	ruff check app server.py docker-entrypoint.py

format: ## Auto-format (black + ruff --fix)
	black app server.py tests
	ruff check --fix app server.py || true

format-check: ## Check formatting without modifying
	black --check app server.py tests
	ruff check app server.py

test: ## Run tests against the compose MySQL/Garage/Meilisearch (each test deletes what it creates)
	$(PY) -m pytest -q --cov=app --cov-report=term-missing

security: bandit pip-audit ## Run all security checks

bandit: ## Bandit SAST
	bandit -r app -c pyproject.toml 2>/dev/null || bandit -r app --severity-level medium --confidence-level medium || true

pip-audit: ## pip-audit for known CVEs
	pip-audit --desc 2>/dev/null || echo "pip-audit: no fixable CVEs or audit skipped"

audit: pip-audit

# ── performance ─────────────────────────────────────────────────────────
perf: ## Load test the whole stack (USERS="5 100 1000" DURATION=60) -> perf-results/report.html
	$(PIP) install -q -r perf/requirements.txt
	PERF_USERS="$${USERS:-5 100 1000}" PERF_DURATION="$${DURATION:-60}" bash perf/run.sh

# ── docker ──────────────────────────────────────────────────────────────
docker-build: ## Build the six images (docker compose)
	docker compose build

docker-scan: ## Trivy scan of the six images (if trivy installed)
	for img in $$(docker compose config --images); do trivy image --severity HIGH,CRITICAL $$img || exit 1; done 2>/dev/null || echo "install trivy: https://aquasecurity.github.io/trivy"

# ── deploy ──────────────────────────────────────────────────────────────
deploy: deploy-railway ## Default deploy = Railway

deploy-railway: ## Deploy to Railway (railway login && railway link); SERVICES="backend frontend"
	for svc in $${SERVICES:-backend frontend}; do railway up --service $$svc || exit 1; done

backup: ## Download a backup zip from production (needs URL and a logged-in COOKIE=fc_session=...)
	@if [ -z "$(URL)" ] || [ -z "$(COOKIE)" ]; then echo "usage: make backup URL=https://... COOKIE=fc_session=..."; else mkdir -p backups && curl -fsS -H "Cookie: $(COOKIE)" "$(URL)/api/v1/admin/backup" -o backups/fihi-chifae-$$(date +%Y%m%d-%H%M).zip && echo "✔ saved in backups/"; fi

# ── clean ───────────────────────────────────────────────────────────────
clean: ## Remove caches, db journal, build artifacts
	@echo "cleaning..."
	@$(PY) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in ['__pycache__','app/__pycache__','.pytest_cache','htmlcov','build','dist','.ruff_cache','.playwright-mcp']]; import pathlib; [p.unlink(missing_ok=True) for p in pathlib.Path('.').glob('*.pyc')]"
	@echo "done"
