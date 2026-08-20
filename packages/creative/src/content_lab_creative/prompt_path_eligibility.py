"""Prompt-path eligibility from selected asset capabilities (motion/sensory/process)."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from content_lab_creative.prompt_paths import PROMPT_PATHS


def _norm(text: str) -> str:
    return "_".join(str(text).strip().lower().replace("-", "_").split())


def _tags(asset: Mapping[str, Any]) -> list[str]:
    raw = asset.get("tags") or []
    if not isinstance(raw, list):
        return []
    return [_norm(str(tag)) for tag in raw if str(tag).strip()]


def _compat(asset: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = asset.get("compatibility")
    return raw if isinstance(raw, Mapping) else {}


def _bool_override(compat: Mapping[str, Any], key: str) -> bool | None:
    if key not in compat:
        return None
    value = compat[key]
    if isinstance(value, bool):
        return value
    return None


class AssetPromptPathCapabilityFlags(BaseModel):
    """Per-asset planner-facing capability flags."""

    model_config = ConfigDict(extra="forbid")

    supports_real_motion: bool = False
    supports_sensory_visual: bool = False
    supports_audio_sensory: bool = False
    supports_process_sequence: bool = False
    supports_transformation: bool = False
    supports_before_after: bool = False
    is_static_image_only: bool = False
    is_video: bool = False
    is_audio: bool = False
    is_atmospheric_overlay: bool = False
    allow_sensory_placeholder_without_motion_evidence: bool = False
    supports_renderer_step_animation: bool = False


class AggregatedPromptPathCapabilities(BaseModel):
    """Roll-up across selected assets for gating stackable prompt paths."""

    model_config = ConfigDict(extra="forbid")

    asset_capabilities: list[AssetPromptPathCapabilityFlags] = Field(default_factory=list)
    static_png_only_pack: bool = False
    sensory_hook_evidence: bool = False
    satisfying_process_evidence: bool = False
    speed_ramp_evidence: bool = False
    physical_motion_claim_evidence: bool = False


class PromptPathEligibilityGate(BaseModel):
    """Decides which creative prompt paths are allowed for the current asset bank."""

    model_config = ConfigDict(extra="forbid")

    aggregate: AggregatedPromptPathCapabilities

    @classmethod
    def from_selected_assets(cls, assets: Sequence[Mapping[str, Any]]) -> PromptPathEligibilityGate:
        return cls(aggregate=aggregate_prompt_path_capabilities(list(assets)))

    def is_allowed(self, path: str) -> bool:
        normalized = _norm(path)
        if normalized == "sensory_hook":
            return self.aggregate.sensory_hook_evidence
        if normalized == "satisfying_process":
            return self.aggregate.satisfying_process_evidence
        if normalized == "speed_ramp_showcase":
            return self.aggregate.speed_ramp_evidence
        return True

    def allowed_prompt_paths_ordered(self) -> list[str]:
        return [p for p in PROMPT_PATHS if self.is_allowed(p)]

    def blocking_reason(self, path: str) -> str | None:
        normalized = _norm(path)
        if self.is_allowed(normalized):
            return None
        if normalized == "sensory_hook":
            return (
                "sensory_hook requires video, audio, an atmospheric overlay asset, motion-capable "
                "visuals, explicit sensory-visual capability metadata, or an allowed sensory placeholder "
                "override on an asset."
            )
        if normalized == "satisfying_process":
            return (
                "satisfying_process requires multiple process-step assets, video, transformation-capable "
                "assets (metadata), or renderer step-animation support flagged on assets."
            )
        if normalized == "speed_ramp_showcase":
            return "speed_ramp_showcase requires video or motion-capable visuals."
        return f"path '{path}' is blocked by prompt-path eligibility rules"


_PROCESS_SEQUENCE_HINT = re.compile(
    r"\b(step|steps|sequence|process|prep|instruction|timeline)\b",
    re.IGNORECASE,
)


def infer_asset_prompt_path_capabilities(asset: Mapping[str, Any]) -> AssetPromptPathCapabilityFlags:
    """Derive conservative defaults plus explicit compatibility_* overrides."""

    kind = _norm(str(asset.get("asset_kind") or ""))
    media = _norm(str(asset.get("media_type") or ""))
    roles_raw = asset.get("possible_cinematic_roles") or []
    roles = {_norm(str(role)) for role in roles_raw if str(role).strip()}
    compat = _compat(asset)
    tags_blob = " ".join(_tags(asset))
    pack_role = _norm(str(asset.get("pack_role") or ""))
    raw_label = str(asset.get("asset_label") or "").lower().replace("-", " ")
    raw_pack_role = str(asset.get("pack_role") or "").lower().replace("-", " ")
    hint_blob = " ".join([kind, media, tags_blob, pack_role, raw_pack_role, raw_label]).lower()

    is_video = (
        media == "video"
        or kind.endswith("_video")
        or kind in {"generated_clip", "source_clip", "final_render"}
    )
    is_audio = media == "audio" or kind in {
        "sound_effect",
        "voiceover",
        "audio_track",
        "trimmed_audio",
    }
    is_atmospheric_overlay = "atmospheric_layer" in roles or (
        "atmospheric" in hint_blob and ("effect" in kind or "foreground_layer" in kind)
    )

    inferred_motion = bool(is_video)
    supports_real_motion = _bool_override(compat, "supports_real_motion")
    if supports_real_motion is None:
        supports_real_motion = inferred_motion

    supports_audio_sensory = _bool_override(compat, "supports_audio_sensory")
    if supports_audio_sensory is None:
        supports_audio_sensory = bool(is_audio)

    supports_sensory_visual = _bool_override(compat, "supports_sensory_visual")
    if supports_sensory_visual is None:
        supports_sensory_visual = False

    seq_hint = bool(_PROCESS_SEQUENCE_HINT.search(hint_blob) or _PROCESS_SEQUENCE_HINT.search(raw_pack_role))
    supports_process_sequence = _bool_override(compat, "supports_process_sequence")
    if supports_process_sequence is None:
        supports_process_sequence = seq_hint

    supports_transformation = _bool_override(compat, "supports_transformation")
    if supports_transformation is None:
        supports_transformation = False

    supports_before_after = _bool_override(compat, "supports_before_after")
    if supports_before_after is None:
        supports_before_after = False

    supports_renderer_step_animation = _bool_override(compat, "supports_renderer_step_animation")
    if supports_renderer_step_animation is None:
        supports_renderer_step_animation = False

    placeholder = _bool_override(compat, "allow_sensory_placeholder_without_motion_evidence")
    if placeholder is None:
        placeholder = False
    allow_sensory_placeholder_without_motion_evidence = placeholder

    is_static_image_only = False
    if not is_video and not is_audio:
        image_like = media == "image" or media == "" or kind.endswith("_image")
        non_overlay_subject = "atmospheric_layer" not in roles and "motion_layer" not in roles
        if image_like and non_overlay_subject:
            is_static_image_only = True

    return AssetPromptPathCapabilityFlags(
        supports_real_motion=supports_real_motion,
        supports_sensory_visual=supports_sensory_visual,
        supports_audio_sensory=supports_audio_sensory,
        supports_process_sequence=supports_process_sequence,
        supports_transformation=supports_transformation,
        supports_before_after=supports_before_after,
        is_static_image_only=is_static_image_only,
        is_video=is_video,
        is_audio=is_audio,
        is_atmospheric_overlay=is_atmospheric_overlay,
        allow_sensory_placeholder_without_motion_evidence=allow_sensory_placeholder_without_motion_evidence,
        supports_renderer_step_animation=supports_renderer_step_animation,
    )


def aggregate_prompt_path_capabilities(
    assets: Sequence[Mapping[str, Any]],
) -> AggregatedPromptPathCapabilities:
    caps = [infer_asset_prompt_path_capabilities(asset) for asset in assets]

    any_video = any(c.is_video for c in caps)
    any_audio = any(c.is_audio for c in caps)
    any_atmospheric = any(c.is_atmospheric_overlay for c in caps)
    any_motion = any(c.supports_real_motion for c in caps)
    any_sensory_visual = any(c.supports_sensory_visual for c in caps)
    placeholder_any = any(c.allow_sensory_placeholder_without_motion_evidence for c in caps)

    sensory_hook_evidence = bool(
        any_video
        or any_audio
        or any_atmospheric
        or any_motion
        or any_sensory_visual
        or placeholder_any
    )

    process_sequence_assets = sum(1 for c in caps if c.supports_process_sequence)
    satisfying_process_evidence = bool(
        any_video
        or any(c.supports_transformation for c in caps)
        or any(c.supports_renderer_step_animation for c in caps)
        or process_sequence_assets >= 2
    )

    speed_ramp_evidence = bool(any_video or any_motion)

    physical_motion_claim_evidence = bool(
        any_video
        or any(c.supports_renderer_step_animation for c in caps)
        or any(c.supports_real_motion for c in caps)
    )

    static_png_only_pack = bool(
        len(caps) > 0
        and not any_video
        and not any_audio
        and all(c.is_static_image_only for c in caps)
    )

    return AggregatedPromptPathCapabilities(
        asset_capabilities=caps,
        static_png_only_pack=static_png_only_pack,
        sensory_hook_evidence=sensory_hook_evidence,
        satisfying_process_evidence=satisfying_process_evidence,
        speed_ramp_evidence=speed_ramp_evidence,
        physical_motion_claim_evidence=physical_motion_claim_evidence,
    )


def selected_assets_capability_summary(
    assets: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Public summary for prompts and APIs (includes per-asset capability dicts)."""

    agg = aggregate_prompt_path_capabilities(assets)
    gate = PromptPathEligibilityGate(aggregate=agg)
    blocked = [p for p in PROMPT_PATHS if not gate.is_allowed(p)]
    return {
        "aggregate": agg.model_dump(mode="json"),
        "allowed_prompt_paths": gate.allowed_prompt_paths_ordered(),
        "blocked_prompt_paths": blocked,
        "blocked_reasons": {path: gate.blocking_reason(path) for path in blocked if gate.blocking_reason(path)},
    }


def validate_prompt_paths_allowed_for_assets(
    paths: Sequence[str],
    *,
    assets: Sequence[Mapping[str, Any]],
) -> None:
    gate = PromptPathEligibilityGate.from_selected_assets(assets)
    invalid: list[str] = []
    for raw in paths:
        normalized = _norm(str(raw))
        if normalized and not gate.is_allowed(normalized):
            invalid.append(normalized)
    if invalid:
        reasons = "; ".join(f"{p}: {gate.blocking_reason(p)}" for p in sorted(set(invalid)))
        raise ValueError(f"prompt paths are not eligible for selected assets: {reasons}")


__all__ = [
    "AggregatedPromptPathCapabilities",
    "AssetPromptPathCapabilityFlags",
    "PromptPathEligibilityGate",
    "aggregate_prompt_path_capabilities",
    "infer_asset_prompt_path_capabilities",
    "selected_assets_capability_summary",
    "validate_prompt_paths_allowed_for_assets",
]
