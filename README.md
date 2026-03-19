# Content Laboratory — Monorepo

Local-first MVP for **ready-to-post reel packages** (MP4 + cover + captions + posting_plan + provenance) with an **Asset Registry** and strict anti-repetition.

## Repo layout

| Path | Description |
|------|-------------|
| `apps/api` | FastAPI HTTP API (Alembic migrations live here) |
| `apps/worker` | Dramatiq workers (generation / edit / QA / package steps) |
| `apps/orchestrator` | Prefect 2 flows (scheduling + dependency graph) |
| `apps/web` | Admin UI (Next.js 15) |
| `packages/shared` | Shared Python models + TypeScript types |
| `packages/*` | Domain packages — assets, auth, core, creative, editing, features, ingestion, intelligence, outbox, qa, runs, storage |
| `infra/` | Docker Compose (Postgres 16 + Redis 7 + MinIO) and Dockerfiles |
| `docs/` | Operating rules, design notes, architecture docs |
| `scripts/` | Repo-wide quality-gate scripts and utilities |

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Docker (Desktop or CE) | recent | Runs Postgres 16 (pgvector), Redis 7, MinIO |
| Python | 3.11 | Required by all Python apps/packages |
| Poetry | latest | One virtualenv per app — `poetry install` in each |
| Node.js | 24+ | For the Next.js admin UI |
| pnpm | 9 | Workspace package manager for JS side |
| FFmpeg | 6+ recommended | Deterministic media processing (clip normalisation, overlays, packaging). Required by the worker for reel composition. Install: `brew install ffmpeg` (macOS), `sudo apt install ffmpeg` (Ubuntu), `winget install ffmpeg` or `choco install ffmpeg` (Windows). |

## Quickstart (local)

> **TL;DR** — `cp infra/.env.example .env && make infra-up && make migrate && make api`
>
> See `docs/RUN_LOCAL.md` for the full walkthrough.

### 1. Environment variables

```bash
cp infra/.env.example .env          # Bash / macOS / Linux
```

```powershell
Copy-Item infra/.env.example .env   # PowerShell
```

The `.env` file is read by Docker Compose **and** by `packages/shared/py` (via `pydantic-settings`). See `infra/.env.example` for the full list of variables.

### 2. Infrastructure (Postgres + Redis + MinIO)

```bash
make infra-up
# or: docker compose -f infra/docker-compose.yml up -d
```

### 3. Database migrations

```bash
make migrate
# or: cd apps/api && poetry run alembic upgrade head
```

### 4. Python apps (API + worker + orchestrator)

Install Poetry (once): <https://python-poetry.org/docs/#installation>

```bash
# Install all Python dependencies
make py-install

# Run individual services
make api          # FastAPI on :8000
make worker       # Dramatiq worker
make orch         # Orchestrator CLI
```

Or run them manually:

```bash
cd apps/api && poetry install && poetry run uvicorn content_lab_api.main:app --reload --host 0.0.0.0 --port 8000
cd apps/worker && poetry install && poetry run dramatiq content_lab_worker.worker
cd apps/orchestrator && poetry install && poetry run python -m content_lab_orchestrator.cli run --name world
```

### 5. Web (Next.js admin UI)

```bash
make web
# or: pnpm install && pnpm --filter web dev
```

The admin UI runs on <http://localhost:3000>.

## MVP smoke path

The intended startup order for a full local session:

```
1. infra-up        →  Postgres, Redis, MinIO healthy
2. migrate         →  DB schema up to date
3. api             →  FastAPI accepting requests on :8000
4. worker          →  Dramatiq consuming tasks from Redis
5. orchestrator    →  Prefect flows scheduling work
6. web             →  Admin UI on :3000 talking to the API
```

Run them all in separate terminals, or use the Docker full-stack mode:

```bash
make infra-app
# or: docker compose -f infra/docker-compose.yml --profile app up -d --build
```

## Quality gates

| Area | Format | Lint | Types | Tests |
|------|--------|------|-------|-------|
| Python | `ruff format` | `ruff check` | `mypy` | `pytest` |
| TypeScript | `prettier` | `eslint` | `tsc --noEmit` | `vitest` |

Run all Python checks at once:

```bash
make py-check
# or: ./scripts/py_check.sh (Bash) / ./scripts/py_check.ps1 (PowerShell)
```

Run TypeScript checks:

```bash
pnpm lint && pnpm typecheck && pnpm test
```

## Database

Migrations are managed by Alembic under `apps/api/migrations/`.

```bash
make migrate
# or: cd apps/api && poetry run alembic upgrade head
```

## Docker (full stack)

Infra only (Postgres + Redis + MinIO):

```bash
make infra-up
```

Everything including app services (API, worker, orchestrator):

```bash
make infra-app
```

Tear down:

```bash
make infra-down
```

## Make targets

Run `make help` for the full list. Key targets:

| Target | Description |
|--------|-------------|
| `infra-up` | Start Postgres, Redis, MinIO |
| `infra-down` | Stop and remove infra containers |
| `infra-app` | Start infra + app services (Docker build) |
| `migrate` | Run Alembic migrations |
| `py-install` | `poetry install` in all Python apps |
| `api` | Run the FastAPI dev server on :8000 |
| `worker` | Run the Dramatiq worker |
| `orch` | Run the orchestrator CLI |
| `web` | Install JS deps and run Next.js dev server on :3000 |
| `py-check` | Repo-wide Python format + lint + typecheck + tests |
