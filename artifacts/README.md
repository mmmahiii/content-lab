# Manual Reel Creation — End-to-End Demo

This folder contains the recording, screenshots, and downloaded reel package
produced by manually creating **one reel for one page** against a fresh
Content Laboratory stack.

## Environment verified before the run

- Python `3.11.15`
- Poetry `2.3.4` (`~/.local/bin/poetry`)
- Node.js `v24.15.0`, pnpm `9.0.0`
- Docker Engine `29.1.3`, Compose v2 `2.40.3`, **Storage driver `fuse-overlayfs`**, iptables backend (symlinked to `iptables-legacy` via `/etc/alternatives/iptables`).
- FFmpeg `6.1.1`

## Stack bootstrapped

- Infra: Postgres 16 (pgvector), Redis 7, MinIO via `infra/docker-compose.yml`.
- Alembic migrations `0001..0008` applied to `contentlab`.
- API: `apps/api` on `http://127.0.0.1:8000`.
- Orchestrator (`apps/orchestrator`) invoked directly for the `process_reel`
  Prefect flow with `RUNWAY_API_MODE=mock`, so the Runway dependency is
  satisfied by the in-repo `MockRunwayClient` (no live API key needed).

## Entities created (all via the real HTTP API)

| Entity | ID |
|--------|----|
| Org | `bc8f5055-33c0-47ba-9405-66da4228baea` (`manual-demo-*` slug) |
| Page | `579f8404-1737-47a5-9c06-66a0a07b2515` (Instagram, owned) |
| Reel family | `7d8618a9-9b51-47ae-a247-0b0dbcc414b3` (`Manual Demo Family`, explore) |
| Reel | `8ac8e82f-d112-4e08-b77a-b4e07dddb798` (generated, draft -> ready) |
| Run | `d96b81f0-3f54-4ad2-a42b-9d3348dd81d4` (`process_reel`, succeeded) |

All IDs are also captured in `last_run_ids.json`.

## Downloaded reel package for the page

Saved at `page/<page_id>/reel/<reel_id>/`:

- `final_video.mp4` — 1080x1920 H.264 + AAC, 10.0s (65,717 bytes)
- `cover.png` — 1080x1920 cover image (30,613 bytes)
- `caption_variants.txt` — short / standard / engagement caption copy
- `posting_plan.json` — full posting plan (compliance, schedule, hashtags)
- `package.json` — raw `/orgs/{org}/packages/{run}` API response with
  presigned MinIO download URLs

These are the same artifacts the production Admin UI downloads when an
operator clicks "Download package" on the reel detail page.

## Captures

- `manual_reel_demo.cast` — asciinema recording of the full terminal session
- `manual_reel_demo.gif` — rendered screen capture (terminal GIF)
- `manual_reel_demo.mp4` — same screen capture encoded as MP4 video
- `screenshots/process_step_*.png` — frames from the recording at key steps
- `screenshots/reel_cover.png`, `reel_frame_01.png`, `reel_frame_05.png` —
  stills taken from the produced reel video / cover

## Reproducing

```bash
bash /workspace/artifacts/manual_reel_demo.sh
```

The script performs steps 1-10 end-to-end:

1. Health check API
2. Insert org row (no `POST /orgs` route exists)
3. `POST /orgs/{org}/pages` — create owned page
4. `PATCH /orgs/{org}/policy/page/{page}` — attach policy
5. `POST /orgs/{org}/pages/{page}/reel-families` — create family
6. `POST /.../reel-families/{family}/reels` — create generated reel
7. `POST /.../reels/{reel}/trigger` — queue `process_reel` run
8. `python -m content_lab_orchestrator.cli run --flow process_reel …` (mock)
9. Fetch final run/reel/package status
10. Download all package artifacts (MP4 + cover + captions + plan) to disk
