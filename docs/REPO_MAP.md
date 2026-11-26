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
| Web UI | Old UI archived to `legacy/ui/2026-09-08/`. `apps/web` has the ~30 API proxy routes, a small design system, and **Quick Reel at `/make`** (Nov 2026, see [Quick Reel](#quick-reel-make-2026-11-25)). Studio is not built. |
| End-to-end run | Verified through the Docker API in `smoke_test` mode (2026-11-26): 12 s and 20 s reels with voice, no blank tail. See [Pipeline fixes](#pipeline-fixes-2026-11-26). |

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
| `apps/web` | Next.js 15 UI: design system, Quick Reel (`/make`), local Remotion render service, API proxy routes | `app/make/**`, `components/ui/*`, `app/_lib/quick-reel/render-queue.ts`, `app/api/**/route.ts` |

### API endpoints (grouped)

- **Orgs / Pages:** list orgs; CRUD pages
- **Policy:** global, per-niche, per-page settings (get/patch)
- **Assets:** list, get, download, resolve
- **Asset packs:** create, list, items, plan, regenerate-plan, ideas, combinations, approve/reject, cinematic-plan-prompt, cinematic-plan-validate, generate
- **Reel families / Reels:** create/list/get; approve, archive, mark-posted
- **Creative / Quick Reel:** hooks, quick-reel branches, quick-reel compose (stateless), **quick-reel reels** (Send to Review: saves a `ready` reel into the page's "Quick Reel" family)
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
| `reel-templates` (TS) | Remotion compositions (`KineticReel`), energy styles, caption geometry + overlay render trace, Quick Reel adapter, local Node render (`render/`) | Real; vitest; used by `/make` |
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
   generate needs `approved`, regenerate-plan needs planned/approved/rejected). (Correction: it does
   not call Runway in the request; it only records provider jobs for the worker.)
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

### Fixes (branch `fix/review-findings`, 2026-11-25)

Verified by a second end-to-end run **through the Docker API** (no host workarounds): queued →
succeeded in 114 s, package links signed for `localhost:9000`. API 208 passed (0 skipped with
Postgres), orchestrator 51, worker 24, all other packages green.

| Finding | Fix |
|---|---|
| Docker API can't launch the pipeline | `Dockerfile.api` ships `apps/orchestrator` + `apps/worker` and installs the orchestrator env |
| No FFmpeg in any image | api/worker/orchestrator images install `ffmpeg` (7.1) + `fonts-dejavu-core` |
| Download links unusable from a browser in Docker | new `MINIO_PUBLIC_ENDPOINT` setting used for presigning; compose sets it to `http://localhost:9000` |
| Pipeline crashed in containers (`TimeoutError`) | Prefect ephemeral-API timeout patch moved to `content_lab_orchestrator.prefect_compat` and applied by the CLI (was test-only) |
| Crashed runs stuck in `queued` forever | the CLI marks its run `failed` (with the error) when the flow raises |
| Failed launch burns the idea plan | idea-plan route now matches the cinematic route: returns a live run, retries a failed one, honours `force_new_package` |
| `.one_or_none()` 500s on assets with several gen-param rows | `.first()` in all four queries |
| Packs stuck in `generating` | failures mark the pack `failed`; generate and regenerate-plan accept `failed` |
| Package 404 while rendering | `GET /packages/{run_id}` returns `409 {"message": "Package not ready yet", "run_status": …}` while pending/queued/running |
| Page runs unpaginated | `limit` (default 100, max 500) and `offset` |
| Idea plans labelled `daily_reel_factory` | stored with workflow key `idea_plan` |
| LLM call inside a DB transaction | transaction ended before the call; run id assigned up front |
| Cinematic reels forced to 10 s | clamped to 5–10 s, so a 7 s plan stays 7 s |
| Capped plans squeeze the last beat to 1 s | beats scale proportionally to the cap |
| Worker connection leak | stores share one engine per database URL (outbox, editing, assets); worker steady at 66 connections over minutes (8 processes) instead of growing past 160 |

Still open (not review items; need real feature work):

(All four were fixed on 2026-11-26; see [Pipeline fixes](#pipeline-fixes-2026-11-26).)

- **10 s maximum reel length**: one Runway clip per reel and editing cannot loop or hold a clip.
- **Blank last ~4 s**: the editing overlay pipeline (`packages/editing/overlays.py`) leaves the last
  scenes without text even when every beat has copy.
- **Silent audio**: no voiceover synthesis exists; QA should fail silent or blank segments.
- Seed scripts download from Wikimedia every run; `open-console.ps1` image freshness and fingerprinting.

## Pipeline fixes (2026-11-26)

Branch `claude/jolly-hamilton-hte4rt`, six commits on top of `main` @ d59f8d7.

### What was fixed

| Problem | Root cause | Fix |
|---|---|---|
| Blank last ~4 s | Not `overlays.py`: `canonical_timeline.build_canonical_timeline` pinned overlay cue *i* to scene *i* and ignored cue timing. Idea plans have 3 beats and scene plans always have 5 scenes, so scenes 4–5 had no text. | Cues use `scene_id`, then their own beat timing, then the scene index. Gaps are closed (hold the previous cue), the first cue starts at 0 and the last runs to the end. |
| QA passed silent, black, frozen reels | Format QA only reads stream metadata. Nearly every media gate is in `_NONBLOCKING_FAIL_GATES` anyway. | `content_lab_qa.media_content`: one downscaled decode with `blackdetect`, `freezedetect`, `volumedetect`, `silencedetect`. New **blocking** gates: `media_content` (black/frozen > 1 s), `audio_content` (no audio, mean < −60 dB, narrated script without a voiceover), `overlay_coverage` (text gap > 0.5 s). Mock voice and silent gaps > 2 s are warnings. |
| No voiceover | Nothing synthesized `spoken_script`. | `content_lab_editing.voiceover`: `TTSProvider` protocol, `MockToneTTSProvider` (deterministic tone per line: length from word count, pitch from a text hash), `ElevenLabsTTSProvider`. Each beat is placed at its start; long lines are sped up (max 1.25×) then trimmed inside the beat. Voice is mixed over clip audio (clip at 0.25). Mock reels carry the MP4 tag `comment=content_lab_voiceover=mock`. Selection: `TTS_PROVIDER`; otherwise mock when `RUNWAY_API_MODE=mock`, ElevenLabs when `ELEVENLABS_API_KEY` is set, else none. `smoke_test` launches force mock. |
| 10 s cap | Orchestrator clamped the reel to one Runway clip; `runs.py` clamped cinematic plans to 5–10 s. | Reels keep the plan length (5–60 s) and are split into the fewest 5–10 s clips (12 → 6+6, 30 → 10+10+10). Each clip has its own seed and a prompt built from its scenes. The resolver resolves each clip through the registry/Runway path, and the editor chains them. Looping or extending one clip is opt-in (`allow_loop`); short media still fails (MED-009). Cinematic plans are bounded to 5–60 s. |
| Mock footage black, fixed 10 s | `MockRunwayClient` returned one 90×160 black fixture. | Deterministic moving test pattern (720×1280, seed-tinted) at the requested length (≤ 10 s). The fixture is the fallback when FFmpeg is missing. |
| `open-console.ps1` stale images / slow `-Rebuild` | The stored fingerprint was **never compared**; only missing images were built. The fingerprint hashed every file (incl. `.venv`, caches), and its exclusions only matched `\`. | Rebuilds when the fingerprint changes. Hashes only git-listed source/config/lock files (~570; pruned walk without git). Migrations run whenever images were rebuilt. |
| Seeds re-download, Windows SSL | New timestamped folder per run, no cache, default CA store. | `scripts/seed_downloads.py`: cache in `artifacts/seed-cache/` (atomic, validated), TLS via `SSL_CERT_FILE`/`REQUESTS_CA_BUNDLE` or certifi, `Retry-After`. The faceless seed reuses its pack and specs (idempotent). |
| Seed output in `git status` | | `.gitignore`: timestamped `artifacts/asset_packs/*/YYYYMMDD-HHMMSS/` folders, `last_seed_summary.json`, `artifacts/seed-cache/`, steak downloads. |

Also: refreshed the stale `packages/editing/poetry.lock`, and fixed `test_process_reel_flow_runs_full_phase_one_package_generation` (it stripped the leading `/` from POSIX paths). It now passes on Linux.

### Verified

Stack: `docker compose -f infra/docker-compose.yml --profile app build` then `up -d`. In this sandbox that needed a compose override for the build network/proxy and `chainguard/minio` (see "Still open"). Migrations went to 0015 in the API container. Then `seed_quick_reel_demo.py`, `POST …/idea-plans`, and `POST …/generate-package {"generation_mode": "smoke_test"}` through the **Docker API**. The MP4s were downloaded via their signed URLs.

| | 12 s plan (3+6+3, template) | 20 s plan (beats edited to 5+10+5) |
|---|---|---|
| Run | queued → succeeded in ~55 s, 2 × `asset.generate` | ~70 s, 2 × `asset.generate` |
| Video (ffprobe) | h264 1080×1920 24 fps, **12.000 s** (was 10.0) | h264 1080×1920 24 fps, **20.000 s** |
| Audio (ffprobe) | AAC 48 kHz stereo, 12.037 s, tag `content_lab_voiceover=mock` | AAC 48 kHz stereo, 20.026 s, same tag |
| Loudness (volumedetect) | mean **−25.7 dB**, max −20.8 dB (was −91 dB) | mean −27.8 dB, max −21.0 dB |
| blackdetect / freezedetect (≥ 0.5 s) | none | none |
| Last seconds | CTA text on screen at 11.5 s over clip 2 | CTA text at 19.5 s over clip 2 |
| QA | `warn`, nothing blocking; `media_content` / `overlay_coverage` / `timeline_timing` pass; `audio_content` warns: mock voice, 2.5 s gap (6.5–9.0 s) | `warn`, nothing blocking; `audio_content` warns: gaps 8.5–15.1 s and 17.4–20.0 s |

Python suites (Linux, Postgres on 5433): api 229 (0 skipped), worker 24, orchestrator 66, editing 396 (+2 skipped), qa 171, assets 280, creative 153, intelligence 32, outbox 28, runs 54, storage 62, auth 18, core 26, shared 41. `features`/`ingestion` have no tests.

### Still open

- **Narration does not fill long beats.** Template narration is about 2 s per line, so a 10 s beat has ~6 s of dead air (QA warns). Scripts should write narration to the beat length. There is no music bed.
- **Not exercised against live providers** (no keys here): ElevenLabs, and Runway with several clips per reel. Multi-clip multiplies Runway cost per reel, and it assumes gen4.5 accepts any whole-second duration in 5–10 (as the existing clamp already did). Clip boundaries are hard cuts; continuity between clips relies only on prompts.
- ~~`infra/docker-compose.yml` still uses `minio/minio` and `minio/mc`~~ — fixed in round 2 (`chainguard/minio`).
- **Not run here:** `open-console.ps1` (no PowerShell in this sandbox), the seed scripts against Wikimedia (blocked here; covered by unit tests), and the images on a real `python:3.11-slim` base (Debian mirrors are blocked here, so a local Ubuntu 24.04 / Python 3.12 stand-in was used).
- The cinematic/layered composition path was not part of the end-to-end run (idea plans only).
- The earlier uncommitted blank-tail attempt (`content-lab-archive/uncommitted/z58o`, on the Windows machine) was not reachable from this session and was not reviewed; the fix was written from the code.
- Editing renders are slow (`-preset medium -threads 1`); chaining adds one encode per clip.
- `process_reel.py` and `content_lab_editing/__init__.py` were already not `ruff format`/isort clean; left as is.

## Quick Reel (`/make`, 2026-11-25)

The hook-first creator from `docs/UI_PLAN.md` section 3, for internal use (no auth, billing or
sign-up). Branch `claude/quick-reel-creator-24gjod`.

### What is where

| Path | What it is |
|---|---|
| `apps/web/app/make/_lib/` | Pure logic, all unit-tested: `machine.ts` (the flow as a reducer), `session.ts` (hooks → branches → compose pre-fetching), `api.ts`, `selection.ts`, `timelines.ts`, `caption.ts`, `visuals.ts`, `suggestions.ts`, `keyboard.ts` |
| `apps/web/app/make/_components/` | Screens: `SeedScreen`, `HookReel`, `BuildStage` (+ `ChoiceSheet`), `DropScreen`, `ShipScreen`; `ReelPlayer` wraps `@remotion/player`; `QuickReelApp` wires it together |
| `apps/web/components/ui/`, `lib/cn.ts` | Design system: Tailwind v4 tokens, Button / Chip / Kbd / StoryBars / PhoneFrame / Toaster (Radix) |
| `apps/web/app/_lib/quick-reel/render-queue.ts`, `app/api/quick-reel/renders/**` | Local render service: `POST /api/quick-reel/renders`, `GET …/{id}`, `…/{id}/video` (`?download=1`), `…/{id}/trace` |
| `packages/reel-templates/src/` | `energy.ts` (chill / punchy / dramatic), `geometry.ts` (caption boxes shared by renderer and trace), `trace.ts`, `quickReel.ts` (compose response → timeline, segments, loop previews), `schema.ts` (zod), `fonts.ts` (self-hosted Montserrat) |
| `packages/reel-templates/render/` | Node render: bundle once, trace in the headless page, `renderMedia` H.264, trace JSON next to the MP4 |
| `apps/api/src/content_lab_api/routes/quick_reels.py` | `POST /orgs/{org}/pages/{page}/quick-reel/reels` (Send to Review) |
| `scripts/seed_quick_reel_demo.py` | Seeds a demo org: cooking page with an image pack (committed PNGs), fitness page without one |

### How it works

- **Flow:** seed (page + topic or suggestion) → hook reel (3 hooks, swipe / ↑↓, tap / Enter) →
  three cliffhangers (structure, energy, ending: the frame holds on the last fully visible
  caption, dims, and cards with looping ~2 s previews slide up; tap or 1/2/3) → drop (full replay,
  no UI) → ship (Download MP4, Copy caption, Send to Review, Remix, Change one thing). Surprise me
  skips to the drop. Desktop shows a centred phone frame with a keyboard legend.
- **No dead time:** branches are fetched for every hook as soon as hooks arrive; once a hook is
  picked every combination is composed in the background (compose has no LLM call), so taps play
  from cache. The MP4 render starts when the drop starts.
- **Visuals:** asset packs are org-scoped, so a pack is the page's when its niche matches the page
  niche. Images go through the same-origin asset proxy (`/api/orgs/{org}/assets/{id}/file`); with
  no matching pack the energy's gradient backdrop is used.
- **Render trace:** `QuickReelTrace`'s `calculateMetadata` computes the trace inside the headless
  page with the real font, using the same `captionGeometry` the renderer draws with. Field names
  match `packages/qa` (`source_text`, `rendered_text`, `clipped`, `safe_area_passed`, `font_size`,
  `visible_start/end_seconds`), plus line boxes and frame intervals. A failing trace blocks the render.
- **Send to Review** re-composes server-side from hook + branches + selection, reuses or creates the
  page's "Quick Reel" family, and creates a generated reel in `ready`, so
  `GET …/reels?status=ready` lists it and the existing approve / archive / mark-posted actions work.
  Pipeline QA does not run on it (recorded as `qa.status = not_run`); `client_request_id` makes
  retries idempotent.

### Run it locally

```bash
docker compose -f infra/docker-compose.yml up -d postgres redis minio minio-init
(cd apps/api && poetry run alembic upgrade head && poetry run python ../../scripts/seed_quick_reel_demo.py)
(cd apps/api && poetry run uvicorn content_lab_api.main:app --port 8000)  # no ANTHROPIC_API_KEY = fallback hooks
REMOTION_BROWSER_EXECUTABLE=/path/to/chrome-headless-shell pnpm --filter web dev  # omit to let Remotion download one
```

Open http://127.0.0.1:3000/make.
Renders land in `apps/web/.quick-reel-renders/` (gitignored; override with `QUICK_REEL_RENDER_DIR`).
Real-render test: `cd packages/reel-templates && RENDER_INTEGRATION=1 pnpm test:render`.

### Verified (2026-11-25, fallback hooks, no API key)

- Full flow in headless Chromium at 375×812 (mouse-drag swipe and clicks; touch events were not
  emulated) and 1440×900 (keyboard only):
  seed → hooks → swipe → 3 cliffhangers → drop → ship → MP4 download → caption copy → Send to
  Review; plus Change one thing, Remix, Esc / D shortcuts, Surprise me from the seed (1.4 s to the
  drop), and the gradient page. No console errors.
- Exported MP4 (ffprobe): H.264, 1080×1920, 30 fps, yuv420p; 480 frames = 16.000 s = the composed
  `duration_seconds`. Traced line boxes drawn over extracted frames sit on the rendered glyphs;
  nothing is cut off. `validate_package_overlay_render_trace` (packages/qa) passes on the trace.
- The sent reels appear in `GET …/reels?status=ready` in the page's "Quick Reel" family.
- `next build` and a render through `next start` work.

### Found while building it

- **`minio/minio` can no longer be pulled from Docker Hub** ("pull access denied"), so
  `docker compose up` fails for MinIO on a fresh machine. Verification used `chainguard/minio`
  with the same ports and credentials; `infra/docker-compose.yml` was not changed.
- One page with invalid persona metadata (e.g. `persona` without `label` / `audience`) makes
  `GET /orgs/{org}/pages` return 500 for the whole org.
- Python suites on Linux: every suite passes except `apps/orchestrator`
  `test_process_reel_flow_runs_full_phase_one_package_generation` (looks for
  `tmp/pytest-of-root/…/timeline.json`, a path missing its leading `/`; it fails the same with
  `main`'s code, so it predates this work). `packages/creative` and `packages/qa` need
  `pytest tests`: their committed `py/tests -> ../tests` symlinks make a bare `pytest` collect
  everything twice. `packages/editing`'s `poetry.lock` is out of date (`poetry install` refuses);
  its 175 tests pass from the orchestrator env.
- Template fixes: cut-out captions sat below the bottom safe line, and uppercase captions were
  measured in mixed case (could overflow). Both fixed in `reel-templates`.
- Renders depend on image size: ~70 s for a 16 s reel with six 2.6–14 MB PNGs (first render adds
  a ~10 s bundle); ~20 s for a short text-only clip. Renders run one at a time, so a quick Remix
  after Change one thing queues behind the earlier render.

### Not done yet

- **Audio:** no music bed or voiceover; `music_mood` is shown but not played. The MP4 is silent.
- MP4s stay on the web server's disk; Send to Review stores the render id, not the file. Next:
  upload the MP4 + trace to MinIO and run `packages/qa` on them.
- Studio Review UI does not exist yet; reviewers use the reels API.
- Fallback hooks/branches are generic templates; real variety needs `ANTHROPIC_API_KEY`.
- Pre-resize asset representations to 1080 px for faster previews and renders.
- Remotion licence: `acknowledgeRemotionLicense` is deliberately not set (UI_PLAN open decision 4).

