"""Static vs true-motion suitability for planned assets (CAR-5A-005)."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from content_lab_assets.types import AssetKind, MediaType


class MotionSuitabilityAssessment(BaseModel):
    """Explainable motion vs static suitability for one planned asset."""

    model_config = ConfigDict(extra="forbid")

    requires_true_motion: bool = Field(
        description="True when the creative intent needs real motion, not a still."
    )
    static_asset_allowed: bool = Field(
        description="Whether a high-quality still / PNG could satisfy the need."
    )
    static_with_motion_transform_allowed: bool = Field(
        description="Whether a still plus deterministic transforms (pan/ken burns) may suffice."
    )
    preferred_media_type: str = Field(description="image | video | text | audio | unknown")
    motion_reason: str = Field(min_length=1, max_length=2000)


# Heuristic tokens: prompts mentioning these lean toward true motion / video.
_MOTION_HINTS = re.compile(
    r"\b("
    r"walk|walking|run|running|pour|pouring|stir|stirring|drive|driving|liquid|steam|"
    r"gym|lift|lifting|jump|jumping|swim|dancing|pour|splash|facial expression|interaction|"
    r"complex camera|handheld|tracking shot|pov motion"
    r")\b",
    re.I,
)

# Creative contexts where still props / backgrounds are usually enough.
_STATIC_FRIENDLY_KINDS = frozenset(
    {
        AssetKind.PROP_IMAGE,
        AssetKind.OBJECT_IMAGE,
        AssetKind.BACKGROUND_IMAGE,
        AssetKind.TRANSPARENT_CUTOUT_PNG,
        AssetKind.EFFECT_IMAGE,
        AssetKind.HOOK_TEXT,
        AssetKind.COVER_IMAGE,
        AssetKind.MASKED_IMAGE,
        AssetKind.FOREGROUND_LAYER_IMAGE,
    }
)

_VIDEO_KINDS = frozenset(
    {
        AssetKind.BACKGROUND_VIDEO,
        AssetKind.SUBJECT_VIDEO,
        AssetKind.OBJECT_VIDEO,
        AssetKind.EFFECT_VIDEO,
        AssetKind.GENERATED_CLIP,
        AssetKind.SOURCE_CLIP,
        AssetKind.TRANSITION_LAYER,
        AssetKind.FOREGROUND_LAYER_VIDEO,
    }
)


def evaluate_motion_suitability(
    *,
    asset_kind: AssetKind | str,
    media_type: MediaType | str,
    purpose: str,
    prompt_or_description: str,
) -> MotionSuitabilityAssessment:
    """Rule-based static vs motion recommendation (deterministic, explainable)."""

    kind = AssetKind(asset_kind) if not isinstance(asset_kind, AssetKind) else asset_kind
    mt = MediaType(media_type) if not isinstance(media_type, MediaType) else media_type
    text_blob = f"{purpose} {prompt_or_description}".strip()
    motion_hit = bool(_MOTION_HINTS.search(text_blob))

    if kind in _VIDEO_KINDS or mt is MediaType.VIDEO:
        return MotionSuitabilityAssessment(
            requires_true_motion=True,
            static_asset_allowed=False,
            static_with_motion_transform_allowed=False,
            preferred_media_type="video",
            motion_reason="Asset role or media type is video; motion is intrinsic to the output.",
        )

    if motion_hit:
        return MotionSuitabilityAssessment(
            requires_true_motion=True,
            static_asset_allowed=False,
            static_with_motion_transform_allowed=True,
            preferred_media_type="video",
            motion_reason=(
                "Planned description implies physical motion or dynamic realism "
                "(matched motion-related language); prefer video or generation over a still."
            ),
        )

    if kind in _STATIC_FRIENDLY_KINDS and mt is MediaType.IMAGE:
        return MotionSuitabilityAssessment(
            requires_true_motion=False,
            static_asset_allowed=True,
            static_with_motion_transform_allowed=True,
            preferred_media_type="image",
            motion_reason=(
                "Role fits compositable stills (props, cut-outs, backgrounds) without "
                "requiring real-world motion in capture."
            ),
        )

    return MotionSuitabilityAssessment(
        requires_true_motion=False,
        static_asset_allowed=True,
        static_with_motion_transform_allowed=True,
        preferred_media_type=mt.value if mt is not MediaType.UNKNOWN else "unknown",
        motion_reason=(
            "No strong motion requirement detected; still acceptable if quality is sufficient."
        ),
    )


__all__ = ["MotionSuitabilityAssessment", "evaluate_motion_suitability"]
