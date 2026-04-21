# Single-reel demo artifacts

This folder is produced end-to-end by `scripts/demo/generate_one_reel.py` and
`scripts/demo/record_ui_walkthrough.py`. It captures the result of running the
full Content Lab stack locally (Postgres 16 + Redis 7 + MinIO via Docker
Compose, FastAPI, Next.js admin UI) and generating exactly one reel for one
page.

## Files

| Path | What it is |
|------|------------|
| `reel.mp4` | Final, canonical 1080×1920 reel video (pulled from MinIO via signed URL, also the `final_video.mp4` you can download through the UI). |
| `reel_cover.png` | Cover image for the reel (PNG, 1080×1920). |
| `local_package/` | The full canonical ready-to-post package: `final_video.mp4`, `cover.png`, `caption_variants.txt`, `posting_plan.json`, `provenance.json`, `package_manifest.json`. |
| `screenshots/01_pages_list.png` … `08_package_hover_downloads.png` | Step-by-step screenshots of the UI during the demo: Pages index → page overview → page reels → reel detail → run detail → package detail (with artifacts downloadable). |
| `ui_walkthrough.mp4` | Full screen capture of the UI walkthrough. |
| `demo_state.json` | All the IDs (org, page, family, reel, run) and the exact UI URLs, plus the signed download URLs the API currently serves for the package artifacts. |

## Reproducing the demo

From a fresh checkout:

```bash
# 1. Start infra
sudo nohup dockerd > /tmp/dockerd.log 2>&1 &
sudo docker compose -f infra/docker-compose.yml up -d

# 2. Install Python deps
for app in apps/api apps/worker apps/orchestrator; do
  (cd "$app" && poetry env use python3.11 && poetry install --no-interaction)
done

# 3. Migrate + start services
(cd apps/api && poetry run alembic upgrade head)
(cd apps/api && poetry run uvicorn content_lab_api.main:app --host 0.0.0.0 --port 8000) &
(cd apps/worker && poetry run dramatiq content_lab_worker.worker) &
pnpm --filter web dev &

# 4. Run the demo
(cd apps/orchestrator && poetry run python ../../scripts/demo/generate_one_reel.py)
python3 scripts/demo/record_ui_walkthrough.py
```

The generator bypasses the external Runway API (no real key is configured in
this environment) by producing a deterministic source clip with ffmpeg, then
runs the real in-repo editing + packaging libraries to turn that source into
the canonical reel package, uploads it to MinIO, and creates a Run row that
links the package to the reel so the existing package-download endpoint serves
it just like a production run would.
