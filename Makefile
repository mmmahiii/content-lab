.PHONY: infra-up infra-down api worker orch web py-check

infra-up:
	docker compose -f infra/docker-compose.yml up -d

infra-down:
	docker compose -f infra/docker-compose.yml down

api:
	cd apps/api && poetry install && poetry run uvicorn content_lab_api.main:app --reload --port 8000

worker:
	cd apps/worker && poetry install && poetry run dramatiq content_lab_worker.worker

orch:
	cd apps/orchestrator && poetry install && poetry run python -m content_lab_orchestrator.cli run --name world

web:
	pnpm install && pnpm --filter web dev

py-check:
	./scripts/py_check.sh
