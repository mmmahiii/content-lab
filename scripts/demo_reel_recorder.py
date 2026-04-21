"""End-to-end demo: create a single reel for a page and record the UI flow.

This script drives the Content Lab admin UI with Playwright while a reel is
created for a page via the real HTTP API, orchestrated with the Prefect
process_reel flow (RUNWAY_API_MODE=mock), and the final reel package is
downloaded to disk so the operator can "download as usual".

Outputs, under /workspace/artifacts/:

  - video/reel_creation.webm          Screen recording of the full flow
  - video/reel_creation.mp4           Same recording transcoded to MP4
  - screenshots/step_XX_*.png         Key-step screenshots
  - page/<page_id>/reel/<reel_id>/    Downloaded reel package for the page
  - last_run_ids.json                 All UUIDs produced by this run
  - demo_summary.json                 Machine-readable summary
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
API = os.environ.get("API_BASE", "http://127.0.0.1:8000")
WEB = os.environ.get("WEB_BASE", "http://127.0.0.1:3000")
ACTOR_ID = "demo-recorder"
OUT_ROOT = REPO_ROOT / "artifacts"
SCREENSHOT_DIR = OUT_ROOT / "screenshots"
VIDEO_DIR = OUT_ROOT / "video"
PAGES_DIR = OUT_ROOT / "page"

SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_DIR.mkdir(parents=True, exist_ok=True)
PAGES_DIR.mkdir(parents=True, exist_ok=True)

step_counter = 0


def banner(msg: str) -> None:
    global step_counter
    step_counter += 1
    print(f"\n==> [{step_counter:02d}] {msg}", flush=True)


def screenshot(page: Page, label: str) -> Path:
    name = f"step_{step_counter:02d}_{label}.png"
    path = SCREENSHOT_DIR / name
    page.screenshot(path=str(path), full_page=False)
    print(f"   saved screenshot: {path.relative_to(REPO_ROOT)}", flush=True)
    full_path = SCREENSHOT_DIR / f"step_{step_counter:02d}_{label}_full.png"
    page.screenshot(path=str(full_path), full_page=True)
    return path


def api_request(
    method: str,
    path: str,
    body: dict | None = None,
    actor_id: str = ACTOR_ID,
) -> dict:
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-Actor-Id": actor_id,
            "X-Request-Id": f"demo-{uuid.uuid4().hex[:8]}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = resp.read().decode()
    return json.loads(payload) if payload.strip() else {}


def pg_exec(sql: str) -> str:
    compose = REPO_ROOT / "infra" / "docker-compose.yml"
    res = subprocess.run(
        [
            "sudo",
            "docker",
            "compose",
            "-f",
            str(compose),
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "contentlab",
            "-d",
            "contentlab",
            "-v",
            "ON_ERROR_STOP=1",
            "-At",
            "-c",
            sql,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return res.stdout.strip()


def run_orchestrator(reel_id: str, run_id: str) -> None:
    orch_dir = REPO_ROOT / "apps" / "orchestrator"
    env = os.environ.copy()
    env["RUNWAY_API_MODE"] = "mock"
    env["PATH"] = f"{Path.home()}/.local/bin:" + env.get("PATH", "")
    cmd = [
        str(Path.home() / ".local/bin/poetry"),
        "run",
        "python",
        "-m",
        "content_lab_orchestrator.cli",
        "run",
        "--flow",
        "process_reel",
        "--reel-id",
        reel_id,
        "--run-id",
        run_id,
    ]
    res = subprocess.run(
        cmd,
        cwd=str(orch_dir),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    tail = "\n".join(res.stdout.splitlines()[-15:])
    print(f"   orchestrator exit={res.returncode}\n   tail:\n{tail}", flush=True)
    if res.returncode != 0:
        print("   stderr:\n" + res.stderr, flush=True)
        raise RuntimeError(f"Orchestrator flow failed: {res.returncode}")


def download_package(org_id: str, run_id: str, page_id: str, reel_id: str) -> Path:
    pkg = api_request("GET", f"/orgs/{org_id}/packages/{run_id}")
    target = PAGES_DIR / page_id / "reel" / reel_id
    target.mkdir(parents=True, exist_ok=True)
    (target / "package.json").write_text(json.dumps(pkg, indent=2))

    ext_by_name = {
        "final_video": "mp4",
        "cover": "png",
        "caption_variants": "txt",
        "posting_plan": "json",
    }
    for art in pkg.get("artifacts", []):
        name = art.get("name", "")
        url = (art.get("download") or {}).get("url")
        if not url:
            continue
        ext = ext_by_name.get(name, "bin")
        dest = target / f"{name}.{ext}"
        urllib.request.urlretrieve(url, str(dest))
        print(f"   downloaded {name:20s} -> {dest.relative_to(REPO_ROOT)} ({dest.stat().st_size} bytes)")

    manifest = pkg.get("manifest_download") or {}
    if manifest.get("url"):
        urllib.request.urlretrieve(manifest["url"], str(target / "package_manifest.json"))
    prov = pkg.get("provenance_download") or {}
    if prov.get("url"):
        urllib.request.urlretrieve(prov["url"], str(target / "provenance.json"))

    return target


def wait_and_sleep(page: Page, ms: int = 1000) -> None:
    page.wait_for_timeout(ms)


def main() -> int:
    banner("Creating smoke org in Postgres")
    org_id = str(uuid.uuid4())
    slug = f"ui-demo-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    pg_exec(
        f"insert into orgs (id, name, slug) values "
        f"('{org_id}', 'UI Demo Org', '{slug}');"
    )
    print(f"   org_id={org_id}", flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            record_video_dir=str(VIDEO_DIR),
            record_video_size={"width": 1440, "height": 900},
        )
        context.add_cookies(
            [
                {
                    "name": "content_lab_operator_org_id",
                    "value": org_id,
                    "url": WEB,
                }
            ]
        )
        page = context.new_page()

        banner("Opening the Content Lab operator console (home)")
        page.goto(f"{WEB}/", wait_until="networkidle")
        wait_and_sleep(page, 1200)
        screenshot(page, "home")

        banner("Opening the Pages list (empty for this fresh org)")
        page.goto(f"{WEB}/pages", wait_until="networkidle")
        wait_and_sleep(page, 1200)
        screenshot(page, "pages_empty")

        banner("Creating an owned page via POST /orgs/{org}/pages")
        page_external_id = f"ui-demo-page-{int(time.time())}"
        page_record = api_request(
            "POST",
            f"/orgs/{org_id}/pages",
            body={
                "platform": "instagram",
                "display_name": "UI Demo Reel Page",
                "external_page_id": page_external_id,
                "handle": "@ui_demo_page",
                "ownership": "owned",
                "metadata": {
                    "persona": {
                        "label": "Calm educator",
                        "audience": "Busy founders",
                        "content_pillars": ["operations"],
                    },
                    "constraints": {"allow_direct_cta": True, "max_hashtags": 4},
                    "timezone": "UTC",
                    "locale": "en",
                },
            },
        )
        page_id = page_record["id"]
        print(f"   page_id={page_id}", flush=True)

        banner("Re-loading Pages list now that one page exists")
        page.goto(f"{WEB}/pages", wait_until="networkidle")
        wait_and_sleep(page, 1200)
        screenshot(page, "pages_with_one")

        banner("Opening the page workspace detail for the new page")
        page.goto(
            f"{WEB}/orgs/{org_id}/pages/{page_id}",
            wait_until="networkidle",
        )
        wait_and_sleep(page, 1200)
        screenshot(page, "page_detail_before_reel")

        banner("Attaching a page-scoped policy (100% explore)")
        api_request(
            "PATCH",
            f"/orgs/{org_id}/policy/page/{page_id}",
            body={
                "mode_ratios": {"exploit": 0.0, "explore": 1.0, "mutation": 0.0, "chaos": 0.0},
                "budget": {
                    "per_run_usd_limit": 20.0,
                    "daily_usd_limit": 50.0,
                    "monthly_usd_limit": 500.0,
                },
            },
        )

        banner("Opening policy editor for the page")
        page.goto(
            f"{WEB}/orgs/{org_id}/pages/{page_id}/policy",
            wait_until="networkidle",
        )
        wait_and_sleep(page, 1200)
        screenshot(page, "page_policy_configured")

        banner("Creating a reel family on the page")
        family = api_request(
            "POST",
            f"/orgs/{org_id}/pages/{page_id}/reel-families",
            body={
                "name": "UI Demo Family",
                "mode": "explore",
                "metadata": {"source": "demo-recorder"},
            },
        )
        family_id = family["id"]
        print(f"   family_id={family_id}", flush=True)

        banner("Creating a draft generated reel in that family")
        reel = api_request(
            "POST",
            f"/orgs/{org_id}/pages/{page_id}/reel-families/{family_id}/reels",
            body={
                "origin": "generated",
                "status": "draft",
                "variant_label": "DemoReel-A",
                "metadata": {"source": "demo-recorder"},
            },
        )
        reel_id = reel["id"]
        print(f"   reel_id={reel_id}", flush=True)

        banner("Viewing the reel detail while it is still in draft")
        page.goto(
            f"{WEB}/orgs/{org_id}/pages/{page_id}/reels/{reel_id}",
            wait_until="networkidle",
        )
        wait_and_sleep(page, 1500)
        screenshot(page, "reel_detail_draft")

        banner("Triggering process_reel on the reel via the API")
        run = api_request(
            "POST",
            f"/orgs/{org_id}/pages/{page_id}/reels/{reel_id}/trigger",
            body={
                "input_params": {"priority": "high"},
                "metadata": {"source": "demo-recorder"},
            },
        )
        run_id = run["id"]
        print(f"   run_id={run_id}", flush=True)

        banner("Viewing the queued run detail page")
        page.goto(
            f"{WEB}/orgs/{org_id}/runs/{run_id}",
            wait_until="networkidle",
        )
        wait_and_sleep(page, 1200)
        screenshot(page, "run_detail_queued")

        banner("Executing the Prefect process_reel flow (RUNWAY_API_MODE=mock)")
        run_orchestrator(reel_id, run_id)

        banner("Re-loading the run detail — now succeeded")
        page.goto(
            f"{WEB}/orgs/{org_id}/runs/{run_id}",
            wait_until="networkidle",
        )
        wait_and_sleep(page, 1200)
        screenshot(page, "run_detail_succeeded")

        banner("Re-loading the reel detail — now ready with package artifacts")
        page.goto(
            f"{WEB}/orgs/{org_id}/pages/{page_id}/reels/{reel_id}",
            wait_until="networkidle",
        )
        wait_and_sleep(page, 1500)
        screenshot(page, "reel_detail_ready")

        banner("Opening the package detail page")
        page.goto(
            f"{WEB}/orgs/{org_id}/packages/{run_id}",
            wait_until="networkidle",
        )
        wait_and_sleep(page, 1500)
        screenshot(page, "package_detail")

        banner("Downloading the reel package for the page")
        target = download_package(org_id, run_id, page_id, reel_id)

        banner("Summary")
        summary = {
            "org_id": org_id,
            "page_id": page_id,
            "family_id": family_id,
            "reel_id": reel_id,
            "run_id": run_id,
            "artifacts_dir": str(target.relative_to(REPO_ROOT)),
            "created_at": datetime.now(UTC).isoformat(),
        }
        (OUT_ROOT / "last_run_ids.json").write_text(json.dumps(summary, indent=2))
        (OUT_ROOT / "demo_summary.json").write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary, indent=2), flush=True)

        video_path = page.video.path() if page.video else None
        context.close()
        browser.close()

    if video_path:
        final_webm = VIDEO_DIR / "reel_creation.webm"
        shutil.move(video_path, str(final_webm))
        print(f"\nSaved raw video: {final_webm.relative_to(REPO_ROOT)}", flush=True)
        final_mp4 = VIDEO_DIR / "reel_creation.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(final_webm),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-preset",
                "fast",
                "-movflags",
                "+faststart",
                str(final_mp4),
            ],
            check=True,
            capture_output=True,
        )
        print(f"Saved mp4: {final_mp4.relative_to(REPO_ROOT)}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
