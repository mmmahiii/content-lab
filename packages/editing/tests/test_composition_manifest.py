from __future__ import annotations

import pytest
from pydantic import ValidationError

from content_lab_editing.composition_manifest import (
    CompositionLayer,
    CompositionManifest,
    MotionTransform,
)


def _layer(
    layer_id: str,
    *,
    asset_id: str | None = None,
    asset_kind: str = "background_video",
    media_type: str = "video",
    z_index: int = 0,
    start_time: float = 0.0,
    end_time: float = 6.0,
    x: int = 0,
    y: int = 0,
    width: int | None = 1080,
    height: int | None = 1920,
    motion_transform: MotionTransform | None = None,
) -> CompositionLayer:
    return CompositionLayer(
        layer_id=layer_id,
        asset_id=asset_id or layer_id,
        asset_kind=asset_kind,
        media_type=media_type,
        z_index=z_index,
        start_time=start_time,
        end_time=end_time,
        x=x,
        y=y,
        width=width,
        height=height,
        motion_transform=motion_transform,
    )


def test_composition_manifest_contract_accepts_layered_reel_payload() -> None:
    manifest = CompositionManifest(
        duration=6.0,
        fps=24,
        background_layer=_layer("background", z_index=0),
        layers=[
            _layer(
                "foreground",
                asset_kind="transparent_cutout_png",
                media_type="image",
                z_index=1,
                width=640,
                height=640,
            ),
            _layer(
                "hook",
                asset_kind="hook_text",
                media_type="text",
                z_index=2,
                x=90,
                y=220,
                width=900,
                height=72,
            ),
        ],
        audio_layers=[
            _layer(
                "audio",
                asset_kind="audio_track",
                media_type="audio",
                z_index=0,
                width=None,
                height=None,
            )
        ],
    )

    assert manifest.canvas_width == 1080
    assert manifest.canvas_height == 1920
    assert [layer.layer_id for layer in manifest.visual_layers_in_render_order] == [
        "foreground",
        "hook",
    ]
    assert manifest.asset_ids == ("background", "foreground", "hook", "audio")


def test_manifest_rejects_layer_timing_outside_duration() -> None:
    with pytest.raises(ValidationError, match="exceeds manifest duration"):
        CompositionManifest(
            duration=6.0,
            background_layer=_layer("background"),
            layers=[_layer("late", z_index=1, end_time=7.0)],
        )


def test_manifest_rejects_unsorted_or_duplicate_z_indexes() -> None:
    with pytest.raises(ValidationError, match="ascending z_index"):
        CompositionManifest(
            duration=6.0,
            background_layer=_layer("background"),
            layers=[
                _layer("top", z_index=2),
                _layer("bottom", z_index=1),
            ],
        )

    with pytest.raises(ValidationError, match="z_index values must be unique"):
        CompositionManifest(
            duration=6.0,
            background_layer=_layer("background"),
            layers=[
                _layer("first", z_index=1),
                _layer("second", z_index=1),
            ],
        )


def test_manifest_rejects_asset_type_mismatches() -> None:
    with pytest.raises(ValidationError, match="background_layer must use image or video"):
        CompositionManifest(
            duration=6.0,
            background_layer=_layer("bad-bg", asset_kind="audio_track", media_type="audio"),
        )

    with pytest.raises(ValidationError, match="audio-compatible asset_kind"):
        _layer("bad-audio", asset_kind="background_video", media_type="audio")


def test_manifest_accepts_motion_transform_presets() -> None:
    layer = _layer(
        "floating-object",
        asset_kind="transparent_cutout_png",
        media_type="image",
        motion_transform=MotionTransform(preset="float", amplitude=18, frequency=0.8),
    )

    assert layer.motion_transform is not None
    assert layer.motion_transform.preset == "float"
    assert layer.motion_transform.amplitude == 18
