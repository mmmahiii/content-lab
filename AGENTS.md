# AGENTS.md

Instructions for **AI coding agents** and automation (Cursor Cloud, local Cursor, CI helpers). Humans can use this as a quick orientation too; full local setup is in `README.md` and `docs/RUN_LOCAL.md`.

## Cursor Cloud specific instructions

### Overview

Content Laboratory is a monorepo for generating ready-to-post social media reel packages. It has four backend Python apps (API, worker, orchestrator, shared lib) managed with Poetry, a Next.js 15 admin UI managed with pnpm, and Docker Compose infrastructure (Postgres 16, Redis 7, MinIO).

### Repository map

| Path | Role |
|------|------|
| `apps/api` | FastAPI HTTP API; Alembic migrations live here |
| `apps/worker` | Dramatiq workers (generation, edit, QA, packaging) |
| `apps/orchestrator` | Prefect 2 flows (scheduling, dependency graph) |
| `apps/web` | Admin UI (Next.js 15) |
| `packages/shared` | Shared Python models and TypeScript types |
| `packages/*` | Domain libraries (assets, auth, core, creative, editing, features, ingestion, intelligence, outbox, qa, runs, storage) |
| `infra/` | Docker Compose and Dockerfiles |
| `docs/` | Architecture and runbooks |
| `scripts/` | Bootstrap, scaffold compat, repo-wide `py_check`, smoke scripts |

Repo-wide Python quality checks iterate **apps** and **packages** paths defined in `./scripts/py_check.sh` (not every folder is a standalone Poetry project; `packages/shared/py` is the shared package layout).

### Prerequisites (already in VM snapshot)

- Python 3.11 (from deadsnakes PPA; `python3.11`)
- Poetry (`~/.local/bin/poetry`)
- Node 24+ (via nvm)
- pnpm 9
- Docker CE with fuse-overlayfs + iptables-legacy (for nested container support)

**Local / non-VM:** FFmpeg 6+ is recommended for deterministic media work; the worker needs FFmpeg for reel composition. See `README.md` prerequisites.

### Starting infrastructure

```bash
sudo nohup dockerd > /tmp/dockerd.log 2>&1 &
sleep 3
sudo docker compose -f infra/docker-compose.yml up -d
```

If `.env` does not exist at repo root, copy it: `cp infra/.env.example .env`

### Running services

See `README.md` "Quickstart (local)" and `docs/RUN_LOCAL.md` for standard commands. From repo root, `Makefile` targets mirror the common flows:

| Goal | Make target |
|------|-------------|
| Infra only | `make infra-up` |
| Migrations | `make migrate` |
| Install all Python apps | `make py-install` |
| API / worker / orchestrator / web | `make api`, `make worker`, `make orch`, `make web` |
| Repo-wide Python gates | `make py-check` |

Key ports:

| Service | Command | Port |
|---------|---------|------|
| API (FastAPI) | `cd apps/api && poetry run uvicorn content_lab_api.main:app --reload --host 0.0.0.0 --port 8000` | 8000 |
| Worker (Dramatiq) | `cd apps/worker && poetry run dramatiq content_lab_worker.worker` | — |
| Orchestrator | `cd apps/orchestrator && poetry run python -m content_lab_orchestrator.cli run --name world` | — |
| Web (Next.js) | `pnpm --filter web dev` | 3000 |

**API health via background job (Windows):** From repo root run `powershell -NoProfile -File scripts/api-health-smoke.ps1`. It uses a **free ephemeral port** and sets `apps/api` inside the job. Avoid pasting `Start-Job { uvicorn … --port 8000 }` plus `Invoke-RestMethod http://127.0.0.1:8000/health`: if something else already listens on 8000, the request hits that process (often HTTP 500), not your job. Use `pwsh` only if PowerShell 7+ is installed (`pwsh` is not the same as the `pwsh` PyPI package).

### Cloud bootstrap automation

Cloud agents bootstrap the VM through `.cursor/environment.json`, which runs:

```bash
bash scripts/bootstrap-cloud-env.sh
```

That script ensures Docker nested-runtime compatibility (`fuse-overlayfs` +
`iptables-legacy`), Python 3.11, Poetry, Node.js 24 (via nvm), pnpm 9, `.env`
provisioning, scaffold compatibility layout, and workspace `pnpm install`.

### Scaffold verification

Cursor Cloud's scaffold check expects `minio-create-bucket` and `packages/*/py` paths. This repo provides compatibility:

- **Docker Compose**: `minio-create-bucket` is an alias for `minio-init` (same behavior).
- **packages/*/py**: Run `bash ./scripts/ensure-scaffold-compat.sh` (Linux) or `pwsh -File scripts/ensure-scaffold-compat.ps1` (Windows) to create the layout before verification. Cloud agents run this automatically from `scripts/bootstrap-cloud-env.sh` via `.cursor/environment.json`.

To run the full scaffold check (infra, installs, lint, format, typecheck, tests, Docker build, API health, orchestrator smoke):

```bash
# From repo root (Linux)
./scripts/ensure-scaffold-compat.sh && pwsh -File scripts/verify-scaffold.ps1
```

```powershell
# Windows PowerShell
.\verify.ps1 # or: .\scripts\verify-scaffold.ps1
```

### Quality gates

- **Python** (per-project): `poetry run ruff check .`, `poetry run ruff format --check .`, `poetry run mypy .`, `poetry run pytest -q`
- **Python repo-wide**: `./scripts/py_check.sh` or `make py-check`
- **TypeScript**: `pnpm lint`, `pnpm typecheck`, `pnpm test`

### Gotchas

- Docker daemon must be started manually in the VM (`sudo nohup dockerd > /tmp/dockerd.log 2>&1 &`) before running `docker compose`.
- Poetry virtualenvs use Python 3.11 specifically; if Poetry picks up a different Python, run `poetry env use python3.11` in each project directory.
- Do not default to "reinstall dependencies". Agents should only suggest dependency reinstallation when there is clear evidence it addresses the specific failure.
- The orchestrator test (`apps/orchestrator/tests/test_flow.py`) emits many Pydantic V2 deprecation warnings from Prefect internals — these are harmless.
- The API's `on_event("startup")` triggers a FastAPI deprecation warning in tests — also harmless.
- Alembic migrations live in `apps/api/migrations/`. Run `cd apps/api && poetry run alembic upgrade head` after infra is up.
- Docker Compose app services (API, worker, orchestrator) use the `app` profile: `docker compose -f infra/docker-compose.yml --profile app up -d --build`.

### Multi-agent worktree workflow

For parallel AI task execution, use one Git worktree per task branch and a dedicated merge chat on `main`.

- Workflow guide: `docs/WORKTREE_WORKFLOW.md`
- Prompt templates (task + merge): `docs/worktree-prompts.md`
- Smoke-check: `powershell -File scripts/verify-worktree-workflow.ps1` (from repo root)
- Worktree creation scripts: `scripts/worktree-spawn.ps1` and `scripts/worktree-spawn.sh`

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
