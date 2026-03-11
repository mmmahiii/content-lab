# Content Laboratory — Monorepo

Local-first MVP for **ready-to-post reel packages** (MP4 + cover + captions + posting_plan + provenance) with an **Asset Registry** and strict anti-repetition.

## Repo layout
- `apps/api` — FastAPI HTTP API
- `apps/worker` — Dramatiq workers (generation/edit/QA/package steps)
- `apps/orchestrator` — Prefect 2 flows (scheduling + dependency graph)
- `apps/web` — Admin UI (Next.js)
- `packages/shared` — Shared code (Python models + TS types)
- `infra` — Docker Compose (Postgres/Redis/MinIO)
- `docs` — Operating rules + design notes

## Quickstart (local)

Prereqs: Docker Desktop, Python 3.11, Poetry, Node 20+, and pnpm 9.

### 1) Infra
```bash
docker compose -f infra/docker-compose.yml up -d
cp infra/.env.example .env
```

PowerShell equivalent:
```powershell
docker compose -f infra/docker-compose.yml up -d
Copy-Item infra/.env.example .env
```

### 2) Python (API + worker + orchestrator)
Install Poetry (once): https://python-poetry.org/docs/#installation

```bash
cd apps/api && poetry install
cd ../worker && poetry install
cd ../orchestrator && poetry install
```

Run API:
```bash
cd apps/api
poetry run uvicorn content_lab_api.main:app --reload --host 0.0.0.0 --port 8000
```

Run worker:
```bash
cd apps/worker
poetry run dramatiq content_lab_worker.worker
```

Run orchestrator (example flow module):
```bash
cd apps/orchestrator
poetry run python -m content_lab_orchestrator.cli list
```

### 3) Web
```bash
pnpm install
pnpm --filter web dev
```

## Quality gates
- Format: Prettier (TS) / Black (Py)
- Lint: ESLint (TS) / Ruff (Py)
- Types: `tsc --noEmit` / `mypy`
- Tests: Jest/Vitest (TS) + Pytest (Py)
- CI: lint + typecheck + test on PR

Python full checks:
- Unix shells: `./scripts/py_check.sh`
- PowerShell: `./scripts/py_check.ps1`
