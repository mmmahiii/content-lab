"""Asset-byte persistence helpers for staged assets."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from content_lab_api.models import Asset
from content_lab_assets.store import (
    AssetMediaMetadata,
    AssetPersistenceFailure,
    AssetPersistenceRecord,
    merge_asset_metadata,
)
from content_lab_shared.settings import Settings
from content_lab_storage import CanonicalStorageLayout, S3StorageClient, S3StorageConfig
from content_lab_storage.assets import StoredAssetBytes, persist_asset_bytes

_FAILED_ASSET_STATUS = "failed"
_READY_ASSET_STATUS = "ready"
_STAGED_ASSET_STATUS = "staged"
_PERSISTABLE_ASSET_STATUSES = frozenset({_FAILED_ASSET_STATUS, _STAGED_ASSET_STATUS})


class AssetPersistenceStateError(ValueError):
    """Raised when an asset is not in a persistable state."""


def persist_asset_content(
    db: Session,
    *,
    asset_id: uuid.UUID,
    data: bytes,
    content_type: str | None = None,
    filename: str | None = None,
    width: int | None = None,
    height: int | None = None,
    fps: int | None = None,
    duration_seconds: float | int | None = None,
    storage_client: S3StorageClient | None = None,
    settings: Settings | None = None,
) -> Asset:
    """Persist staged asset bytes and mark the asset ready only after DB registration succeeds."""

    asset = _get_asset_or_raise(db, asset_id)
    _ensure_persistable(asset)

    resolved_settings = settings or Settings()
    client = storage_client or _build_storage_client(resolved_settings)
    layout = CanonicalStorageLayout(bucket=resolved_settings.minio_bucket)
    media_metadata = AssetMediaMetadata(
        width=width,
        height=height,
        fps=fps,
        duration_seconds=duration_seconds,
    )

    try:
        stored = persist_asset_bytes(
            client=client,
            layout=layout,
            asset_id=asset.id,
            asset_class=asset.asset_class,
            data=data,
            content_type=content_type,
            filename=filename,
            metadata=_storage_object_metadata(asset),
        )
    except Exception as exc:
        _mark_asset_failed(
            db,
            asset=asset,
            media_metadata=media_metadata,
            failure=AssetPersistenceFailure(
                stage="storage_write",
                message=str(exc),
                error_type=type(exc).__name__,
            ),
        )
        raise

    ready_record = _ready_record(stored, media_metadata=media_metadata)
    try:
        _apply_ready_state(asset, record=ready_record)
        db.commit()
    except Exception as exc:
        db.rollback()
        failed_asset = _get_asset_or_raise(db, asset_id)
        _mark_asset_failed(
            db,
            asset=failed_asset,
            media_metadata=media_metadata,
            record=ready_record,
            failure=AssetPersistenceFailure(
                stage="metadata_persistence",
                message=str(exc),
                error_type=type(exc).__name__,
            ),
        )
        raise

    db.refresh(asset)
    return asset


def _apply_ready_state(asset: Asset, *, record: AssetPersistenceRecord) -> None:
    asset.status = _READY_ASSET_STATUS
    asset.storage_uri = record.storage_uri
    asset.content_hash = record.content_hash
    asset.metadata_ = merge_asset_metadata(
        asset.metadata_,
        media_metadata=record.media_metadata,
        state=_READY_ASSET_STATUS,
        storage_uri=record.storage_uri,
        content_hash=record.content_hash,
        size_bytes=record.size_bytes,
        content_type=record.content_type,
    )


def _mark_asset_failed(
    db: Session,
    *,
    asset: Asset,
    media_metadata: AssetMediaMetadata,
    failure: AssetPersistenceFailure,
    record: AssetPersistenceRecord | None = None,
) -> None:
    asset.status = _FAILED_ASSET_STATUS
    if record is not None:
        asset.storage_uri = record.storage_uri
        asset.content_hash = record.content_hash
    asset.metadata_ = merge_asset_metadata(
        asset.metadata_,
        media_metadata=media_metadata,
        state=_FAILED_ASSET_STATUS,
        storage_uri=asset.storage_uri,
        content_hash=asset.content_hash,
        size_bytes=None if record is None else record.size_bytes,
        content_type=None if record is None else record.content_type,
        failure=failure,
    )
    db.commit()


def _ready_record(
    stored: StoredAssetBytes,
    *,
    media_metadata: AssetMediaMetadata,
) -> AssetPersistenceRecord:
    return AssetPersistenceRecord(
        storage_uri=stored.storage_uri,
        content_hash=stored.checksums.content_hash,
        size_bytes=stored.stored_object.size_bytes,
        content_type=stored.stored_object.content_type,
        media_metadata=media_metadata,
    )


def _storage_object_metadata(asset: Asset) -> dict[str, str]:
    return {
        "asset-class": asset.asset_class,
        "asset-id": str(asset.id),
        "org-id": str(asset.org_id),
    }


def _get_asset_or_raise(db: Session, asset_id: uuid.UUID) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise LookupError(f"Asset {asset_id} was not found")
    return asset


def _ensure_persistable(asset: Asset) -> None:
    if asset.status not in _PERSISTABLE_ASSET_STATUSES:
        raise AssetPersistenceStateError(
            f"Asset {asset.id} must be in one of {_PERSISTABLE_ASSET_STATUSES!r} before persistence"
        )


def _build_storage_client(settings: Settings) -> S3StorageClient:
    return S3StorageClient(
        S3StorageConfig(
            endpoint=settings.minio_endpoint,
            access_key_id=settings.minio_root_user,
            secret_access_key=settings.minio_root_password.get_secret_value(),
            default_bucket=settings.minio_bucket,
        )
    )
