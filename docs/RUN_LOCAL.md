# Running locally

## Infra
```bash
docker compose -f infra/docker-compose.yml up -d
```

If you need local env vars:
- Bash: `cp infra/.env.example .env`
- PowerShell: `Copy-Item infra/.env.example .env`

Services:
- Postgres: `localhost:5432`
- Redis: `localhost:6379`
- MinIO: `localhost:9000` (console `localhost:9001`)

## Python apps
### API
```bash
cd apps/api
poetry install
poetry run uvicorn content_lab_api.main:app --reload --port 8000
```

### Worker
```bash
cd apps/worker
poetry install
poetry run dramatiq content_lab_worker.worker
```

### Orchestrator
```bash
cd apps/orchestrator
poetry install
poetry run python -m content_lab_orchestrator.cli list
```

## Web
```bash
pnpm install
pnpm --filter web dev
```

## Full Python checks
- Bash: `./scripts/py_check.sh`
- PowerShell: `./scripts/py_check.ps1`
