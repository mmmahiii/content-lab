from __future__ import annotations

from content_lab_assets.store import (
    AssetMediaMetadata,
    AssetPersistenceFailure,
    merge_asset_metadata,
)


def test_merge_asset_metadata_records_ready_state_and_media_fields() -> None:
    metadata = merge_asset_metadata(
        {"intent": {"resolution": "generate"}},
        media_metadata=AssetMediaMetadata(width=1080, height=1920, fps=24, duration_seconds=6.0),
        state="ready",
        storage_uri="s3://content-lab/assets/derived/asset-123/clip.mp4",
        content_hash="sha256:" + ("a" * 64),
        size_bytes=1024,
        content_type="video/mp4",
    )

    assert metadata["width"] == 1080
    assert metadata["height"] == 1920
    assert metadata["fps"] == 24
    assert metadata["duration_seconds"] == 6.0
    assert metadata["storage"] == {
        "state": "ready",
        "storage_uri": "s3://content-lab/assets/derived/asset-123/clip.mp4",
        "content_hash": "sha256:" + ("a" * 64),
        "size_bytes": 1024,
        "content_type": "video/mp4",
    }


def test_merge_asset_metadata_replaces_failure_when_asset_becomes_ready() -> None:
    failure = AssetPersistenceFailure(
        stage="storage_write",
        message="MinIO offline",
        error_type="RuntimeError",
    )

    failed_metadata = merge_asset_metadata(
        {},
        media_metadata=AssetMediaMetadata(fps=24),
        state="failed",
        storage_uri="s3://content-lab/assets/raw/asset-123/source.bin",
        failure=failure,
    )
    recovered_metadata = merge_asset_metadata(
        failed_metadata,
        media_metadata=AssetMediaMetadata(fps=24),
        state="ready",
        storage_uri="s3://content-lab/assets/derived/asset-123/clip.mp4",
        content_hash="sha256:" + ("b" * 64),
    )

    assert failed_metadata["storage"]["failure"] == {
        "stage": "storage_write",
        "message": "MinIO offline",
        "error_type": "RuntimeError",
    }
    assert "failure" not in recovered_metadata["storage"]
    assert recovered_metadata["storage"]["state"] == "ready"
