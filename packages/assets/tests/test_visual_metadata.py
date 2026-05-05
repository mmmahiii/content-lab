from __future__ import annotations

import pytest
from pydantic import ValidationError

from content_lab_assets.types import (
    AssetVisualMetadata,
    aspect_ratio_from_dimensions,
    detect_png_visual_metadata,
)

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_chunk(chunk_type: bytes, chunk_data: bytes = b"") -> bytes:
    return len(chunk_data).to_bytes(4, byteorder="big") + chunk_type + chunk_data + b"\x00" * 4


def _png_bytes(*, width: int, height: int, color_type: int = 2) -> bytes:
    ihdr = (
        width.to_bytes(4, byteorder="big")
        + height.to_bytes(4, byteorder="big")
        + bytes([8, color_type, 0, 0, 0])
    )
    return _PNG_SIGNATURE + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IEND")


def test_visual_metadata_accepts_manual_or_generated_realism_fields() -> None:
    metadata = AssetVisualMetadata.model_validate(
        {
            "width": 1080,
            "height": 1920,
            "duration": 6,
            "fps": 24,
            "shot_type": " medium close-up ",
            "camera_angle": " eye level ",
            "perspective": " shallow depth ",
            "lighting": "soft key light",
            "colour_temperature": "warm",
            "visual_style": "cinematic realism",
            "motion_type": "slow push-in",
            "loopable": False,
            "foreground_safe": True,
            "background_safe": False,
        }
    )

    assert metadata.width == 1080
    assert metadata.height == 1920
    assert metadata.duration_seconds == 6
    assert metadata.fps == 24
    assert metadata.aspect_ratio == "9:16"
    assert metadata.shot_type == "medium close-up"
    assert metadata.camera_angle == "eye level"
    assert metadata.foreground_safe is True
    assert metadata.background_safe is False


@pytest.mark.parametrize(
    ("width", "height", "expected"),
    [
        (1080, 1920, "9:16"),
        (1920, 1080, "16:9"),
        (1024, 1024, "1:1"),
    ],
)
def test_aspect_ratio_from_dimensions(width: int, height: int, expected: str) -> None:
    assert aspect_ratio_from_dimensions(width, height) == expected


def test_visual_metadata_normalizes_explicit_aspect_ratio() -> None:
    metadata = AssetVisualMetadata(width=1920, height=1080, aspect_ratio=" 16 x 9 ")

    assert metadata.aspect_ratio == "16:9"


def test_visual_metadata_rejects_invalid_dimensions() -> None:
    with pytest.raises(ValidationError):
        AssetVisualMetadata(width=0, height=1080)


def test_detect_png_visual_metadata_populates_dimensions_and_ratio() -> None:
    metadata = detect_png_visual_metadata(_png_bytes(width=1200, height=800))

    assert metadata is not None
    assert metadata.width == 1200
    assert metadata.height == 800
    assert metadata.aspect_ratio == "3:2"


def test_detect_png_visual_metadata_returns_none_for_non_png() -> None:
    assert detect_png_visual_metadata(b"not a png") is None
