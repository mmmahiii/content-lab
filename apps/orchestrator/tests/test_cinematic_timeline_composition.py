from __future__ import annotations

from content_lab_orchestrator.flows.process_reel import (
    _cinematic_composition_duration_seconds,
    _composition_manifest_from_cinematic_plan,
    _retime_canonical_timeline_payload,
    _validate_duration_contract,
)


def _role(asset_id: str, *, storage_uri: str, asset_kind: str = "transparent_cutout_png") -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "asset_kind": asset_kind,
        "storage_uri": storage_uri,
        "media_type": "image/png",
    }


def test_cinematic_plan_composition_uses_timeline_positions_and_rejections() -> None:
    manifest, _ = _composition_manifest_from_cinematic_plan(
        manifest_payload={
            "cinematic_plan": {
                "canvas": {"width": 1080, "height": 1920},
                "fps": 24,
                "total_duration_seconds": 6.5,
                "provenance": {
                    "rejected_assets": [
                        {"asset_id": "rejected-plant", "reason": "Duplicate/clutter."}
                    ]
                },
                "scenes": [
                    {
                        "objects": [
                            {
                                "object_id": "base",
                                "asset_id": "counter",
                                "role": "environment_base",
                                "start_time": 0.0,
                                "end_time": 6.5,
                                "x": 0.5,
                                "y": 0.5,
                                "z": 0.05,
                                "width_normalised": 1.0,
                                "height_normalised": 1.0,
                                "scale": 1.0,
                            },
                            {
                                "object_id": "steak_hero_hook",
                                "asset_id": "steak",
                                "role": "hero_subject",
                                "start_time": 0.0,
                                "end_time": 1.4,
                                "x": 0.48,
                                "y": 0.64,
                                "z": 0.82,
                                "width_normalised": 0.52,
                                "height_normalised": 0.3,
                                "scale": 0.82,
                                "opacity": 1.0,
                            },
                            {
                                "object_id": "steak_hero_payoff",
                                "asset_id": "steak",
                                "role": "narrative_payoff",
                                "start_time": 1.4,
                                "end_time": 6.5,
                                "x": 0.55,
                                "y": 0.59,
                                "z": 0.83,
                                "width_normalised": 0.64,
                                "height_normalised": 0.36,
                                "scale": 0.88,
                                "opacity": 1.0,
                            },
                            {
                                "object_id": "plant_rear",
                                "asset_id": "plant",
                                "role": "background_reveal",
                                "start_time": 1.7,
                                "end_time": 3.7,
                                "x": 0.9,
                                "y": 0.18,
                                "z": 0.22,
                                "width_normalised": 0.2,
                                "height_normalised": 0.24,
                                "scale": 0.2,
                                "opacity": 0.55,
                            },
                            {
                                "object_id": "side_pan",
                                "asset_id": "pan",
                                "role": "supporting_subject",
                                "start_time": 1.7,
                                "end_time": 3.7,
                                "x": 0.2,
                                "y": 0.72,
                                "z": 0.22,
                                "width_normalised": 0.22,
                                "height_normalised": 0.18,
                                "scale": 0.3,
                                "opacity": 0.7,
                            },
                            {
                                "object_id": "bad_plant",
                                "asset_id": "rejected-plant",
                                "role": "background_reveal",
                                "start_time": 1.7,
                                "end_time": 3.7,
                                "x": 0.5,
                                "y": 0.5,
                                "z": 0.9,
                                "width_normalised": 0.6,
                                "height_normalised": 0.6,
                                "scale": 1.0,
                            },
                        ]
                    }
                ],
            }
        },
        visual_roles=[
            ("background", _role("counter", storage_uri="s3://assets/counter.png")),
            ("foreground", _role("steak", storage_uri="s3://assets/steak.png")),
            ("foreground_2", _role("plant", storage_uri="s3://assets/plant.png")),
            ("foreground_3", _role("pan", storage_uri="s3://assets/pan.png")),
            ("foreground_3", _role("rejected-plant", storage_uri="s3://assets/rejected.png")),
        ],
    )

    assert manifest.background_layer.asset_id == "counter"
    assert manifest.background_layer.motion_transform is not None
    assert manifest.background_layer.motion_transform.preset == "slow_zoom"
    layer_by_asset = {layer.asset_id: layer for layer in manifest.layers}
    assert set(layer_by_asset) == {"steak", "plant", "pan"}
    assert len({layer.z_index for layer in manifest.layers}) == len(manifest.layers)
    assert layer_by_asset["steak"].layer_id == "steak_hero_payoff-003"
    assert layer_by_asset["steak"].start_time == 0.0
    assert layer_by_asset["steak"].end_time == 6.5
    assert layer_by_asset["plant"].z_index < layer_by_asset["steak"].z_index
    assert layer_by_asset["plant"].x > layer_by_asset["steak"].x
    assert layer_by_asset["plant"].y < layer_by_asset["steak"].y
    assert layer_by_asset["plant"].width < layer_by_asset["steak"].width


def test_cinematic_canonical_timeline_can_retime_to_fractional_source_duration() -> None:
    retimed = _retime_canonical_timeline_payload(
        {
            "duration_seconds": 6.0,
            "cover_frame_timestamp_seconds": 0.5,
            "source_clips": [{"clip_id": "source-001", "duration_seconds": 6.0}],
            "scenes": [
                {
                    "scene_id": "scene-1",
                    "start_seconds": 0.0,
                    "end_seconds": 6.0,
                    "source_clip_id": "source-001",
                    "source_start_seconds": 0.0,
                    "source_end_seconds": 6.0,
                }
            ],
            "edit_segments": [
                {
                    "segment_id": "segment-1",
                    "timeline_start_seconds": 0.0,
                    "timeline_end_seconds": 6.0,
                    "source_clip_id": "source-001",
                    "source_start_seconds": 0.0,
                    "source_end_seconds": 6.0,
                }
            ],
            "overlays": [{"overlay_id": "ov-1", "start_seconds": 0.0, "end_seconds": 6.0}],
            "audio_tracks": [{"track_id": "audio-master", "start_seconds": 0.0, "end_seconds": 6.0}],
        },
        target_duration_seconds=6.5,
    )

    assert retimed["duration_seconds"] == 6.5
    assert retimed["source_clips"][0]["duration_seconds"] == 6.5
    assert retimed["scenes"][0]["end_seconds"] == 6.5
    assert retimed["edit_segments"][0]["timeline_end_seconds"] == 6.5
    assert retimed["overlays"][0]["end_seconds"] == 6.5
    assert retimed["audio_tracks"][0]["end_seconds"] == 6.5


def test_cinematic_composition_duration_overrides_stale_integer_provider_duration() -> None:
    source_duration = _cinematic_composition_duration_seconds(
        {
            "asset_source": "asset_pack_cinematic_plan",
            "duration_seconds": 6.5,
            "canonical_params": {"duration_seconds": 6.0},
        }
    )

    assert source_duration == 6.5
    assert _validate_duration_contract(
        requested_provider_duration_seconds=source_duration,
        source_clip_duration_seconds=6.5,
        scene_plan_duration_seconds=6.5,
        final_rendered_duration_seconds=6.5,
        tolerance_seconds=0.25,
    )["status"] == "pass"
