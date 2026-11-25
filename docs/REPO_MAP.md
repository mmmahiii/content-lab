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
