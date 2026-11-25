"""Seed a small local workspace for trying Quick Reel (/make). Idempotent, no network.

Creates (or reuses) org ``quick-reel-demo`` with two pages:

- **Crispy Kitchen** (niche ``cooking``) with a ready ``cooking`` asset pack built from the
  cut-out PNGs already in ``artifacts/asset_packs/faceless_cooking_real_png/`` (uploaded to
  MinIO), so Quick Reel uses real images;
- **Iron Habit** (niche ``fitness``) with no pack, so Quick Reel uses the gradient backdrop.

Run from ``apps/api`` with Postgres and MinIO up and migrations applied:

    poetry run python ../../scripts/seed_quick_reel_demo.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

from botocore.exceptions import ClientError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from content_lab_api.models import Asset, AssetPack, AssetPackItem, Org, Page, PageKind
from content_lab_shared.settings import Settings
from content_lab_storage.client import S3StorageClient
from content_lab_storage.config import S3StorageConfig

REPO = Path(__file__).resolve().parents[1]
PNG_DIR = REPO / "artifacts/asset_packs/faceless_cooking_real_png/20260511-164911"
IMAGES = ["basil", "bell_pepper", "cut_eggplant", "broccoli", "ginger", "fresh_vegetables"]
ORG_SLUG = "quick-reel-demo"
PACK_NAME = "Kitchen cut-outs (Quick Reel demo)"


def _storage(settings: Settings) -> tuple[S3StorageClient, str]:
    client = S3StorageClient(
        S3StorageConfig(
            endpoint=settings.minio_endpoint,
            access_key_id=settings.minio_root_user,
            secret_access_key=settings.minio_root_password.get_secret_value(),
            default_bucket=settings.minio_bucket,
        )
    )
    raw = client._client  # noqa: SLF001 - bucket bootstrap only
    try:
        raw.head_bucket(Bucket=settings.minio_bucket)
    except ClientError:
        raw.create_bucket(Bucket=settings.minio_bucket)
    return client, settings.minio_bucket


def _page(db: Session, org: Org, name: str, handle: str, metadata: dict[str, object]) -> Page:
    page = db.query(Page).filter(Page.org_id == org.id, Page.handle == handle).one_or_none()
    if page is None:
        page = Page(
            org_id=org.id,
            platform="instagram",
            display_name=name,
            handle=handle,
            external_page_id=f"demo-{handle}",
            kind=PageKind.OWNED.value,
            metadata_=metadata,
        )
        db.add(page)
        db.flush()
    else:
        page.metadata_ = metadata
    return page


def main() -> int:
    settings = Settings()
    missing = [name for name in IMAGES if not (PNG_DIR / f"{name}.png").exists()]
    if missing:
        print(f"Missing demo images in {PNG_DIR}: {missing}", file=sys.stderr)
        return 1
    storage, bucket = _storage(settings)
    engine = create_engine(settings.database_url)
    with Session(engine) as db:
        org = db.query(Org).filter(Org.slug == ORG_SLUG).one_or_none()
        if org is None:
            org = Org(name="Quick Reel Demo", slug=ORG_SLUG)
            db.add(org)
            db.flush()
        kitchen = _page(
            db,
            org,
            "Crispy Kitchen",
            "crispykitchen",
            {
                "niche": "cooking",
                "persona": {
                    "label": "Home cook",
                    "audience": "busy weeknight cooks",
                    "content_pillars": ["crispy potatoes", "weeknight dinners"],
                },
            },
        )
        _page(
            db,
            org,
            "Iron Habit",
            "ironhabit",
            {
                "niche": "fitness",
                "persona": {
                    "label": "Strength coach",
                    "audience": "new lifters",
                    "content_pillars": ["squat depth", "first pull-up"],
                },
            },
        )

        pack = (
            db.query(AssetPack)
            .filter(AssetPack.org_id == org.id, AssetPack.name == PACK_NAME)
            .one_or_none()
        )
        if pack is None:
            pack = AssetPack(
                org_id=org.id,
                name=PACK_NAME,
                niche="cooking",
                requested_asset_count=len(IMAGES),
                status="ready",
                purpose="Quick Reel local demo",
            )
            db.add(pack)
            db.flush()
            for priority, name in enumerate(IMAGES):
                asset_id = uuid.uuid4()
                key = f"assets/derived/{asset_id}/{name}.png"
                storage.put_object(
                    ref=storage.build_ref(key, bucket=bucket),
                    data=(PNG_DIR / f"{name}.png").read_bytes(),
                    content_type="image/png",
                )
                label = name.replace("_", " ")
                asset = Asset(
                    org_id=org.id,
                    asset_class="image",
                    storage_uri=f"s3://{bucket}/{key}",
                    source="seed",
                    status="ready",
                    metadata_={
                        "asset_kind": "cutout",
                        "media_type": "image",
                        "has_transparency": True,
                        "label": label,
                        "tags": [label, "cooking"],
                        "niche": "cooking",
                    },
                )
                asset.id = asset_id
                db.add(asset)
                db.flush()
                db.add(
                    AssetPackItem(
                        asset_pack_id=pack.id,
                        asset_kind="cutout",
                        pack_role="subject",
                        asset_id=asset_id,
                        priority=priority,
                        status="uploaded",
                    )
                )
        db.commit()
        print(f"org={org.id} kitchen_page={kitchen.id} pack={pack.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
