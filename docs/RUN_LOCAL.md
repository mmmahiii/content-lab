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

## One-command console startup

If you want the system to boot the full stack and open the operator console for you, run:

```powershell
powershell -NoProfile -File .\open-console.ps1
```

Or:

```powershell
pnpm run console:open
```

This launcher will:

1. ensure `.env` exists;
2. start Postgres, Redis, MinIO, and bucket init;
3. run Alembic migrations;
4. start API, worker, orchestrator, and web in Docker;
5. wait until `http://127.0.0.1:8000/health` and `http://127.0.0.1:3000` are ready;
6. open the web console in your browser.

The first run may take a while because Docker has to build the app images once.
After that, the launcher reuses those images by default so opening the console is
much faster. If you want to rebuild after changing Dockerfiles or app
dependencies, use:

```powershell
powershell -NoProfile -File .\open-console.ps1 -Rebuild
```

Stop the stack with:

```powershell
powershell -NoProfile -File .\stop-console.ps1
```

If you want the policy and queue views to load immediately, set `CONTENT_LAB_OPERATOR_ORG_ID`
in `.env` to an org UUID before launching.

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

The credential-free golden path is:

```bash
./scripts/e2e_mvp_smoke.sh
```

This wrapper keeps one obvious boot order for the mock-backed MVP flow:

1. ensure `.env` exists;
2. start Postgres, Redis, MinIO, and bucket init;
3. run Alembic migrations;
4. start the API on a free local port;
5. run `scripts/e2e_mvp_smoke.py`, which seeds an org/page/policy/family/reel,
   queues the real trigger route, executes `process_reel`, and verifies API,
   Postgres, outbox, and MinIO package state.

The smoke path exports `RUNWAY_API_MODE=mock`, so it stays on the real Runway
provider boundary without requiring production credentials. The current
`process_reel` implementation calls the Runway worker path in-process, so a
separate long-running worker process is not required for this MVP check.

If you already have infra, migrations, and the API running, the direct Python
entrypoint is:

```bash
RUNWAY_API_MODE=mock python scripts/e2e_mvp_smoke.py
```

Optional flags:

- `--api-base-url http://127.0.0.1:8000` to point at an existing API.
- `--org-id <uuid>` and `--page-id <uuid>` to reuse seeded records.
- `--policy-scope global` to smoke the global policy path instead of the page override.

On success the script prints the created IDs plus the final `run_status`,
`reel_status`, and `package_root_uri`. On failure it raises step-scoped errors
that include the relevant IDs, URIs, or rows that were checked.

## No-regeneration regression

The exact-reuse cost-control contract has its own repo-level regression script:

```bash
./scripts/e2e_no_regen.sh
```

This wrapper keeps the path deterministic and intentionally narrower than the
full MVP smoke:

1. ensure `.env` exists;
2. start Postgres, Redis, MinIO, and bucket init;
3. run Alembic migrations;
4. start the API on a free local port;
5. run `scripts/e2e_no_regen.py`, which:
   resolves one generation request,
   verifies exactly one provider submission record exists,
   marks the staged asset `ready` directly in Postgres,
   resolves the identical request again,
   and proves the second response is `reuse_exact` without a second provider submission.

If you already have infra, migrations, and the API running, the direct Python
entrypoint is:

```bash
python scripts/e2e_no_regen.py
```

On success the script prints a JSON summary like:

```json
{
  "asset_id": "<uuid>",
  "asset_key_hash": "<hash>",
  "first_decision": "generate",
  "org_id": "<uuid>",
  "provider_job_count": 1,
  "provider_submission_history_entries": 1,
  "second_decision": "reuse_exact",
  "storage_uri": "s3://content-lab/assets/derived/<uuid>.mp4",
  "task_count": 1
}
```

That output means the same request generated once, transitioned to a ready
asset, and then reused that exact asset on the second resolve without recording
another provider submission.

## Real provider reel smoke

The real-Runway manual path remains available separately:

```powershell
powershell -NoProfile -File scripts/manual-smoke-reel.ps1
```

That script now delegates to `scripts/e2e_mvp_smoke.py --provider-mode live`, so
the seeding and assertions stay aligned with the mock-backed MVP path.

Use that path only when you intentionally want to exercise live provider
credentials. Before running it:

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
