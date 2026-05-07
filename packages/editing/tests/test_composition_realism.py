from __future__ import annotations

from content_lab_editing.composition_manifest import (
    CompositionLayer,
    CompositionManifest,
    MotionTransform,
    SafeAreaConstraints,
)
from content_lab_editing.composition_realism import validate_composition_realism


def _manifest(*, layers: list[CompositionLayer]) -> CompositionManifest:
    return CompositionManifest(
        duration=4.0,
        background_layer=CompositionLayer(
            layer_id="bg",
            asset_id="bg",
            asset_kind="background_image",
            media_type="image",
            z_index=0,
            start_time=0,
            end_time=4,
        ),
        layers=layers,
    )


def _object_layer(**updates: object) -> CompositionLayer:
    payload = {
        "layer_id": "object",
        "asset_id": "object",
        "asset_kind": "transparent_cutout_png",
        "media_type": "image",
        "z_index": 1,
        "start_time": 0.0,
        "end_time": 4.0,
        "x": 320,
        "y": 760,
        "width": 420,
        "height": 420,
        "mask_mode": "alpha",
        "motion_transform": MotionTransform(preset="float"),
    }
    payload.update(updates)
    return CompositionLayer(**payload)


def _text_layer(**updates: object) -> CompositionLayer:
    payload = {
        "layer_id": "text",
        "asset_id": "text",
        "asset_kind": "hook_text",
        "media_type": "text",
        "z_index": 2,
        "start_time": 0.0,
        "end_time": 3.0,
        "x": 80,
        "y": 160,
        "width": 920,
        "height": 96,
    }
    payload.update(updates)
    return CompositionLayer(**payload)


def _codes(report: object) -> set[str]:
    payload = report.as_dict()
    return {str(item["code"]) for item in payload["findings"]}


def test_realism_report_passes_intentional_layered_composition() -> None:
    report = validate_composition_realism(
        _manifest(layers=[_object_layer(), _text_layer()]),
        asset_metadata={
            "bg": {"visual_style": ["dark_luxury"]},
            "object": {"visual_style": ["dark_luxury"], "alpha_edge_score": 0.92},
        },
    )

    assert report.passed is True
    assert report.findings == ()


def test_realism_report_flags_bad_object_size_and_frame_bounds() -> None:
    report = validate_composition_realism(
        _manifest(
            layers=[
                _object_layer(x=-30, y=100, width=1100, height=1700),
            ]
        )
    )

    codes = _codes(report)
    assert report.passed is False
    assert "foreground_too_large" in codes
    assert "layer_out_of_frame" in codes


def test_realism_report_flags_text_covering_object_and_safe_area_violation() -> None:
    report = validate_composition_realism(
        _manifest(
            layers=[
                _object_layer(),
                _text_layer(
                    x=40,
                    y=740,
                    width=800,
                    height=180,
                    safe_area_constraints=SafeAreaConstraints(top=120, left=90, right=90),
                ),
            ]
        )
    )

    codes = _codes(report)
    assert report.passed is False
    assert "text_covers_critical_object_area" in codes
    assert "safe_area_violation" in codes


def test_realism_report_warns_on_static_cutout_style_and_edge_risks() -> None:
    report = validate_composition_realism(
        _manifest(
            layers=[
                _object_layer(mask_mode="none", motion_transform=None),
            ]
        ),
        asset_metadata={
            "bg": {"visual_style": ["warm_documentary"]},
            "object": {"visual_style": ["neon_3d"], "alpha_edge_score": 0.62},
        },
    )

    payload = report.as_dict()
    warning_codes = set(payload["warning_codes"])
    assert report.passed is True
    assert "static_asset_without_motion" in warning_codes
    assert "alpha_layer_without_mask_mode" in warning_codes
    assert "alpha_edges_need_review" in warning_codes
    assert "background_object_style_mismatch" in warning_codes


def test_realism_report_warns_on_tiny_text_clipping_and_layer_clutter() -> None:
    layers = [
        _object_layer(x=-12, y=760),
        _text_layer(height=24),
        _text_layer(layer_id="text-2", asset_id="text-2", z_index=3),
        _text_layer(layer_id="text-3", asset_id="text-3", z_index=4),
        _text_layer(layer_id="text-4", asset_id="text-4", z_index=5),
        _object_layer(layer_id="object-2", asset_id="object-2", z_index=6),
        _object_layer(layer_id="object-3", asset_id="object-3", z_index=7),
        _object_layer(layer_id="object-4", asset_id="object-4", z_index=8),
        _object_layer(layer_id="object-5", asset_id="object-5", z_index=9),
    ]

    report = validate_composition_realism(_manifest(layers=layers))
    payload = report.as_dict()
    codes = _codes(report)

    assert "text_too_small" in codes
    assert "object_clipped_unintentionally" in codes
    assert "too_many_visual_layers" in payload["warning_codes"]
    assert "too_many_text_layers" in payload["warning_codes"]


def test_realism_report_fails_when_expected_transparency_is_missing() -> None:
    report = validate_composition_realism(
        _manifest(layers=[_object_layer()]),
        asset_metadata={"object": {"has_alpha": False}},
    )

    assert report.passed is False
    assert "expected_transparency_missing" in _codes(report)
