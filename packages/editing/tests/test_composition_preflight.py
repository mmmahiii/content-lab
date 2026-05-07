from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from content_lab_editing.composition_manifest import (
    CompositionLayer,
    CompositionManifest,
    MediaType,
)
from content_lab_editing.composition_preflight import (
    CompositionPreflightError,
    SourceAssetReference,
    ensure_composition_preflight,
    validate_composition_manifest,
    validate_source_asset_availability,
)


def _layer(
    layer_id: str,
    *,
    asset_id: str | None = None,
    asset_kind: str = "background_image",
    media_type: MediaType = "image",
    z_index: int = 0,
    start_time: float = 0.0,
    end_time: float = 6.0,
) -> CompositionLayer:
    return CompositionLayer(
        layer_id=layer_id,
        asset_id=asset_id or f"asset-{layer_id}",
        asset_kind=asset_kind,
        media_type=media_type,
        z_index=z_index,
        start_time=start_time,
        end_time=end_time,
    )


def _manifest() -> CompositionManifest:
    return CompositionManifest(
        duration=6.0,
        background_layer=_layer("background", asset_id="asset-bg"),
        layers=[
            _layer(
                "foreground",
                asset_id="asset-fg",
                asset_kind="transparent_cutout_png",
                z_index=1,
            )
        ],
        audio_layers=[
            _layer(
                "audio",
                asset_id="asset-audio",
                asset_kind="audio_track",
                media_type="audio",
            )
        ],
    )


@dataclass(frozen=True, slots=True)
class _StoredObject:
    content_type: str = "image/png"


class _StorageProbe:
    def __init__(self, existing_uris: set[str]) -> None:
        self.existing_uris = existing_uris

    def head_object(self, *, storage_uri: str) -> _StoredObject:
        if storage_uri not in self.existing_uris:
            raise FileNotFoundError(storage_uri)
        return _StoredObject()


def test_source_asset_preflight_accepts_ready_assets_with_storage_objects() -> None:
    manifest = _manifest()
    sources = {
        "asset-bg": SourceAssetReference(
            source="s3://content-lab/bg.png",
            media_type="image/png",
            content_hash="sha256:" + ("a" * 64),
            status="ready",
        ),
        "asset-fg": SourceAssetReference(
            source="s3://content-lab/fg.png",
            media_type="image",
            content_hash="sha256:" + ("b" * 64),
            status="ready",
        ),
        "asset-audio": SourceAssetReference(
            source="s3://content-lab/audio.wav",
            media_type="audio/wav",
            content_hash="sha256:" + ("c" * 64),
            status="ready",
        ),
    }

    issues = validate_source_asset_availability(
        manifest,
        asset_sources=sources,
        storage_client=_StorageProbe({str(ref.source) for ref in sources.values()}),
    )

    assert issues == []


def test_source_asset_preflight_reports_operator_readable_asset_failures(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    bg = tmp_path / "bg.png"
    bg.write_bytes(b"bg")
    issues = validate_source_asset_availability(
        manifest,
        asset_sources={
            "asset-bg": {
                "storage_uri": bg,
                "media_type": "video",
                "content_hash": "sha256:" + ("a" * 64),
                "asset_status": "ready",
            },
            "asset-fg": {
                "storage_uri": "s3://content-lab/missing.png",
                "media_type": "image",
                "content_hash": "sha256:" + ("b" * 64),
                "asset_status": "ready",
            },
            "asset-audio": {
                "storage_uri": "s3://content-lab/audio.wav",
                "media_type": "audio",
                "asset_status": "draft",
            },
        },
        storage_client=_StorageProbe({"s3://content-lab/audio.wav"}),
    )

    assert [issue.code for issue in issues] == [
        "media_type_mismatch",
        "storage_object_missing",
        "asset_status_not_ready",
        "content_hash_missing",
    ]
    assert all(issue.message for issue in issues)


def test_manifest_preflight_reports_bad_constructed_manifest() -> None:
    background = _layer("background", asset_id="asset-bg", end_time=3.0)
    manifest = CompositionManifest.model_construct(
        canvas_width=0,
        canvas_height=1920,
        duration=6.0,
        fps=24,
        background_layer=background,
        layers=[
            _layer("top", z_index=2),
            _layer("bottom", z_index=1),
        ],
        audio_layers=[],
        export_preset=CompositionManifest(duration=1.0, background_layer=background).export_preset,
    )

    issues = validate_composition_manifest(manifest)

    assert "invalid_canvas_dimensions" in {issue.code for issue in issues}
    assert "background_duration_incomplete" in {issue.code for issue in issues}
    assert "z_index_order_invalid" in {issue.code for issue in issues}


def test_ensure_composition_preflight_raises_before_render_for_missing_source() -> None:
    with pytest.raises(CompositionPreflightError, match="missing asset source"):
        ensure_composition_preflight(
            _manifest(),
            asset_sources={"asset-bg": "memory://bg.png"},
            require_content_hash=False,
        )
