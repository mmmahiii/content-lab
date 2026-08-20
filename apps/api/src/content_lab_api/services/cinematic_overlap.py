"""Resolve support-surface masks for cinematic plan validation."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from content_lab_api.models.asset import Asset
from content_lab_shared.settings import Settings
from content_lab_creative.planning_schema import CinematicReelPlan
from content_lab_editing.support_surface_overlap import OverlapValidationContext
from content_lab_qa.placement_overlap_lookup import (
    build_overlap_validation_context,
    collect_mask_uris_from_plan,
)
from content_lab_storage import S3StorageClient, S3StorageConfig


def build_cinematic_overlap_context(
    db: Session,
    plan: CinematicReelPlan,
    *,
    settings: Settings | None = None,
) -> OverlapValidationContext:
    asset_ids = plan.used_asset_ids()
    if not asset_ids:
        return OverlapValidationContext()

    parsed_ids = [uuid.UUID(asset_id) for asset_id in asset_ids]
    assets = db.query(Asset).filter(Asset.id.in_(parsed_ids)).all()
    assets_by_id = {str(asset.id): dict(asset.metadata_ or {}) for asset in assets}
    mask_uris = collect_mask_uris_from_plan(plan)
    for metadata in assets_by_id.values():
        placement = metadata.get("placement_overlap") or metadata.get("placement")
        if isinstance(placement, Mapping):
            uri = placement.get("support_surface_mask_uri")
            if uri:
                mask_uris.add(str(uri))

    settings = settings or Settings()
    client = _storage_client(settings)

    def fetch_bytes(uri: str) -> bytes | None:
        try:
            return client.get_object(storage_uri=uri).body
        except OSError:
            return None

    return build_overlap_validation_context(
        assets_by_id=assets_by_id,
        mask_uris=mask_uris,
        fetch_bytes=fetch_bytes,
    )


def _storage_client(settings: Settings) -> S3StorageClient:
    return S3StorageClient(
        S3StorageConfig(
            endpoint=settings.minio_endpoint,
            access_key_id=settings.minio_root_user,
            secret_access_key=settings.minio_root_password.get_secret_value(),
            default_bucket=settings.minio_bucket,
        )
    )
