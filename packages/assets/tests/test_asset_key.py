from __future__ import annotations

import hashlib
import uuid
from typing import Any

import pytest

from content_lab_assets.asset_key import (
    Phase1ProviderLockError,
    build_asset_key,
    build_audio_asset_key,
    build_derived_asset_key,
    build_final_render_asset_key,
    build_overlay_text_asset_key,
    validate_phase1_provider_model,
)
from content_lab_assets.canonicalise import (
    canonicalise_runway_gen45_generation,
    serialise_canonical_payload,
)


def _base_generation_request(*, reference_asset_ids: list[uuid.UUID]) -> dict[str, Any]:
    return {
        "asset_class": " Clip ",
        "provider": " Runway ",
        "model": " GEN4.5 ",
        "prompt": " Hero   launch   shot ",
        "negative_prompt": " no   text overlays ",
        "seed": 7,
        "duration_seconds": 6.0,
        "fps": 24,
        "ratio": " 9 x 16 ",
        "motion": {
            "presets": [" cinematic ", "", "punchy"],
            "camera": {
                "tilt": " slow up ",
                "strength": 1.0,
            },
            "ignored": "   ",
        },
        "init_image_hash": " ABC123 ",
        "reference_asset_ids": reference_asset_ids,
    }


def test_canonical_generation_inputs_hash_identically_when_equivalent() -> None:
    reference_one = uuid.uuid4()
    reference_two = uuid.uuid4()
    first_request = _base_generation_request(reference_asset_ids=[reference_two, reference_one])
    second_request = {
        **_base_generation_request(reference_asset_ids=[reference_one, reference_two]),
        "asset_class": "clip",
        "provider": "runway",
        "model": "gen4.5",
        "prompt": "Hero launch shot",
        "negative_prompt": "no text overlays",
        "duration_seconds": 6,
        "ratio": "9:16",
        "motion": {
            "camera": {
                "strength": 1,
                "tilt": "slow up",
            },
            "presets": ["cinematic", "punchy"],
        },
        "init_image_hash": "abc123",
    }

    first_key = build_asset_key(**first_request)
    second_key = build_asset_key(**second_request)

    expected_payload = {
        "asset_class": "clip",
        "asset_kind": "generated_clip",
        "media_type": "video",
        "asset_source": "generated",
        "provider": "runway",
        "model": "gen4.5",
        "prompt": "Hero launch shot",
        "negative_prompt": "no text overlays",
        "seed": 7,
        "duration_seconds": 6,
        "fps": 24,
        "ratio": "9:16",
        "motion": {
            "camera": {
                "strength": 1,
                "tilt": "slow up",
            },
            "presets": ["cinematic", "punchy"],
        },
        "init_image_hash": "abc123",
        "reference_asset_ids": sorted([str(reference_one), str(reference_two)]),
    }

    assert first_key.canonical_params == expected_payload
    assert second_key.canonical_params == expected_payload
    assert (
        first_key.asset_key == second_key.asset_key == serialise_canonical_payload(expected_payload)
    )
    assert first_key.asset_key_hash == second_key.asset_key_hash
    assert (
        first_key.asset_key_hash == hashlib.sha256(first_key.asset_key.encode("utf-8")).hexdigest()
    )


def test_blank_optional_fields_are_omitted_from_the_canonical_payload() -> None:
    canonical = canonicalise_runway_gen45_generation(
        asset_class="clip",
        provider="runway",
        model="gen4.5",
        prompt="Hero launch shot",
        negative_prompt="   ",
        ratio=" 9 : 16 ",
        motion={"camera": {"strength": 0.5}, "empty": {}},
        init_image_hash="   ",
        reference_asset_ids=[],
    )

    assert canonical == {
        "asset_class": "clip",
        "asset_kind": "generated_clip",
        "media_type": "video",
        "asset_source": "generated",
        "provider": "runway",
        "model": "gen4.5",
        "prompt": "Hero launch shot",
        "ratio": "9:16",
        "motion": {"camera": {"strength": 0.5}},
    }


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("prompt", "Different shot"),
        ("duration_seconds", 8),
        ("motion", {"camera": {"strength": 0.8, "tilt": "slow up"}, "presets": ["cinematic"]}),
    ],
)
def test_non_equivalent_payload_differences_change_the_asset_key_hash(
    field_name: str,
    replacement: Any,
) -> None:
    request = _base_generation_request(reference_asset_ids=[uuid.uuid4()])
    mutated_request = dict(request)
    mutated_request[field_name] = replacement

    baseline_key = build_asset_key(**request)
    changed_key = build_asset_key(**mutated_request)

    assert changed_key.asset_key_hash != baseline_key.asset_key_hash
    assert changed_key.asset_key != baseline_key.asset_key


def test_validate_phase1_provider_model_rejects_non_runway_gen45_requests() -> None:
    with pytest.raises(Phase1ProviderLockError):
        validate_phase1_provider_model(provider="pika", model="gen4.5")


# --- KEY-001 -----------------------------------------------------------------


def _shared_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "asset_class": "component",
        "provider": "runway",
        "model": "gen4.5",
        "prompt": "Luxury office skyline",
    }
    base.update(overrides)
    return base


def test_key001_different_asset_kinds_do_not_collide() -> None:
    kinds = [
        ("background_image", "image"),
        ("object_image", "image"),
        ("final_render", "video"),
        ("hook_text", "text"),
        ("background_video", "video"),
    ]
    hashes = {
        kind: build_asset_key(**_shared_kwargs(asset_kind=kind, media_type=media)).asset_key_hash
        for kind, media in kinds
    }
    assert len(set(hashes.values())) == len(hashes), hashes


def test_component_asset_key_regression_component_roles_do_not_collide() -> None:
    shared_text = {
        "canonical_text": "Luxury is a decision before it is a result.",
        "timing": {"start": 0, "end": 2.5},
        "layout": {"anchor": "top", "x": 0.5, "y": 0.12},
        "safe_area": {"top": 0.08, "bottom": 0.12, "left": 0.05, "right": 0.05},
        "template_version": "text-component-v1",
        "style": {"font": "Inter Bold", "size": 72},
    }
    hook_text = build_overlay_text_asset_key(asset_kind="hook_text", **shared_text)
    caption_text = build_overlay_text_asset_key(asset_kind="caption_text", **shared_text)

    shared_prompt = _shared_kwargs(
        asset_class="component",
        prompt="Luxury morning desk ritual, cinematic natural light",
        seed=11,
        ratio="9:16",
    )
    background_image = build_asset_key(
        **{**shared_prompt, "asset_kind": "background_image", "media_type": "image"}
    )
    object_image = build_asset_key(
        **{**shared_prompt, "asset_kind": "object_image", "media_type": "image"}
    )

    generated_clip = build_asset_key(
        **{
            **shared_prompt,
            "asset_kind": "generated_clip",
            "media_type": "video",
            "duration_seconds": 6,
            "fps": 24,
        }
    )
    final_render = build_final_render_asset_key(
        ordered_source_asset_ids_or_hashes=[uuid.uuid4(), "hookhash"],
        composition_manifest_hash="manifesthash",
        edit_template_version="edit-v1",
        export_preset={"container": "mp4", "codec": "h264"},
        render_parameters={"width": 1080, "height": 1920, "fps": 24},
    )

    source_asset_id = uuid.uuid4()
    cutout_recipe = {
        "operation": "remove_background",
        "model": "rembg-u2net",
        "alpha_mode": "alpha",
    }
    transparent_cutout_png = build_derived_asset_key(
        asset_kind="transparent_cutout_png",
        source_asset_id=source_asset_id,
        transform_recipe=cutout_recipe,
        transform_recipe_version="cutout-v1",
        output_parameters={"format": "png", "background": "transparent"},
    )
    source_image = build_derived_asset_key(
        asset_kind="object_image",
        source_asset_id=source_asset_id,
        transform_recipe=cutout_recipe,
        transform_recipe_version="cutout-v1",
        output_parameters={"format": "png", "background": "transparent"},
    )

    pairs = [
        (hook_text, caption_text),
        (background_image, object_image),
        (generated_clip, final_render),
        (transparent_cutout_png, source_image),
    ]
    for left, right in pairs:
        assert left.asset_key_hash != right.asset_key_hash
        assert left.asset_key != right.asset_key
        assert left.canonical_params["asset_kind"] != right.canonical_params["asset_kind"]


def test_key001_same_inputs_with_default_asset_kind_are_stable() -> None:
    first = build_asset_key(**_shared_kwargs(prompt="Hero launch shot"))
    second = build_asset_key(
        **_shared_kwargs(
            prompt="Hero launch shot",
            asset_kind="generated_clip",
            media_type="video",
            asset_source="generated",
        )
    )
    assert first.asset_key_hash == second.asset_key_hash
    assert first.canonical_params["asset_kind"] == "generated_clip"
    assert first.canonical_params["media_type"] == "video"
    assert first.canonical_params["asset_source"] == "generated"


def test_key001_canonical_payload_orders_keys_stably() -> None:
    key = build_asset_key(
        **_shared_kwargs(
            asset_kind="object_image",
            media_type="image",
            prompt="Espresso cup product shot",
        )
    )
    assert key.asset_key.startswith(
        '{"asset_class":"component","asset_kind":"object_image","asset_source":"generated",'
        '"media_type":"image",'
    )
    assert key.asset_key_hash == hashlib.sha256(key.asset_key.encode("utf-8")).hexdigest()


# --- KEY-002 -----------------------------------------------------------------


def test_key002_generated_clip_is_distinct_from_background_video_for_same_prompt() -> None:
    base = _shared_kwargs(
        prompt="City skyline at golden hour",
        seed=42,
        duration_seconds=6,
        fps=24,
        ratio="9:16",
    )
    generated_clip = build_asset_key(**base)
    background_video = build_asset_key(
        **{**base, "asset_kind": "background_video", "media_type": "video"}
    )
    assert generated_clip.asset_key_hash != background_video.asset_key_hash
    assert generated_clip.canonical_params["asset_kind"] == "generated_clip"
    assert background_video.canonical_params["asset_kind"] == "background_video"


def test_key002_object_image_payload_includes_motion_video_fields_only_when_supplied() -> None:
    object_image = build_asset_key(
        **_shared_kwargs(
            asset_kind="object_image",
            media_type="image",
            prompt="Frying pan, top down studio light",
            init_image_hash="abc123",
            reference_asset_ids=[uuid.uuid4()],
        )
    )
    assert object_image.canonical_params["asset_kind"] == "object_image"
    assert object_image.canonical_params["media_type"] == "image"
    assert "motion" not in object_image.canonical_params
    assert "duration_seconds" not in object_image.canonical_params
    assert "fps" not in object_image.canonical_params
    assert object_image.canonical_params["init_image_hash"] == "abc123"


def test_key002_background_video_payload_includes_motion_and_duration() -> None:
    background_video = build_asset_key(
        **_shared_kwargs(
            asset_kind="background_video",
            media_type="video",
            prompt="Slow pan over a desert highway",
            duration_seconds=6,
            fps=24,
            ratio="9:16",
            motion={"camera": {"pan": "slow left"}, "strength": 0.6},
        )
    )
    assert background_video.canonical_params["asset_kind"] == "background_video"
    assert background_video.canonical_params["media_type"] == "video"
    assert background_video.canonical_params["duration_seconds"] == 6
    assert background_video.canonical_params["fps"] == 24
    assert background_video.canonical_params["motion"] == {
        "camera": {"pan": "slow left"},
        "strength": 0.6,
    }


def test_key002_changing_seed_or_motion_changes_hash() -> None:
    base = _shared_kwargs(
        asset_kind="background_video",
        media_type="video",
        prompt="Slow pan over a desert highway",
        duration_seconds=6,
        fps=24,
        ratio="9:16",
        motion={"camera": {"pan": "slow left"}, "strength": 0.6},
    )
    baseline = build_asset_key(**base)
    different_seed = build_asset_key(**{**base, "seed": 99})
    different_motion = build_asset_key(
        **{**base, "motion": {"camera": {"pan": "slow right"}, "strength": 0.6}}
    )
    assert different_seed.asset_key_hash != baseline.asset_key_hash
    assert different_motion.asset_key_hash != baseline.asset_key_hash


def test_key002_rejects_incompatible_media_type_for_asset_kind() -> None:
    with pytest.raises(ValueError):
        build_asset_key(
            **_shared_kwargs(
                asset_kind="object_image",
                media_type="video",
                prompt="Espresso cup product shot",
            )
        )


# --- KEY-003 -----------------------------------------------------------------


def test_key003_transparent_cutout_derived_from_source_image_has_own_key() -> None:
    source_asset_id = uuid.uuid4()

    cutout = build_derived_asset_key(
        asset_kind="transparent_cutout_png",
        source_asset_id=source_asset_id,
        transform_recipe={
            "operation": "remove_background",
            "alpha_mode": "alpha",
            "model": "rembg-u2net",
            "threshold": 0.5,
        },
        transform_recipe_version="cutout-v1",
        output_parameters={
            "format": "png",
            "background": "transparent",
            "width": 1080.0,
            "height": 1920,
        },
    )
    source_image_derivative = build_derived_asset_key(
        asset_kind="object_image",
        source_asset_id=source_asset_id,
        transform_recipe={
            "operation": "remove_background",
            "alpha_mode": "alpha",
            "model": "rembg-u2net",
            "threshold": 0.5,
        },
        transform_recipe_version="cutout-v1",
        output_parameters={
            "format": "png",
            "background": "transparent",
            "width": 1080,
            "height": 1920,
        },
    )

    assert cutout.canonical_params == {
        "asset_kind": "transparent_cutout_png",
        "media_type": "image",
        "asset_source": "derived",
        "source_asset_id": str(source_asset_id),
        "transform_recipe": {
            "alpha_mode": "alpha",
            "model": "rembg-u2net",
            "operation": "remove_background",
            "threshold": 0.5,
        },
        "transform_recipe_version": "cutout-v1",
        "output_parameters": {
            "background": "transparent",
            "format": "png",
            "height": 1920,
            "width": 1080,
        },
    }
    assert cutout.asset_key_hash != source_image_derivative.asset_key_hash


def test_key003_resized_or_reframed_asset_recipe_and_output_change_hash() -> None:
    source_hash = "ABCDEF123456"
    baseline = build_derived_asset_key(
        asset_kind="background_video",
        source_content_hash=source_hash,
        transform_recipe={
            "operation": "reframe",
            "crop": {"x": 0.1, "y": 0, "width": 0.8, "height": 1.0},
            "scale": "cover",
        },
        transform_recipe_version="reframe-v2",
        output_parameters={"width": 1080, "height": 1920, "fps": 30.0},
    )
    equivalent = build_derived_asset_key(
        asset_kind="background_video",
        source_content_hash=" abcdef123456 ",
        transform_recipe={
            "scale": "cover",
            "crop": {"height": 1, "width": 0.8, "y": 0, "x": 0.1},
            "operation": "reframe",
        },
        transform_recipe_version="reframe-v2",
        output_parameters={"fps": 30, "height": 1920, "width": 1080.0},
    )
    resized = build_derived_asset_key(
        asset_kind="background_video",
        source_content_hash=source_hash,
        transform_recipe={
            "operation": "reframe",
            "crop": {"x": 0.1, "y": 0, "width": 0.8, "height": 1.0},
            "scale": "cover",
        },
        transform_recipe_version="reframe-v2",
        output_parameters={"width": 720, "height": 1280, "fps": 30},
    )

    assert baseline.asset_key_hash == equivalent.asset_key_hash
    assert baseline.canonical_params["source_content_hash"] == "abcdef123456"
    assert baseline.asset_key_hash != resized.asset_key_hash


def test_key003_requires_source_identity_for_derived_assets() -> None:
    with pytest.raises(ValueError, match="source_asset_id or source_content_hash"):
        build_derived_asset_key(
            asset_kind="effect_image",
            transform_recipe={"operation": "colour_grade", "lut": "warm"},
            transform_recipe_version="grade-v1",
            output_parameters={"format": "png"},
        )


# --- KEY-004 -----------------------------------------------------------------


def test_key004_hook_text_assets_are_reusable_and_deterministic() -> None:
    base: dict[str, Any] = {
        "asset_kind": "hook_text",
        "canonical_text": " Stop scrolling for this ",
        "timing": {"start": 0.0, "end": 2},
        "layout": {"anchor": "top", "x": 0.5, "y": 0.12},
        "safe_area": {"top": 0.08, "bottom": 0.12, "left": 0.05, "right": 0.05},
        "template_version": "hook-template-v1",
        "style": {"font": "Inter Bold", "size": 72.0, "case": "sentence"},
    }
    first = build_overlay_text_asset_key(**base)
    second = build_overlay_text_asset_key(
        **{
            **base,
            "canonical_text": "Stop scrolling for this",
            "timing": {"end": 2.0, "start": 0},
            "style": {"case": "sentence", "size": 72, "font": "Inter Bold"},
        }
    )
    caption = build_overlay_text_asset_key(**{**base, "asset_kind": "caption_text"})

    assert first.asset_key_hash == second.asset_key_hash
    assert first.asset_key_hash != caption.asset_key_hash
    assert first.canonical_params["canonical_text"] == "Stop scrolling for this"
    assert first.canonical_params["media_type"] == "text"


def test_key004_audio_assets_are_reusable_and_deterministic() -> None:
    base: dict[str, Any] = {
        "asset_kind": "trimmed_audio",
        "audio_identity": {"provider": "internal", "content_hash": "AUDIOHASH123"},
        "trim_range": {"start": 1.0, "end": 8.0},
        "volume": {"gain_db": -3.0},
        "normalisation": {"target_lufs": -14.0, "true_peak_db": -1},
        "looping": {"enabled": False},
    }
    first = build_audio_asset_key(**base)
    second = build_audio_asset_key(
        **{
            **base,
            "trim_range": {"end": 8, "start": 1},
            "volume": {"gain_db": -3},
            "normalisation": {"true_peak_db": -1.0, "target_lufs": -14},
        }
    )
    louder = build_audio_asset_key(**{**base, "volume": {"gain_db": 0}})

    assert first.asset_key_hash == second.asset_key_hash
    assert first.asset_key_hash != louder.asset_key_hash
    assert first.canonical_params["asset_kind"] == "trimmed_audio"
    assert first.canonical_params["media_type"] == "audio"


def test_key004_final_renders_are_deterministic_derived_outputs() -> None:
    background_id = uuid.uuid4()
    hook_hash = "HOOKHASH"
    audio_hash = "AUDIOHASH"
    baseline = build_final_render_asset_key(
        ordered_source_asset_ids_or_hashes=[background_id, hook_hash, audio_hash],
        composition_manifest_hash="ABCDEF",
        edit_template_version="edit-v3",
        export_preset={"container": "mp4", "codec": "h264", "profile": "reels-1080x1920"},
        render_parameters={"width": 1080.0, "height": 1920, "fps": 30.0, "crf": 18},
    )
    equivalent = build_final_render_asset_key(
        ordered_source_asset_ids_or_hashes=[str(background_id).upper(), " hookhash ", "audiohash"],
        composition_manifest_hash=" abcdef ",
        edit_template_version="edit-v3",
        export_preset={"profile": "reels-1080x1920", "codec": "h264", "container": "mp4"},
        render_parameters={"crf": 18.0, "fps": 30, "height": 1920.0, "width": 1080},
    )
    reordered_sources = build_final_render_asset_key(
        ordered_source_asset_ids_or_hashes=[audio_hash, hook_hash, background_id],
        composition_manifest_hash="ABCDEF",
        edit_template_version="edit-v3",
        export_preset={"container": "mp4", "codec": "h264", "profile": "reels-1080x1920"},
        render_parameters={"width": 1080, "height": 1920, "fps": 30, "crf": 18},
    )

    assert baseline.asset_key_hash == equivalent.asset_key_hash
    assert baseline.asset_key_hash != reordered_sources.asset_key_hash
    assert baseline.canonical_params["asset_kind"] == "final_render"
    assert baseline.canonical_params["asset_source"] == "package_output"
    assert baseline.canonical_params["composition_manifest_hash"] == "abcdef"
