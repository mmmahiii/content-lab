# Reel Creation End-to-End Demo

This folder is the complete evidence that the Content Laboratory environment is
working and that a single reel can be created for a page, with the reel
downloadable the same way an operator would download it from the admin UI.

## What was recorded

One real reel was built end-to-end on `main` against a freshly bootstrapped
Content Lab stack:

| Entity | ID |
| --- | --- |
| Org | `56b5ec2a-8dab-4fba-b94b-5d9b4c1021db` (`UI Demo Org`) |
| Page | `39046f4b-b819-41f9-a706-3642e7fb3597` (`UI Demo Reel Page`, Instagram, owned) |
| Reel family | `cde7e715-0af9-4e5d-b1bd-a51872a2201c` (`UI Demo Family`, explore) |
| Reel | `883bb88f-d8e6-4351-8a6b-34ddeaf4546d` (generated, `DemoReel-A`, draft -> ready) |
| Run | `e4455adb-6405-4808-a10f-ac1dec6e253f` (`process_reel`, succeeded) |

The same IDs are captured in `last_run_ids.json` / `demo_summary.json`.

## Environment

- Python `3.11.15`, Poetry `2.3.4`
- Node.js `v24.15.0`, pnpm `9.0.0`
- Docker Engine `29.1.3` + Compose v2
- FFmpeg `6.1.1`
- Services up: Postgres 16 (pgvector) on `:5433`, Redis 7 on `:6379`, MinIO on `:9000/:9001`
- Alembic migrations `0001..0008` applied
- API at `http://127.0.0.1:8000` (FastAPI, uvicorn)
- Web console at `http://127.0.0.1:3000` (Next.js 15 dev)
- Orchestrator flow executed inline with `RUNWAY_API_MODE=mock`
  (no live Runway credentials required)

## Screen capture of the creation process

- `video/reel_creation.webm` — full browser screen recording (Playwright)
- `video/reel_creation.mp4` — same capture re-encoded to H.264 MP4 for easy viewing

The recording walks through:

1. Operator console home
2. Pages list (empty for the fresh org)
3. Page workspace detail right after the page was created
4. Page-scoped policy editor with an `explore: 1.0` policy
5. Reel detail while the reel is still in `draft`
6. Run detail as the `process_reel` run gets queued
7. Run detail after the Prefect flow finishes (`succeeded`)
8. Reel detail with status `ready` and all package artifacts exposed
9. Package detail page with per-artifact downloads (manifest, final_video, cover,
   caption_variants, posting_plan, provenance)

## Screenshots

Key-step PNGs are in `screenshots/`:

- `step_02_home.png` — operator console home
- `step_03_pages_empty.png` — pages list before any page exists
- `step_05_pages_with_one.png` — pages list after creating the page
- `step_06_page_detail_before_reel.png` — page workspace overview
- `step_08_page_policy_configured.png` — page policy editor with explore policy
- `step_11_reel_detail_draft.png` — reel detail in `draft`
- `step_13_run_detail_queued.png` — run detail immediately after `POST /.../trigger`
- `step_15_run_detail_succeeded.png` — run detail after `process_reel` finished
- `step_16_reel_detail_ready.png` — reel detail with package artifacts
- `step_17_package_detail.png` — package detail with per-artifact download buttons

## The actual reel, saved on the page

`page/39046f4b-b819-41f9-a706-3642e7fb3597/reel/883bb88f-d8e6-4351-8a6b-34ddeaf4546d/`:

| File | Purpose | Size |
| --- | --- | --- |
| `final_video.mp4` | Final 1080x1920 H.264+AAC reel (10s) | 65,717 bytes |
| `cover.png` | 1080x1920 cover image with the hook text | 30,613 bytes |
| `caption_variants.txt` | short / standard / engagement captions | 358 bytes |
| `posting_plan.json` | Full posting plan (schedule, platforms, compliance) | 3,978 bytes |
| `provenance.json` | Asset + provider job lineage for the reel | 625 bytes |
| `package_manifest.json` | Artifact index with SHA-256 checksums | 1,582 bytes |
| `package.json` | Raw `GET /orgs/{org_id}/packages/{run_id}` response with presigned MinIO download URLs | |

These are the same files an operator would get if they clicked "Download
<artifact>" on the reel / package detail pages in the admin UI — the files were
downloaded through those same presigned MinIO URLs.

## Reproducing

```bash
# 1. Start infra (Postgres + Redis + MinIO)
sudo docker compose -f infra/docker-compose.yml up -d

# 2. Apply migrations
cd apps/api && poetry run alembic upgrade head && cd ../..

# 3. Start API (tmux / background)
cd apps/api && poetry run uvicorn content_lab_api.main:app --host 0.0.0.0 --port 8000

# 4. Start the web console
pnpm --filter web dev

# 5. Drive the full reel creation + UI recording
python3 scripts/demo_reel_recorder.py
```

`scripts/demo_reel_recorder.py` is checked in and performs all 19 steps end to
end, including downloading the final reel package for the page into this
`artifacts/` directory.
