"""End-to-end demo: seed DB rows, run the `process_reel` flow, download artifacts.

This script:
  1. Seeds an Org, an owned Page, a ReelFamily, and a Reel.
  2. Invokes the Prefect `process_reel` flow in-process (uses real Runway + MinIO).
  3. Downloads the canonical reel-package artifacts (final_video.mp4, cover,
     caption_variants, posting_plan, provenance, manifest) from MinIO into a
     local directory for inspection.

Usage:
    poetry run python /workspace/scripts/demo_reel.py --output-dir /tmp/demo_reel

The script prints a JSON summary on stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any


def _ensure_pythonpath() -> None:
    """Make every Poetry-managed app/package importable from this script."""

    repo_root = Path(__file__).resolve().parent.parent
    candidates = [
        repo_root / "apps/api/src",
        repo_root / "apps/worker/src",
        repo_root / "apps/orchestrator/src",
        repo_root / "packages/assets/src",
        repo_root / "packages/auth/src",
        repo_root / "packages/core/src",
        repo_root / "packages/creative/src",
        repo_root / "packages/editing/src",
        repo_root / "packages/features/src",
        repo_root / "packages/ingestion/src",
        repo_root / "packages/intelligence/src",
        repo_root / "packages/outbox/src",
        repo_root / "packages/qa/src",
        repo_root / "packages/runs/src",
        repo_root / "packages/shared/py/src",
        repo_root / "packages/storage/src",
    ]
    for path in candidates:
        if path.is_dir():
            sys.path.insert(0, str(path))


_ensure_pythonpath()


def _seed_fixtures(
    *,
    org_slug: str,
    page_platform: str = "instagram",
) -> dict[str, str]:
    """Insert a minimal org/page/family/reel set for the demo."""

    from content_lab_api.db import SessionLocal
    from content_lab_api.models.org import Org
    from content_lab_api.models.page import Page, PageKind
    from content_lab_api.models.reel import GeneratedReelStatus, Reel, ReelOrigin
    from content_lab_api.models.reel_family import ReelFamily

    page_metadata = {
        "timezone": "UTC",
        "locale": "en",
        "persona": {
            "label": "Mindful operator",
            "audience": "Operators who want calm, direct insight",
            "brand_tone": ["calm", "direct"],
            "content_pillars": ["focus rituals", "deep work"],
            "differentiators": ["operator-led advice"],
            "primary_call_to_action": "Subscribe for one tactic a week.",
        },
        "constraints": {
            "blocked_phrases": [],
            "allow_direct_cta": True,
            "max_script_words": 140,
        },
    }

    family_metadata = {
        "mode": "explore",
        "content_pillar": "focus rituals",
    }

    reel_metadata = {
        "duration_seconds": 5,
    }

    session = SessionLocal()
    try:
        org = session.query(Org).filter(Org.slug == org_slug).one_or_none()
        if org is None:
            org = Org(name="Demo Org", slug=org_slug)
            session.add(org)
            session.flush()

        page = (
            session.query(Page)
            .filter(
                Page.org_id == org.id,
                Page.platform == page_platform,
                Page.handle == "@demo-operator",
            )
            .one_or_none()
        )
        if page is None:
            page = Page(
                org_id=org.id,
                platform=page_platform,
                display_name="Demo Operator",
                external_page_id="demo-operator-1",
                handle="@demo-operator",
                kind=PageKind.OWNED.value,
                metadata_=page_metadata,
            )
            session.add(page)
            session.flush()

        family = ReelFamily(
            org_id=org.id,
            page_id=page.id,
            name="Focus Rituals Launch",
            metadata_=family_metadata,
        )
        session.add(family)
        session.flush()

        reel = Reel(
            org_id=org.id,
            reel_family_id=family.id,
            origin=ReelOrigin.GENERATED.value,
            status=GeneratedReelStatus.DRAFT.value,
            variant_label="A",
            metadata_=reel_metadata,
        )
        session.add(reel)
        session.flush()
        session.commit()

        return {
            "org_id": str(org.id),
            "page_id": str(page.id),
            "family_id": str(family.id),
            "reel_id": str(reel.id),
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _run_flow(reel_id: str) -> dict[str, Any]:
    """Run the Prefect `process_reel` flow synchronously."""

    from content_lab_orchestrator.flows import run_flow

    summary = run_flow("process_reel", reel_id=reel_id, dry_run=False, run_id=None)
    if not isinstance(summary, dict):
        raise TypeError(f"process_reel returned unexpected type {type(summary)!r}")
    return summary


def _download_package(reel_id: str, output_dir: Path) -> dict[str, str]:
    """Download every canonical package artifact from MinIO into ``output_dir``."""

    from content_lab_shared.settings import Settings
    from content_lab_storage import (
        CanonicalStorageLayout,
        S3StorageClient,
        S3StorageConfig,
    )

    settings = Settings()
    client = S3StorageClient(
        S3StorageConfig(
            endpoint=settings.minio_endpoint,
            access_key_id=settings.minio_root_user,
            secret_access_key=settings.minio_root_password.get_secret_value(),
            default_bucket=settings.minio_bucket,
        )
    )
    layout = CanonicalStorageLayout(bucket=settings.minio_bucket)
    refs = layout.reel_package(reel_id)

    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded: dict[str, str] = {}

    artifacts = {
        "final_video.mp4": refs.final_video,
        "cover.png": refs.cover,
        "caption_variants.txt": refs.caption_variants,
        "posting_plan.json": refs.posting_plan,
        "provenance.json": refs.provenance,
        "package_manifest.json": refs.manifest,
    }
    for filename, ref in artifacts.items():
        target = output_dir / filename
        retrieved = client.get_object(storage_uri=ref.uri)
        target.write_bytes(retrieved.body)
        downloaded[filename] = str(target)
    return downloaded


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--org-slug",
        default="demo-org",
        help="Slug used to look up or create the demo org.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/tmp/demo_reel_artifacts"),
        help="Directory to download canonical artifacts into.",
    )
    args = parser.parse_args(argv)

    seeded = _seed_fixtures(org_slug=args.org_slug + "-" + uuid.uuid4().hex[:6])
    print(json.dumps({"phase": "seeded", "ids": seeded}, indent=2), flush=True)

    summary = _run_flow(seeded["reel_id"])
    print(
        json.dumps(
            {
                "phase": "flow_complete",
                "reel_status": summary.get("reel_status"),
                "run_status": summary.get("run_status"),
                "task_statuses": summary.get("task_statuses"),
                "package_root_uri": (summary.get("package") or {}).get("package_root_uri"),
            },
            indent=2,
        ),
        flush=True,
    )

    downloaded = _download_package(seeded["reel_id"], args.output_dir)
    print(
        json.dumps(
            {
                "phase": "artifacts_downloaded",
                "output_dir": str(args.output_dir),
                "files": downloaded,
            },
            indent=2,
        ),
        flush=True,
    )

    env_vars = {key: os.environ.get(key, "") for key in ("MINIO_BUCKET", "MINIO_ENDPOINT")}
    print(json.dumps({"phase": "done", "env": env_vars}, indent=2), flush=True)


if __name__ == "__main__":
    main()
