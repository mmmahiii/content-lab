"""End-to-end demo: create a page, then create & package a single reel.

This bypasses the external Runway API (no real key available) by generating a
deterministic demo source clip locally with ffmpeg, then reusing the real
in-repo editing + packaging libraries to produce the canonical ready-to-post
reel package, uploads it to MinIO, and links the package to a DB Run so the
existing `GET /orgs/{org_id}/packages/{run_id}` endpoint returns downloadable
signed URLs (exactly like a production worker would).

Outputs:
  - artifacts/demo/demo_state.json   : all IDs and URLs the UI needs
  - artifacts/demo/local_package/    : full local copy of the package
  - Data persisted in Postgres + MinIO so the UI and API can observe it
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path

API_BASE_URL = os.environ.get("CONTENT_LAB_API_BASE_URL", "http://127.0.0.1:8000")
ARTIFACT_ROOT = Path(os.environ.get("CONTENT_LAB_DEMO_ARTIFACTS", "/workspace/artifacts/demo"))
ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)


def log(step: str, message: str) -> None:
    ts = datetime.now(UTC).strftime("%H:%M:%S")
    print(f"[{ts}] [{step}] {message}", flush=True)


def http_json(method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE_URL}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        return json.loads(raw.decode("utf-8")) if raw else {}


def generate_source_clip(output_path: Path, *, duration: int = 10) -> None:
    """Generate a deterministic demo source clip (720p) with ffmpeg."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi",
            "-i", f"color=c=0x1f6feb:size=1280x720:duration={duration}:rate=30",
            "-f", "lavfi",
            "-i", f"sine=frequency=440:sample_rate=48000:duration={duration}",
            "-vf",
            (
                "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
                "text='Content Lab Demo Reel':fontcolor=white:fontsize=64:"
                "x=(w-text_w)/2:y=(h-text_h)/2-60,"
                "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
                "text='Automated generation test':fontcolor=white:fontsize=34:"
                "x=(w-text_w)/2:y=(h-text_h)/2+30"
            ),
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "96k",
            "-shortest",
            str(output_path),
        ],
        check=True,
    )


def main() -> int:
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    # Imports that need the API venv
    from content_lab_api.db import SessionLocal
    from content_lab_api.models import Org, Run

    from content_lab_editing import build_ready_to_post_package
    from content_lab_storage import (
        CanonicalStorageLayout,
        S3StorageClient,
        S3StorageConfig,
    )
    from content_lab_shared.settings import Settings

    settings = Settings()
    suffix = uuid.uuid4().hex[:6]

    log("setup", f"API base: {API_BASE_URL}")
    log("setup", f"Artifact root: {ARTIFACT_ROOT}")

    # 1. Create (or reuse) an Org directly in the DB; no public endpoint for orgs.
    with SessionLocal() as session:  # type: Session
        org = Org(name=f"Demo Org {suffix}", slug=f"demo-org-{suffix}")
        session.add(org)
        session.commit()
        session.refresh(org)
        org_id = str(org.id)
    log("org", f"created org {org_id}")

    # 2. Create a Page.
    page_body = {
        "platform": "instagram",
        "display_name": f"Demo Page {suffix}",
        "handle": f"@demo_{suffix}",
        "external_page_id": f"demo-ext-{suffix}",
        "ownership": "owned",
        "metadata": {
            "persona": {
                "label": "Demo persona",
                "audience": "Content Lab operators",
                "content_pillars": ["proof", "faq"],
            },
            "constraints": {
                "required_disclosures": [],
            },
            "timezone": "UTC",
            "locale": "en",
        },
    }
    page = http_json("POST", f"/orgs/{org_id}/pages", page_body)
    page_id = page["id"]
    log("page", f"created page {page_id}")

    # 3. Create a reel family.
    family = http_json(
        "POST",
        f"/orgs/{org_id}/pages/{page_id}/reel-families",
        {"name": "Demo Family", "mode": "explore", "metadata": {"content_pillar": "proof"}},
    )
    family_id = family["id"]
    log("family", f"created reel family {family_id}")

    # 4. Create a (generated) reel in DRAFT.
    reel = http_json(
        "POST",
        f"/orgs/{org_id}/pages/{page_id}/reel-families/{family_id}/reels",
        {
            "origin": "generated",
            "status": "draft",
            "variant_label": "A",
            "metadata": {"source": "demo-script", "content_pillar": "proof"},
        },
    )
    reel_id = reel["id"]
    log("reel", f"created reel {reel_id}")

    # 5. Generate a demo source clip locally with ffmpeg (stand-in for Runway).
    workdir = Path(tempfile.mkdtemp(prefix="content-lab-demo-"))
    source_clip = workdir / "source_clip.mp4"
    log("asset", "generating local source clip with ffmpeg")
    generate_source_clip(source_clip)
    log("asset", f"source clip ready at {source_clip} ({source_clip.stat().st_size} bytes)")

    # 6. Upload source clip to MinIO so the real editor can fetch it by URI.
    storage_client = S3StorageClient(
        S3StorageConfig(
            endpoint=settings.minio_endpoint,
            access_key_id=settings.minio_root_user,
            secret_access_key=settings.minio_root_password.get_secret_value(),
            default_bucket=settings.minio_bucket,
        )
    )
    layout = CanonicalStorageLayout(bucket=settings.minio_bucket)

    asset_id = uuid.uuid4()
    raw_ref = layout.raw_asset_object(asset_id, "source.mp4")
    storage_client.put_object(
        data=source_clip.read_bytes(),
        ref=raw_ref,
        content_type="video/mp4",
        metadata={"demo": "content-lab", "reel-id": reel_id},
    )
    log("asset", f"uploaded source clip to {raw_ref.uri}")

    # 7. Render the vertical 1080x1920 edit with the real editing library.
    from content_lab_editing import render_basic_vertical_edit

    editing_workdir = workdir / "editing"
    editing_workdir.mkdir(parents=True, exist_ok=True)
    log("edit", "running render_basic_vertical_edit")
    overlay_timeline = [
        {
            "text": "Automated reel demo",
            "start_seconds": 0.5,
            "end_seconds": 3.0,
            "font_size": 72,
            "vertical_align": "top",
        },
        {
            "text": "Content Lab",
            "start_seconds": 3.0,
            "end_seconds": 8.0,
            "font_size": 56,
            "vertical_align": "bottom",
        },
    ]
    edit_artifact = render_basic_vertical_edit(
        source_uri=raw_ref.uri,
        workdir=editing_workdir,
        storage_client=storage_client,
        overlay_timeline=overlay_timeline,
    )
    log(
        "edit",
        f"edit produced {edit_artifact.final_video_path} "
        f"({edit_artifact.width}x{edit_artifact.height}, "
        f"{edit_artifact.duration_seconds:.1f}s)",
    )

    # 8. Build the canonical ready-to-post package and push it to MinIO.
    package_workdir = workdir / "package"
    package_workdir.mkdir(parents=True, exist_ok=True)
    caption_variants = [
        {
            "variant": "default",
            "text": "Demo reel generated by Content Lab for smoke-testing the pipeline.",
        },
        {
            "variant": "alt",
            "text": "Automated reel generation demo: source -> edit -> package -> download.",
        },
    ]
    posting_plan = {
        "page_id": page_id,
        "family_id": family_id,
        "reel_id": reel_id,
        "platforms": [
            {"platform": "instagram", "schedule": "2026-04-22T15:00:00Z", "surface": "reel"}
        ],
        "hashtags": ["#demo", "#contentlab", "#automation"],
        "notes": "Generated by scripts/demo/generate_one_reel.py.",
    }
    provenance = {
        "editor_version": edit_artifact.template_version,
        "source_run_id": "demo-manual",
        "asset_ids": [str(asset_id)],
        "assets": [{"role": "source_clip", "storage_uri": raw_ref.uri}],
        "provider_jobs": [{"provider": "demo-ffmpeg", "status": "succeeded"}],
        "upstream_refs": {"timeline_uri": str(edit_artifact.cover_image_path)},
    }
    log("package", "building ready-to-post package and uploading to MinIO")
    built = build_ready_to_post_package(
        client=storage_client,
        layout=layout,
        reel_id=reel_id,
        final_video_path=edit_artifact.final_video_path,
        cover_path=edit_artifact.cover_image_path,
        caption_variants=caption_variants,
        posting_plan=posting_plan,
        provenance=provenance,
        temp_root=package_workdir,
        upload_metadata={"reel-id": reel_id, "demo": "content-lab"},
    )
    log("package", f"uploaded package to {built.stored_package.root_uri}")

    # Copy the full local package into the artifacts dir so the user can grab it.
    local_pkg_dest = ARTIFACT_ROOT / "local_package"
    if local_pkg_dest.exists():
        shutil.rmtree(local_pkg_dest)
    shutil.copytree(built.local_package.directory, local_pkg_dest)
    log("package", f"local package copy at {local_pkg_dest}")

    # 9. Create a Run row carrying the package payload so the API serves downloads.
    with SessionLocal() as session:
        run = Run(
            org_id=uuid.UUID(org_id),
            workflow_key="process_reel",
            status="succeeded",
            input_params={
                "reel_id": reel_id,
                "page_id": page_id,
                "org_id": org_id,
                "reel_family_id": family_id,
            },
            output_payload={"package": built.package_payload},
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = str(run.id)

        # Also flip the reel into READY so the page UI shows it as such.
        session.execute(
            text(
                "UPDATE reels SET status = 'ready', metadata = metadata || CAST(:extra AS jsonb) "
                "WHERE id = CAST(:reel_id AS uuid)"
            ),
            {
                "reel_id": reel_id,
                "extra": json.dumps(
                    {
                        "package_run_id": run_id,
                        "package_root_uri": built.stored_package.root_uri,
                        "process_reel": {"last_run_id": run_id},
                    }
                ),
            },
        )
        session.commit()
    log("run", f"created Run {run_id} linked to reel + package")

    # 10. Fetch the package detail via the API so we prove downloads work.
    package_detail = http_json("GET", f"/orgs/{org_id}/packages/{run_id}")
    artifacts_by_name = {a["name"]: a for a in package_detail["artifacts"]}
    final_video_download = artifacts_by_name.get("final_video", {}).get("download", {})
    log(
        "download",
        "signed download URL for final_video: "
        f"{final_video_download.get('url', '(none)')[:120]}...",
    )

    demo_state = {
        "org_id": org_id,
        "page_id": page_id,
        "family_id": family_id,
        "reel_id": reel_id,
        "run_id": run_id,
        "api_base_url": API_BASE_URL,
        "package_root_uri": built.stored_package.root_uri,
        "artifact_uris": built.stored_package.artifact_uris,
        "local_package_dir": str(local_pkg_dest),
        "ui_urls": {
            "pages_index": "/pages",
            "page_overview": f"/orgs/{org_id}/pages/{page_id}",
            "page_reels": f"/orgs/{org_id}/pages/{page_id}/reels",
            "reel_detail": f"/orgs/{org_id}/pages/{page_id}/reels/{reel_id}",
            "run_detail": f"/orgs/{org_id}/runs/{run_id}",
            "package_detail": f"/orgs/{org_id}/packages/{run_id}",
        },
        "package_detail": package_detail,
    }
    (ARTIFACT_ROOT / "demo_state.json").write_text(
        json.dumps(demo_state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    log("done", f"wrote {ARTIFACT_ROOT / 'demo_state.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
