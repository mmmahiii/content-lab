from __future__ import annotations

from datetime import UTC, datetime

from content_lab_assets.provenance import (
    PackageAssetProvenance,
    build_provenance,
    serialize_provenance_json,
)


def test_build_provenance_redacts_provider_credentials_and_sorts_timeline() -> None:
    created_at = datetime(2026, 3, 25, 10, 30, tzinfo=UTC)
    packaged_at = datetime(2026, 3, 25, 10, 45, tzinfo=UTC)

    provenance = build_provenance(
        assets=[
            {
                "role": "final_video",
                "stage": "output",
                "asset_id": "asset-output",
                "storage_uri": "s3://content-lab/reels/packages/reel-1/final_video.mp4",
                "kind": "video",
                "metadata": {"checksum": "sha256:video"},
            },
            {
                "role": "source_clip",
                "stage": "input",
                "asset_id": "asset-input",
                "storage_uri": "s3://content-lab/assets/raw/asset-input/source.mp4",
                "kind": "video",
                "source": "runway",
                "asset_key_hash": "hash-123",
            },
        ],
        generation_params={
            "prompt": "Hero launch shot",
            "seed": 7,
            "api_key": "sk-live-12345678",
        },
        provider_jobs=[
            {
                "provider": "runway",
                "model": "gen4.5",
                "status": "succeeded",
                "job_id": "job-123",
                "task_id": "task-123",
                "external_ref": "runway-gen45:hash-123",
                "submitted_at": created_at,
                "completed_at": packaged_at,
                "request": {
                    "Authorization": "Bearer super-secret-token",
                    "prompt": "Hero launch shot",
                },
                "response": {
                    "output_url": "https://example.invalid/video.mp4",
                    "token": "provider-token",
                },
            }
        ],
        editor_version="basic_vertical_v1",
        package_timestamps={
            "packaged_at": packaged_at,
            "assets_resolved_at": created_at,
        },
    )

    payload = provenance.model_dump(mode="json")
    assert payload["generation_params"]["api_key"] == "***REDACTED***"
    assert payload["provider_jobs"][0]["request"]["Authorization"] == "***REDACTED***"
    assert payload["provider_jobs"][0]["response"]["token"] == "***REDACTED***"
    assert payload["package_timestamps"] == [
        {"label": "assets_resolved_at", "timestamp": "2026-03-25T10:30:00Z"},
        {"label": "packaged_at", "timestamp": "2026-03-25T10:45:00Z"},
    ]
    assert payload["summary"] == {
        "asset_count": 2,
        "provider_job_count": 1,
        "asset_roles": ["source_clip", "final_video"],
        "provider_refs": ["job-123"],
        "timestamp_labels": ["assets_resolved_at", "packaged_at"],
        "provider_credentials_redacted": True,
    }


def test_provenance_json_is_stable_for_equivalent_mappings() -> None:
    timestamp = datetime(2026, 3, 25, 11, 0, tzinfo=UTC)

    first = build_provenance(
        assets=[
            {
                "role": "cover",
                "stage": "output",
                "storage_uri": "s3://content-lab/reels/packages/reel-1/cover.png",
                "metadata": {"b": 2, "a": 1},
            }
        ],
        generation_params={"b": 2, "a": 1},
        provider_jobs=[
            {
                "provider": "runway",
                "status": "submitted",
                "request": {"b": 2, "a": 1},
            }
        ],
        editor_version="basic_vertical_v1",
        package_timestamps={"packaged_at": timestamp},
    )
    second = build_provenance(
        assets=[
            {
                "role": "cover",
                "stage": "output",
                "storage_uri": "s3://content-lab/reels/packages/reel-1/cover.png",
                "metadata": {"a": 1, "b": 2},
            }
        ],
        generation_params={"a": 1, "b": 2},
        provider_jobs=[
            {
                "provider": "runway",
                "status": "submitted",
                "request": {"a": 1, "b": 2},
            }
        ],
        editor_version="basic_vertical_v1",
        package_timestamps={"packaged_at": timestamp},
    )

    assert serialize_provenance_json(first) == serialize_provenance_json(second)


def test_package_asset_provenance_backfills_source_first_fields() -> None:
    imported_at = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)

    asset = PackageAssetProvenance(
        role="product_prop",
        asset_id="asset-imported",
        storage_uri="s3://content-lab/assets/raw/asset-imported/product.png",
        content_hash="sha256:" + ("a" * 64),
        metadata={
            "asset_kind": "object_image",
            "media_type": "image",
            "source_metadata": {
                "source_type": "approved_external_source",
                "source_provider": "Example Stock",
                "external_source_url": "https://cdn.example.com/product.png",
                "licence_type": "custom",
                "usage_allowed": True,
                "attribution_required": True,
                "attribution_text": "Image: Example Stock",
                "original_content_hash": "sha256:" + ("b" * 64),
                "imported_at": imported_at.isoformat(),
            },
        },
    )

    assert asset.asset_kind == "object_image"
    assert asset.media_type == "image"
    assert asset.source_type == "approved_external_source"
    assert asset.source_provider == "Example Stock"
    assert asset.licence_type == "custom"
    assert asset.usage_allowed is True
    assert asset.attribution_text == "Image: Example Stock"
    assert asset.original_content_hash == "sha256:" + ("b" * 64)
    assert asset.stored_content_hash == "sha256:" + ("a" * 64)
    assert asset.used_as_component_role == "product_prop"
