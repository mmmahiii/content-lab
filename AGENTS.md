# AGENTS.md

## Cursor Cloud specific instructions

### Overview

Content Laboratory is a monorepo for generating ready-to-post social media reel packages. It has four backend Python apps (API, worker, orchestrator, shared lib) managed with Poetry, a Next.js 15 admin UI managed with pnpm, and Docker Compose infrastructure (Postgres 16, Redis 7, MinIO).

### Prerequisites (already in VM snapshot)

- Python 3.11 (from deadsnakes PPA; `python3.11`)
- Poetry (`~/.local/bin/poetry`)
- Node 20+ (via nvm)
- pnpm 9
- Docker CE with fuse-overlayfs + iptables-legacy (for nested container support)

### Starting infrastructure

```bash
sudo nohup dockerd > /tmp/dockerd.log 2>&1 &
sleep 3
sudo docker compose -f infra/docker-compose.yml up -d
```

If `.env` does not exist at repo root, copy it: `cp infra/.env.example .env`

### Running services

See `README.md` "Quickstart (local)" and `docs/RUN_LOCAL.md` for standard commands. Key ports:

| Service | Command | Port |
|---------|---------|------|
| API (FastAPI) | `cd apps/api && poetry run uvicorn content_lab_api.main:app --reload --host 0.0.0.0 --port 8000` | 8000 |
| Worker (Dramatiq) | `cd apps/worker && poetry run dramatiq content_lab_worker.worker` | — |
| Orchestrator | `cd apps/orchestrator && poetry run python -m content_lab_orchestrator.cli run --name world` | — |
| Web (Next.js) | `pnpm --filter web dev` | 3000 |

### Quality gates

- **Python** (per-project): `poetry run ruff check .`, `poetry run black --check .`, `poetry run mypy .`, `poetry run pytest -q`
- **Python repo-wide**: `./scripts/py_check.sh`
- **TypeScript**: `pnpm lint`, `pnpm typecheck`, `pnpm test`

### Gotchas

- Docker daemon must be started manually in the VM (`sudo nohup dockerd > /tmp/dockerd.log 2>&1 &`) before running `docker compose`.
- Poetry virtualenvs use Python 3.11 specifically; if Poetry picks up a different Python, run `poetry env use python3.11` in each project directory.
- The orchestrator test (`apps/orchestrator/tests/test_flow.py`) emits many Pydantic V2 deprecation warnings from Prefect internals — these are harmless.
- The API's `on_event("startup")` triggers a FastAPI deprecation warning in tests — also harmless.
- No Alembic migrations exist yet; database schema is not required for the current scaffold to run.
