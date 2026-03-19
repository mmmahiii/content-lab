.PHONY: help infra-up infra-down infra-app migrate py-install api worker orch web py-check

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ── Infrastructure ───────────────────────────────────────────────────

infra-up: ## Start Postgres, Redis, MinIO
	docker compose -f infra/docker-compose.yml up -d

infra-down: ## Stop and remove infra containers
	docker compose -f infra/docker-compose.yml down

infra-app: ## Start infra + app services (Docker build)
	docker compose -f infra/docker-compose.yml --profile app up -d --build

# ── Database ─────────────────────────────────────────────────────────

migrate: ## Run Alembic migrations (apps/api)
	cd apps/api && poetry run alembic upgrade head

# ── Python install ───────────────────────────────────────────────────

py-install: ## poetry install in all Python apps
	cd apps/api && poetry install
	cd apps/worker && poetry install
	cd apps/orchestrator && poetry install

# ── Services ─────────────────────────────────────────────────────────

api: ## Run FastAPI dev server on :8000
	cd apps/api && poetry install && poetry run uvicorn content_lab_api.main:app --reload --host 0.0.0.0 --port 8000

worker: ## Run Dramatiq worker
	cd apps/worker && poetry install && poetry run dramatiq content_lab_worker.worker

orch: ## Run orchestrator CLI
	cd apps/orchestrator && poetry install && poetry run python -m content_lab_orchestrator.cli run --name world

web: ## Install JS deps and run Next.js dev on :3000
	pnpm install && pnpm --filter web dev

# ── Quality gates ────────────────────────────────────────────────────

py-check: ## Repo-wide Python format + lint + typecheck + tests
	./scripts/py_check.sh
