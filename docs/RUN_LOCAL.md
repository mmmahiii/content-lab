# Running locally

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Docker (Desktop or CE) | recent | <https://docs.docker.com/get-docker/> |
| Python | 3.11 | `deadsnakes` PPA (Ubuntu), <https://python.org> (other) |
| Poetry | latest | <https://python-poetry.org/docs/#installation> |
| Node.js | 24+ | <https://nodejs.org> or `nvm install 24` |
| pnpm | 9 | `corepack enable && corepack prepare pnpm@9 --activate` |
| FFmpeg | 6+ recommended | See [FFmpeg troubleshooting](#ffmpeg) below |

## 1. Environment variables

Copy the example env to the repo root. This file is loaded by Docker Compose
and by the shared Python settings module (`packages/shared/py` via
`pydantic-settings`).

```bash
cp infra/.env.example .env          # Bash / macOS / Linux
```

```powershell
Copy-Item infra/.env.example .env   # PowerShell
```

See `infra/.env.example` for the full variable list and comments.

## 2. Infrastructure

Start Postgres 16 (with pgvector), Redis 7, and MinIO:

```bash
make infra-up
# or: docker compose -f infra/docker-compose.yml up -d
```

Services exposed locally:

| Service | Port | Notes |
|---------|------|-------|
| Postgres | 5433 | User `contentlab`, DB `contentlab` (host port; avoids local Postgres on 5432) |
| Redis | 6379 | Default DB 0 |
| MinIO API | 9000 | Credentials in `.env` |
| MinIO Console | 9001 | Web UI for browsing buckets |

The `minio-init` service automatically creates the `content-lab` bucket on
first startup.

## 3. Database migrations

Run Alembic migrations (managed under `apps/api/migrations/`):

```bash
make migrate
# or: cd apps/api && poetry run alembic upgrade head
```

## 4. Python apps

### Install dependencies

```bash
make py-install
```

This runs `poetry install` in `apps/api`, `apps/worker`, and
`apps/orchestrator`.

### API (FastAPI)

```bash
make api
# or: cd apps/api && poetry run uvicorn content_lab_api.main:app --reload --host 0.0.0.0 --port 8000
```

Runs on <http://localhost:8000>. Interactive docs at `/docs`.

### Worker (Dramatiq)

```bash
make worker
# or: cd apps/worker && poetry run dramatiq content_lab_worker.worker
```

Consumes tasks from Redis. Requires FFmpeg on `$PATH` for media processing
steps.

### Orchestrator (Prefect 2)

```bash
make orch
# or: cd apps/orchestrator && poetry run python -m content_lab_orchestrator.cli run --name world
```

List available flows:

```bash
cd apps/orchestrator && poetry run python -m content_lab_orchestrator.cli list
```

## 5. Web (Next.js admin UI)

```bash
make web
# or: pnpm install && pnpm --filter web dev
```

Runs on <http://localhost:3000>.

## 6. Full Python checks

```bash
make py-check
# or: ./scripts/py_check.sh   (Bash)
# or: ./scripts/py_check.ps1  (PowerShell)
```

This runs `ruff check`, `ruff format --check`, `mypy`, and `pytest` across all
Python apps.

## MVP smoke path

The intended order for bootstrapping a full local session:

```
1. cp infra/.env.example .env      →  environment configured
2. make infra-up                   →  Postgres, Redis, MinIO healthy
3. make migrate                    →  DB schema up to date
4. make api                        →  FastAPI on :8000
5. make worker                     →  Dramatiq consuming from Redis
6. make orch                       →  Prefect orchestrator running
7. make web                        →  Admin UI on :3000
```

Steps 4–7 each need their own terminal. Alternatively, run everything in
Docker:

```bash
make infra-app
# or: docker compose -f infra/docker-compose.yml --profile app up -d --build
```

## Real Manual Reel Smoke

Run the end-to-end one-reel happy path with:

```powershell
powershell -NoProfile -File scripts/manual-smoke-reel.ps1
```

This script creates or reuses the test org/page, upserts policy, creates a
reel family and generated reel, queues the real trigger route, runs the real
`process_reel` flow with the queued `run_id`, and verifies Postgres, MinIO,
and outbox state.

Before running it:

- infra must already be up;
- Alembic migrations must already be applied;
- the API must already be running on `http://127.0.0.1:8000`;
- `.env` must contain a real `RUNWAY_API_KEY`;
- `ffmpeg` must be available on `PATH`.

## Docker (full stack)

| Mode | Command |
|------|---------|
| Infra only | `make infra-up` |
| Infra + apps | `make infra-app` |
| Tear down | `make infra-down` |

## Troubleshooting

### FFmpeg

FFmpeg is used by the worker for deterministic media processing (clip
normalisation, overlays, cover generation, packaging). It must be available on
`$PATH`.

**Install:**

| OS | Command |
|----|---------|
| macOS (Homebrew) | `brew install ffmpeg` |
| Ubuntu / Debian | `sudo apt update && sudo apt install ffmpeg` |
| Windows (winget) | `winget install ffmpeg` |
| Windows (Chocolatey) | `choco install ffmpeg` |

**Verify:** `ffmpeg -version` should print version info.

If you see `ffmpeg: command not found` after installing, make sure the install
directory is on your system `PATH`.

### Docker daemon not starting

On VMs or WSL, the Docker daemon may need manual start:

```bash
sudo nohup dockerd > /tmp/dockerd.log 2>&1 &
sleep 3
```

### Poetry picks wrong Python version

Force Poetry to use 3.11:

```bash
poetry env use python3.11
```

Run this in each project directory (`apps/api`, `apps/worker`,
`apps/orchestrator`).

### Pydantic V2 deprecation warnings

Known Pydantic V2 deprecation warnings from Prefect internals are filtered in
the orchestrator pytest configuration so test output stays readable. If these
warnings reappear after a dependency upgrade, review the filters in
`apps/orchestrator/pyproject.toml`.

### FastAPI startup deprecation warning

The API's `on_event("startup")` triggers a FastAPI deprecation warning in
tests. This is harmless.

### MinIO bucket not created

If the `content-lab` bucket is missing, the `minio-init` container may have
failed. Check with:

```bash
docker compose -f infra/docker-compose.yml logs minio-init
```

Recreate it manually:

```bash
docker compose -f infra/docker-compose.yml up minio-init
```
