# Repo Map — what's actually here (2026-11-24)

A plain-language map of Content Lab, written after surveying the code and running every
Python test suite. Read this before diving into source. It describes **what exists today**,
not what the charter in `docs/` hopes for.

## What the product does, in one paragraph

You set up a **Page** (an Instagram-style account) inside an **Org**, upload or generate an
**Asset Pack** (images/clips around a theme), and the system plans reels from it: a hook,
script beats, on-screen text, captions, hashtags, camera/scene plans. It then renders a
vertical MP4 with FFmpeg (layered overlays on your assets, optionally Runway-generated clips),
runs a large set of QA checks, and outputs a **ready-to-post package** (MP4 + cover + captions
+ posting plan + provenance). A human approves and posts; nothing auto-posts.

## The honest status

| Area | Status |
|------|--------|
| Backend structure (API, worker, orchestrator, DB) | Real, organised, mostly tested |
| Tests | ~1,000 tests; **2 failing**, ~111 skipped (need Postgres running) |
| AI script writing | **Claude via `packages/intelligence`** (Nov 2026). Hooks, Quick Reel branches, idea plans and reel scripts are LLM-written when `ANTHROPIC_API_KEY` is set, with the old rule/template generators as offline fallbacks. The cinematic planner still uses the manual ChatGPT copy-paste flow. |
| Video generation | Runway `gen4.5` client exists (needs `RUNWAY_API_KEY`) |
| "Learns from performance" (charter vision) | **Not built.** `packages/features` and `ingestion` are empty one-line stubs. |
| Content variety | Niche-specific rules now live in `content_lab_creative/niche.py` (cooking, luxury, business, fitness, finance, beauty, travel; register more). Some QA motion checks (sizzle/steam) and planner prompt examples are still food-flavoured. |
| Web UI | Old UI archived to `legacy/ui/2026-09-08/`. `apps/web` is now an empty page **plus ~30 working API proxy routes** in `apps/web/app/api/` — keep these for the new UI. |
| End-to-end run | Not verified in this survey (needs Docker running). |

### The 2 failing tests

1. `apps/api/tests/test_db_0008.py::test_alembic_script_head_is_0013` — **stale test**.
   Migrations now go to `0015`; the test still expects `0013`. Harmless, just update it.
2. `apps/orchestrator/tests/test_source_plan_overlay_regression.py::test_source_plan_overlays_do_not_reintroduce_word_clipping`
   — **real user-facing bug.** On-screen overlay text renders an instruction-like placeholder
   ("Show the useful shift, example, or operating principle.") instead of short copy
   ("Useful shift"). Would appear in finished videos.

## How a reel gets made (the main pipeline)

```
Web UI ──> apps/web/app/api/* (proxy) ──> FastAPI (apps/api)
                                              │ writes Run + outbox event to Postgres
                                              ▼
                         Worker (Dramatiq/Redis) + Orchestrator (Prefect)
   daily_reel_factory ─> process_reel:  plan creative ─> resolve assets ─> generate (Runway)
                                        ─> edit/render (FFmpeg) ─> QA ─> package
                                              │
                                              ▼
                          MinIO (files)  +  Postgres (records, provenance)
```

Asset-pack path: `asset_pack_generation` (plan + generate a reusable pack) →
`asset_pack_to_reels` (combine pack items into reel candidates).

## Where things live

### Apps

| Path | What it is | Biggest / key files |
|------|-----------|---------------------|
| `apps/api` | FastAPI HTTP API + Alembic migrations (`migrations/versions`, up to 0015) | `routes/asset_packs.py` (1.6k lines), `routes/runs.py` (1.4k), `services/asset_packs.py` (2.3k), `services/process_reel.py` (1.8k) |
| `apps/worker` | Dramatiq background jobs | `actors/editing.py` (render), `actors/runway.py` (video gen), `actors/outbox_dispatcher.py` |
| `apps/orchestrator` | Prefect flows that sequence the pipeline | `flows/process_reel.py` (2.9k — the heart), `flows/daily_reel_factory.py`, `flows/asset_pack_*.py`, plus maintenance flows (`provider_job_sweeper`, `storage_integrity_check`, `outbox_drain`) |
| `apps/web` | Next.js 15 UI — **empty shell**, proxy routes kept | `app/api/**/route.ts`, `app/_lib/operator-context.ts` |

### API endpoints (grouped)

- **Orgs / Pages:** list orgs; CRUD pages
- **Policy:** global, per-niche, per-page settings (get/patch)
- **Assets:** list, get, download, resolve
- **Asset packs:** create, list, items, plan, regenerate-plan, ideas, combinations, approve/reject, cinematic-plan-prompt, cinematic-plan-validate, generate
- **Reel families / Reels:** create/list/get; approve, archive, mark-posted
- **Runs:** trigger, list, get; idea-plan discard; hook-cover update
- **Packages:** metadata + signed download
- **Health**

### Packages (shared Python libraries)

| Package | Purpose | Notes |
|---------|---------|-------|
| `assets` | Asset registry: catalogue, dedupe, embeddings, combinator, Runway client | Real; 138 tests pass |
| `creative` | Briefs, script generation, reel planning schemas, planner prompts | Real but rule-based; cooking-tuned |
| `editing` | FFmpeg rendering, overlays, layouts, templates, packaging | Real; `overlays.py` is 2k lines |
| `qa` | Quality gates: format, timing, overlays, scene coherence, semantic script, plan repair | Real; 158 tests pass |
| `storage` | MinIO/S3 client | Real |
| `runs` | Run status, correlation IDs, idempotency keys | Real |
| `outbox` | Transactional outbox (reliable event publishing) | Real |
| `auth` | Auth/policy engine | Small |
| `core` | Base types, budget logic | Small |
| `shared` | Shared Python models (`py/`) + TypeScript types (`ts/`) | Used by web |
| `intelligence` | Structured-output LLM client (Claude), fake client for tests | Real |
| `features`, `ingestion` | — | **Empty stubs** |

### Infra & tooling

- `infra/` — Docker Compose: Postgres 16 (pgvector), Redis 7, MinIO; Dockerfiles for app services
- `open-console.ps1` / `stop-console.ps1` — one-command start/stop of the whole stack
- `scripts/` — quality gates (`py_check`), e2e smoke scripts, seed scripts for demo cooking packs, worktree helpers for parallel AI agents
- `docs/` — charter, architecture, run-local guide, regression lanes

### Clutter (safe to ignore; candidates for cleanup)

- Root: `.console-*`, `.dev-stack-*.log/.pid`, `debug-*.log` — leftovers from old runs
- `.dev-stack/` (195 MB) and `artifacts/` (96 MB) — local run outputs; some are committed to git
- `apps/graphify-out/` — a stray duplicate graph; the real one is `graphify-out/`
- `graphify-out/cache/` — committed to git (~750 files); shouldn't be
- `tools/car-epic-playground/` — unrelated side experiment
- `.mypy_cache`, `.pytest_cache`, `.ruff_cache` in every package

## Running it

```powershell
powershell -NoProfile -File .\open-console.ps1   # needs Docker Desktop running
```

Tests per package: `cd <package> && poetry run pytest -q`.

## Before building the new UI

- Build on the existing proxy routes in `apps/web/app/api/` — they map 1:1 to the endpoints above.
- The old UI in `legacy/ui/` is reference only (shows what screens existed: page workspace,
  asset-pack workspace, hook image creator, creative review, QA-failed workbench, policy editor).
- Decide early whether "many varieties of content" means beyond cooking — if so, the
  cooking-specific logic in `creative`/`qa`/`editing` and the missing LLM are bigger gaps than the UI.

## End-to-end run (2026-11-25, on `main` @ 2878810)

First full pipeline run: idea plan → package, Runway in mock (`smoke_test`) mode.

### Result: the pipeline works, but only with workarounds

One reel went `queued → running → succeeded` in **55 s**; all 7 stages succeeded
(creative_planning, asset_resolution, asset.generate, editing, qa, packaging, process_reel).
Every package file exists and downloads through its signed URL.

| Step | Command | Outcome |
|---|---|---|
| Stack | `open-console.ps1 -NoBrowser` | **Failed**: reused 7-month-old images → `Can't locate revision identified by '0015'` |
| Stack | `open-console.ps1 -NoBrowser -Rebuild` | **Hung** >6 min hashing ~18k cache files (`Get-BuildFingerprint`) before building |
| Stack | `docker compose -f infra/docker-compose.yml --profile app build api worker orchestrator` then `up -d` | Worked (~8 min build) |
| Migrations | `cd apps/api && poetry run alembic upgrade head` (host) | Worked (already at 0015) |
| Seed | `scripts/seed_faceless_cooking_asset_pack.py` | **Failed**: `SSL: CERTIFICATE_VERIFY_FAILED … certificate has expired` (Windows Python cert store, not the site). With `SSL_CERT_FILE` → certifi bundle it ran, but re-downloads ~24 images from Wikimedia **every run** with no cache and was throttled to ~2 min/image; first attempt died on breakage 2, second was stopped after 40 min. The run used pack/page data already in the DB from earlier seeds. |
| Package | `POST …/idea-plans/{id}/generate-package` (API in Docker) | **Failed**: HTTP 500 `Could not launch process_reel: Orchestrator app was not found at /app/apps/orchestrator` |
| Package | same, API run on host (`poetry run uvicorn …`) | **Worked** |
| Postgres tests | `cd apps/api && poetry run pytest` | **202 passed, 0 skipped** |

### What the video looks like

- 1080×1920, H.264, 24 fps, AAC stereo 48 kHz, **10.0 s** (plan asked for **12 s**).
- Black background (expected: mock Runway produces no footage).
- Small, plain monospace-style white text, centred. **No captions cut off**; **no placeholder or
  instruction text on screen** (the creator-direction fix works in a real run).
- Text only for 0–6 s ("What would make @test worth following this week?" → "Useful shift" →
  "One concrete next step"); **the last 4 s are a blank black screen**.
- **Audio is silent** (−91 dB): narration tracks are listed in the timeline but no voice is made.
- Captions were rewritten by copy lint into awkward text ("…turn page approach into a useful update").
- QA passed all of the above.

### Breakages found by the run

1. **API in Docker cannot generate packages.** `routes/runs.py:_launch_process_reel_flow` runs
   `poetry run python -m content_lab_orchestrator.cli` as a child of the API process, but the API
   image only contains `apps/api`. Package generation only works when the API runs on the host.
2. **Worker leaks DB connections until Postgres refuses everyone.** `outbox_dispatcher.py`
   calls `build_dispatch_store()` on every poll → `SQLOutboxStore()` → new `create_engine()` each
   time, never disposed. 161 idle connections in ~15 min; then `FATAL: sorry, too many clients
   already` for the API, tests and scripts.
3. **Every reel is capped at 10 s**, even in mock mode: `process_reel.py:_primary_asset_duration_seconds`
   clamps to `RUNWAY_GEN45_MAX_DURATION_SECONDS = 10`.
4. **Overlays don't follow the plan's beats**: the 5-scene plan (2 s each) carries the text, so 3
   beats fill only scenes 1–3 and scenes 4–5 are blank.
5. **A failed launch burns the plan**: `used_in_package_run_id` is committed before launching, so
   retrying returns `409 Plan has already been used`. (The cinematic route handles this correctly.)
6. **No voiceover** is generated; QA does not flag silent audio or blank segments.
7. Host `ffmpeg` on PATH is 4.2.3 (ImageMagick's copy); README asks for 6+. It worked for this run.
8. `open-console.ps1`: stale-image detection doesn't catch new migrations; fingerprinting is too slow.
9. Seed scripts download from Wikimedia at runtime into a new timestamped folder each run (no reuse),
   so seeding is slow, network-dependent and leaves ~50 MB of untracked files per run in `artifacts/`.

### Fixes applied during the run (no application code changed)

1. Re-ran the launcher with `-Rebuild`, then built images directly with `docker compose … build`.
2. Ran migrations from the host.
3. `SSL_CERT_FILE` set to certifi's CA bundle for the seed script (verification stays on).
4. Restarted, then stopped, the worker container to clear leaked connections (process_reel doesn't use it).
5. Stopped the API container and ran the API on the host so it can launch the orchestrator.

### Honest assessment

The core happy path (plan → script → mock clip → FFmpeg edit → QA → package → signed downloads)
is real and works. Around it, the repo is not production-shaped: the documented one-command start
fails, the Docker stack cannot run its main action, a worker leaks connections fast enough to take
the database down within ~20 minutes, seeding depends on a throttled public website, and QA passes a
video that is silent and blank for 40% of its length. Treat "the tests pass" as "the units behave as
their authors assumed", not "the product works".

### Code review: UI-facing routes (ranked by impact on the new UI)

1. **Package generation can't run in the Docker stack** (breakage 1) — the UI's main action.
2. **Idea-plan package generation can't be retried after a failed launch** (`runs.py`, breakage 5).
3. **`.order_by(seq.desc()).one_or_none()` raises when an asset has >1 generation-params rows** —
   `routes/asset_packs.py:_latest_gen_params`, `routes/assets.py:54`, `services/asset_registry.py:117,245`.
   `asset_registry.py:248` writes `seq = latest + 1`, so asset detail / register-source-asset 500 after
   the second row. Should be `.first()`.
4. **Asset packs can get stuck in `generating`**: `generate_approved_asset_pack` commits `GENERATING`
   before the per-item loop; an exception leaves no valid transition out (approve needs `planned`,
   generate needs `approved`, regenerate-plan needs planned/approved/rejected). It also runs generation
   (possibly Runway submissions) synchronously inside the HTTP request.
5. **`GET /packages/{run_id}` returns 404 "Package not found" while a run is in progress** — the UI must
   poll `GET /runs/{id}` and only then fetch the package.
6. **`GET /pages/{id}/runs` has no pagination** — returns every run the page has ever had.
7. **Idea plans are stored as `daily_reel_factory` runs with status `succeeded`** although no flow runs;
   run lists will mislabel them.
8. **The idea-plan LLM call happens inside an open DB transaction** (added in the LLM work) — move the
   call before the transaction.
9. Cinematic plans: `max(duration, 10)` plus the orchestrator's 10 s cap means every cinematic reel is
   exactly 10 s.
10. No dead private helpers in the four files; all public service functions have callers.
