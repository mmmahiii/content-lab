"""Record a narrated walkthrough of the reel creation UI using Playwright.

Runs against a local Next.js console already seeded by
``scripts/demo/generate_one_reel.py``. Expects the ``artifacts/demo/demo_state.json``
file to contain the IDs. The script:

1. Launches Chromium with page video recording enabled.
2. Visits each relevant workspace URL (pages list, page overview, page reels,
   reel detail, run detail, and package detail).
3. Saves individual PNG screenshots for each page to
   ``artifacts/demo/screenshots/``.
4. Writes the final Playwright video (webm) to ``artifacts/demo/videos/`` and
   transcodes it to an MP4 for easy download.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

WEB_BASE_URL = "http://127.0.0.1:3000"
ARTIFACT_ROOT = Path("/workspace/artifacts/demo")
STATE_FILE = ARTIFACT_ROOT / "demo_state.json"
SCREENSHOT_DIR = ARTIFACT_ROOT / "screenshots"
VIDEO_DIR = ARTIFACT_ROOT / "videos"


def log(msg: str) -> None:
    print(f"[ui-walkthrough] {msg}", flush=True)


def capture(page: Page, label: str, url: str, *, wait_ms: int = 1800) -> None:
    log(f"navigating to {label}: {url}")
    page.goto(url, wait_until="networkidle", timeout=30_000)
    page.wait_for_timeout(wait_ms)
    path = SCREENSHOT_DIR / f"{label}.png"
    page.screenshot(path=str(path), full_page=True)
    log(f"  saved screenshot -> {path}")


def main() -> int:
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    ids = state["ui_urls"]
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    script_steps: list[tuple[str, str]] = [
        ("01_pages_list", f"{WEB_BASE_URL}/pages"),
        ("02_page_overview", f"{WEB_BASE_URL}{ids['page_overview']}"),
        ("03_page_reels", f"{WEB_BASE_URL}{ids['page_reels']}"),
        ("04_reel_detail", f"{WEB_BASE_URL}{ids['reel_detail']}"),
        ("05_run_detail", f"{WEB_BASE_URL}{ids['run_detail']}"),
        ("06_package_detail_top", f"{WEB_BASE_URL}{ids['package_detail']}"),
    ]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            record_video_dir=str(VIDEO_DIR),
            record_video_size={"width": 1400, "height": 900},
        )
        page = context.new_page()

        # Narration via console logs so the video is self-documenting.
        page.add_init_script(
            """
            (() => {
              const banner = document.createElement('div');
              banner.id = 'demo-banner';
              banner.style.cssText = `
                position: fixed; top: 8px; right: 8px; z-index: 999999;
                background: #111827; color: #f9fafb; padding: 8px 12px;
                border-radius: 8px; font: 600 13px/1.3 system-ui, sans-serif;
                box-shadow: 0 6px 20px rgba(0,0,0,0.35);
              `;
              banner.textContent = 'Content Lab — automated reel demo';
              document.addEventListener('DOMContentLoaded', () => {
                document.body && document.body.appendChild(banner);
              });
            })();
            """
        )

        for label, url in script_steps:
            capture(page, label, url)

        # Show the "Downloadable artifacts" section specifically by scrolling to it.
        log("scrolling to downloadable artifacts")
        page.goto(f"{WEB_BASE_URL}{ids['package_detail']}", wait_until="networkidle")
        page.wait_for_timeout(1000)
        locator = page.get_by_text("Downloadable artifacts", exact=False).first
        try:
            locator.scroll_into_view_if_needed(timeout=4000)
        except Exception:  # noqa: BLE001
            pass
        page.wait_for_timeout(1500)
        page.screenshot(
            path=str(SCREENSHOT_DIR / "07_package_downloads.png"), full_page=True
        )

        # Explicitly hover each Download button to prove they are real.
        log("hovering each download button")
        for name in ("final_video", "cover", "caption_variants", "posting_plan"):
            button = page.get_by_role("link", name=f"Download {name}").first
            try:
                button.hover()
                page.wait_for_timeout(900)
            except Exception:  # noqa: BLE001
                pass

        page.screenshot(
            path=str(SCREENSHOT_DIR / "08_package_hover_downloads.png"),
            full_page=True,
        )

        # Close to flush video.
        video_path = None
        try:
            video_path = page.video.path() if page.video else None
        except Exception:  # noqa: BLE001
            video_path = None
        context.close()
        browser.close()

        if video_path and Path(video_path).exists():
            log(f"raw video at {video_path}")

    # Transcode all webm videos in VIDEO_DIR to one combined MP4.
    webms = sorted(VIDEO_DIR.glob("*.webm"))
    if webms:
        latest = webms[-1]
        target = ARTIFACT_ROOT / "ui_walkthrough.mp4"
        log(f"transcoding {latest} -> {target}")
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(latest),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
                "-movflags", "+faststart",
                str(target),
            ],
            check=True,
        )
        log(f"done: {target}")
    else:
        log("no video captured (unexpected)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
