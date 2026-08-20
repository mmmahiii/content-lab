from __future__ import annotations

import pytest
from pydantic import ValidationError

from content_lab_assets.types import (
    AlphaMode,
    AssetKind,
    AssetRegion,
    AssetTransparencyMetadata,
    MediaType,
    compatible_media_types_for_asset_kind,
    detect_png_transparency,
    infer_media_type_for_asset_kind,
    validate_asset_kind_media_type,
)

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_chunk(chunk_type: bytes, chunk_data: bytes = b"") -> bytes:
    return len(chunk_data).to_bytes(4, byteorder="big") + chunk_type + chunk_data + b"\x00" * 4


def _png_bytes(*, color_type: int, extra_chunks: tuple[bytes, ...] = ()) -> bytes:
    ihdr = (
        (1).to_bytes(4, byteorder="big")
        + (1).to_bytes(4, byteorder="big")
        + bytes([8, color_type, 0, 0, 0])
    )
    return _PNG_SIGNATURE + _png_chunk(b"IHDR", ihdr) + b"".join(extra_chunks) + _png_chunk(b"IEND")


def test_media_type_includes_required_values() -> None:
    assert {media_type.value for media_type in MediaType} == {
        "image",
        "video",
        "audio",
        "text",
        "json",
        "package",
        "unknown",
    }


@pytest.mark.parametrize(
    ("asset_kind", "media_type"),
    [
        (AssetKind.OBJECT_IMAGE, MediaType.IMAGE),
        (AssetKind.OBJECT_VIDEO, MediaType.VIDEO),
        (AssetKind.BACKGROUND_IMAGE, MediaType.IMAGE),
        (AssetKind.BACKGROUND_VIDEO, MediaType.VIDEO),
        (AssetKind.AUDIO_TRACK, MediaType.AUDIO),
        (AssetKind.HOOK_TEXT, MediaType.TEXT),
        (AssetKind.OVERLAY_PLAN, MediaType.JSON),
        (AssetKind.PACKAGE_ARTIFACT, MediaType.PACKAGE),
        (AssetKind.PROVENANCE_ARTIFACT, MediaType.JSON),
    ],
)
def test_asset_kind_media_type_compatibility(
    asset_kind: AssetKind,
    media_type: MediaType,
) -> None:
    assert media_type in compatible_media_types_for_asset_kind(asset_kind)
    assert (
        validate_asset_kind_media_type(asset_kind=asset_kind, media_type=media_type) is media_type
    )


def test_text_and_json_assets_are_not_treated_as_video() -> None:
    assert infer_media_type_for_asset_kind(AssetKind.HOOK_TEXT) is MediaType.TEXT
    assert infer_media_type_for_asset_kind(AssetKind.OVERLAY_PLAN) is MediaType.JSON

    with pytest.raises(ValueError, match="not compatible"):
        validate_asset_kind_media_type(
            asset_kind=AssetKind.HOOK_TEXT,
            media_type=MediaType.VIDEO,
        )


def test_unknown_media_type_is_allowed_as_an_explicit_fallback() -> None:
    assert (
        validate_asset_kind_media_type(
            asset_kind=AssetKind.TRANSPARENT_CUTOUT_PNG,
            media_type=MediaType.UNKNOWN,
        )
        is MediaType.UNKNOWN
    )


def test_transparency_metadata_represents_cutout_images() -> None:
    metadata = AssetTransparencyMetadata(
        alpha_mode=AlphaMode.ALPHA,
        has_transparency=True,
        subject_bbox=AssetRegion(x=0.2, y=0.1, width=0.5, height=0.7),
        safe_crop=AssetRegion(x=0.1, y=0.05, width=0.8, height=0.85),
    )

    assert metadata.has_transparency is True
    assert metadata.alpha_mode is AlphaMode.ALPHA
    assert metadata.model_dump(mode="json")["subject_bbox"] == {
        "x": 0.2,
        "y": 0.1,
        "width": 0.5,
        "height": 0.7,
    }


def test_placement_overlap_metadata_from_registry_metadata() -> None:
    from content_lab_assets.types import AssetPlacementOverlapMetadata

    metadata = AssetPlacementOverlapMetadata.from_metadata(
        {"placement_overlap": {"support_surface_mask_uri": "s3://masks/plate.png"}}
    )

    assert metadata.support_surface_mask_uri == "s3://masks/plate.png"


def test_mask_transparency_requires_mask_uri() -> None:
    with pytest.raises(ValidationError, match="mask_uri is required"):
        AssetTransparencyMetadata(alpha_mode=AlphaMode.MASK, has_transparency=True)


def test_alpha_mode_none_cannot_claim_transparency() -> None:
    with pytest.raises(ValidationError, match="cannot have transparency"):
        AssetTransparencyMetadata(alpha_mode=AlphaMode.NONE, has_transparency=True)


def test_detect_png_transparency_detects_rgba_alpha_channel() -> None:
    metadata = detect_png_transparency(_png_bytes(color_type=6))

    assert metadata.alpha_mode is AlphaMode.ALPHA
    assert metadata.has_transparency is True


def test_detect_png_transparency_detects_trns_chunk() -> None:
    metadata = detect_png_transparency(
        _png_bytes(color_type=2, extra_chunks=(_png_chunk(b"tRNS", b"\x00" * 6),))
    )

    assert metadata.alpha_mode is AlphaMode.ALPHA
    assert metadata.has_transparency is True


def test_detect_png_transparency_marks_opaque_png_as_none() -> None:
    metadata = detect_png_transparency(_png_bytes(color_type=2))

    assert metadata.alpha_mode is AlphaMode.NONE
    assert metadata.has_transparency is False


def test_detect_png_transparency_returns_unknown_for_non_png() -> None:
    metadata = detect_png_transparency(b"not a png")

    assert metadata.alpha_mode is AlphaMode.UNKNOWN
    assert metadata.has_transparency is False
