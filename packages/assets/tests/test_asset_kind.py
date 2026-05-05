from __future__ import annotations

import uuid

from content_lab_assets.types import AssetKind, GenerateDecision, GenerationIntent, MediaType

REQUIRED_ASSET_KIND_VALUES = {
    "background_image",
    "background_video",
    "object_image",
    "object_video",
    "subject_image",
    "subject_video",
    "prop_image",
    "prop_video",
    "foreground_layer_image",
    "foreground_layer_video",
    "transparent_cutout_png",
    "masked_image",
    "effect_image",
    "effect_video",
    "transition_layer",
    "generated_clip",
    "source_clip",
    "final_render",
    "cover_image",
    "hook_text",
    "overlay_plan",
    "subtitle_plan",
    "caption_text",
    "design_template",
    "audio_track",
    "sound_effect",
    "voiceover",
    "trimmed_audio",
    "package_artifact",
    "provenance_artifact",
    "posting_plan_artifact",
}


def test_asset_kind_includes_required_component_taxonomy() -> None:
    assert {kind.value for kind in AssetKind} == REQUIRED_ASSET_KIND_VALUES


def test_asset_kind_groups_make_non_video_assets_first_class() -> None:
    assert AssetKind.TRANSPARENT_CUTOUT_PNG.value.endswith("_png")
    assert {
        AssetKind.BACKGROUND_IMAGE,
        AssetKind.BACKGROUND_VIDEO,
        AssetKind.HOOK_TEXT,
        AssetKind.AUDIO_TRACK,
        AssetKind.PACKAGE_ARTIFACT,
        AssetKind.FINAL_RENDER,
    } <= set(AssetKind)


def test_registry_payloads_carry_asset_kind() -> None:
    intent = GenerationIntent(
        asset_id=uuid.UUID("00000000-0000-4000-8000-000000000001"),
        asset_status="staged",
        storage_uri="s3://content-lab/assets/raw/asset-1/source.bin",
        idempotency_key="asset.generate:abc",
        asset_class="clip",
        provider="runway",
        model="gen4.5",
        asset_key="{}",
        asset_key_hash="abc",
    )
    decision = GenerateDecision(
        asset_class="clip",
        asset_key="{}",
        asset_key_hash="abc",
        provider="runway",
        model="gen4.5",
        generation_intent=intent,
    )

    assert intent.asset_kind is AssetKind.GENERATED_CLIP
    assert intent.media_type is MediaType.VIDEO
    assert decision.asset_kind is AssetKind.GENERATED_CLIP
    assert decision.media_type is MediaType.VIDEO
    assert decision.model_dump(mode="json")["asset_kind"] == "generated_clip"
    assert decision.model_dump(mode="json")["media_type"] == "video"
