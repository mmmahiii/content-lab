"""Physical compatibility metadata and scoring for procedural reel planning."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ViewAngle(StrEnum):
    TOP_DOWN = "top_down"
    FRONT = "front"
    SIDE = "side"
    THREE_QUARTER = "three_quarter"
    OVERHEAD = "overhead"
    UNKNOWN = "unknown"


class SurfacePlane(StrEnum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    ANGLED = "angled"
    FLOATING = "floating"
    UNKNOWN = "unknown"


class LightingDirection(StrEnum):
    UPPER_LEFT = "upper_left"
    UPPER_RIGHT = "upper_right"
    OVERHEAD = "overhead"
    FRONT = "front"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class LightingQuality(StrEnum):
    SOFT = "soft"
    HARD = "hard"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class AssetResolutionClass(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AlphaQuality(StrEnum):
    CLEAN = "clean"
    ROUGH = "rough"
    NONE = "none"
    UNKNOWN = "unknown"


CompatibilityDimension = Literal[
    "niche",
    "topic",
    "theme",
    "emotion",
    "visual_style",
    "pace",
    "format_type",
]


class AssetCompatibilityMetadata(BaseModel):
    """What an asset works with semantically and physically in a composite scene."""

    model_config = ConfigDict(extra="forbid")

    # Existing semantic combinator fields.
    niche: list[str] = Field(default_factory=list)
    topic: list[str] = Field(default_factory=list)
    theme: list[str] = Field(default_factory=list)
    emotion: list[str] = Field(default_factory=list)
    visual_style: list[str] = Field(default_factory=list)
    pace: list[str] = Field(default_factory=list)
    format_type: list[str] = Field(default_factory=list)
    works_as_background_for: list[str] = Field(default_factory=list)
    works_with_object_types: list[str] = Field(default_factory=list)
    works_with_audio_moods: list[str] = Field(default_factory=list)
    works_with_hook_types: list[str] = Field(default_factory=list)
    requires_transparency: bool = False
    requires_safe_area: bool = False

    # Physical scene compatibility fields.
    view_angle: ViewAngle = ViewAngle.UNKNOWN
    surface_plane: SurfacePlane = SurfacePlane.UNKNOWN
    lighting_direction: LightingDirection = LightingDirection.UNKNOWN
    lighting_quality: LightingQuality = LightingQuality.UNKNOWN
    asset_resolution_class: AssetResolutionClass = AssetResolutionClass.MEDIUM
    can_be_full_frame_base: bool = False
    can_support_objects: bool = False
    can_be_supported_by_surface: bool = False
    natural_support_roles: list[str] = Field(default_factory=list)
    alpha_quality: AlphaQuality = AlphaQuality.UNKNOWN
    realism_risk_score: float = Field(default=0.35, ge=0.0, le=1.0)
    recommended_max_scale: float = Field(default=1.0, gt=0.0)
    recommended_min_scale: float = Field(default=0.05, ge=0.0)
    preferred_screen_regions: list[str] = Field(default_factory=list)
    forbidden_screen_regions: list[str] = Field(default_factory=list)
    compatible_view_angles: list[str] = Field(default_factory=list)
    compatible_surface_planes: list[str] = Field(default_factory=list)

    # Prompt-path eligibility overrides (None = infer from asset_kind/media/roles).
    supports_real_motion: bool | None = None
    supports_sensory_visual: bool | None = None
    supports_audio_sensory: bool | None = None
    supports_process_sequence: bool | None = None
    supports_transformation: bool | None = None
    supports_before_after: bool | None = None
    allow_sensory_placeholder_without_motion_evidence: bool | None = None
    supports_renderer_step_animation: bool | None = None

    @field_validator(
        "niche",
        "topic",
        "theme",
        "emotion",
        "visual_style",
        "pace",
        "format_type",
        "works_as_background_for",
        "works_with_object_types",
        "works_with_audio_moods",
        "works_with_hook_types",
        "natural_support_roles",
        "preferred_screen_regions",
        "forbidden_screen_regions",
        "compatible_view_angles",
        "compatible_surface_planes",
        mode="before",
    )
    @classmethod
    def _normalize_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        values: Iterable[Any] = [value] if isinstance(value, str) else value
        normalized: list[str] = []
        for item in values:
            text = _normalize_token(item)
            if text is not None and text not in normalized:
                normalized.append(text)
        return normalized

    @model_validator(mode="after")
    def _validate_scale_bounds(self) -> AssetCompatibilityMetadata:
        if self.recommended_min_scale > self.recommended_max_scale:
            raise ValueError("recommended_min_scale cannot exceed recommended_max_scale")
        return self

    @classmethod
    def from_metadata(cls, metadata: Mapping[str, Any] | None) -> AssetCompatibilityMetadata:
        """Hydrate compatibility from common pack metadata shapes."""

        if not metadata:
            return cls()
        candidate = metadata.get("compatibility")
        if isinstance(candidate, Mapping):
            return cls.model_validate(dict(candidate))
        candidate = metadata.get("compatibility_metadata")
        if isinstance(candidate, Mapping):
            return cls.model_validate(dict(candidate))
        candidate = metadata.get("compatible_with")
        if isinstance(candidate, Mapping):
            mapped = dict(candidate)
            if "reel_formats" in mapped and "format_type" not in mapped:
                mapped["format_type"] = mapped.pop("reel_formats")
            return cls.model_validate(mapped)
        return cls.model_validate(
            {key: value for key, value in metadata.items() if key in cls.model_fields}
        )

    def matches_filters(
        self,
        *,
        format_filters: Sequence[str] | None = None,
        style_filters: Sequence[str] | None = None,
    ) -> bool:
        formats = _token_set(format_filters or [])
        styles = _token_set(style_filters or [])
        if formats and self.format_type and not formats.intersection(self.format_type):
            return False
        if styles and self.visual_style and not styles.intersection(self.visual_style):
            return False
        return True


class AssetPairCompatibilityScore(BaseModel):
    """Explainable physical compatibility score for two planner assets."""

    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0.0, le=1.0)
    verdict: Literal["pass", "warn", "fail"]
    warnings: list[str] = Field(default_factory=list)


def compatibility_score(
    base: AssetCompatibilityMetadata,
    overlay: AssetCompatibilityMetadata,
) -> AssetPairCompatibilityScore:
    """Score whether two assets can plausibly share a physical scene."""

    score = 1.0
    warnings: list[str] = []

    unknowns = _unknown_count(base) + _unknown_count(overlay)
    if unknowns:
        score -= min(0.25, unknowns * 0.035)
        warnings.append("unknown metadata increases realism risk")

    if overlay.can_be_supported_by_surface:
        if base.can_support_objects:
            score += 0.05
        elif overlay.surface_plane is not SurfacePlane.FLOATING:
            score -= 0.35
            warnings.append("asset needs a support surface but base cannot support objects")

    if base.surface_plane is SurfacePlane.HORIZONTAL and overlay.can_be_supported_by_surface:
        score += 0.08

    if base.compatible_view_angles and overlay.view_angle.value not in base.compatible_view_angles:
        score -= 0.25
        warnings.append("overlay view angle is outside base compatible view angles")
    elif overlay.compatible_view_angles and base.view_angle.value not in overlay.compatible_view_angles:
        score -= 0.25
        warnings.append("base view angle is outside overlay compatible view angles")
    elif _view_angles_mismatch(base.view_angle, overlay.view_angle):
        score -= 0.22
        warnings.append("view angles are likely mismatched")

    if base.compatible_surface_planes and overlay.surface_plane.value not in base.compatible_surface_planes:
        score -= 0.2
        warnings.append("overlay surface plane is outside base compatible planes")
    elif overlay.compatible_surface_planes and base.surface_plane.value not in overlay.compatible_surface_planes:
        score -= 0.2
        warnings.append("base surface plane is outside overlay compatible planes")

    if (
        base.lighting_direction is not LightingDirection.UNKNOWN
        and overlay.lighting_direction is not LightingDirection.UNKNOWN
        and base.lighting_direction is not overlay.lighting_direction
        and LightingDirection.MIXED not in {base.lighting_direction, overlay.lighting_direction}
    ):
        score -= 0.12
        warnings.append("lighting directions differ")

    if overlay.alpha_quality is AlphaQuality.ROUGH:
        score -= 0.12
        warnings.append("rough alpha may expose cutout edges")

    score -= min(0.25, (base.realism_risk_score + overlay.realism_risk_score) * 0.12)
    score = round(max(0.0, min(1.0, score)), 4)
    verdict: Literal["pass", "warn", "fail"] = (
        "fail" if score < 0.45 else "warn" if warnings or score < 0.72 else "pass"
    )
    return AssetPairCompatibilityScore(score=score, verdict=verdict, warnings=_dedupe(warnings))


def _view_angles_mismatch(left: ViewAngle, right: ViewAngle) -> bool:
    if ViewAngle.UNKNOWN in {left, right}:
        return False
    compatible = {
        ViewAngle.TOP_DOWN: {ViewAngle.TOP_DOWN, ViewAngle.OVERHEAD},
        ViewAngle.OVERHEAD: {ViewAngle.TOP_DOWN, ViewAngle.OVERHEAD, ViewAngle.THREE_QUARTER},
        ViewAngle.FRONT: {ViewAngle.FRONT, ViewAngle.THREE_QUARTER},
        ViewAngle.SIDE: {ViewAngle.SIDE, ViewAngle.THREE_QUARTER},
        ViewAngle.THREE_QUARTER: {
            ViewAngle.THREE_QUARTER,
            ViewAngle.FRONT,
            ViewAngle.SIDE,
            ViewAngle.OVERHEAD,
        },
    }
    return right not in compatible.get(left, {left})


def _unknown_count(metadata: AssetCompatibilityMetadata) -> int:
    values = (
        metadata.view_angle,
        metadata.surface_plane,
        metadata.lighting_direction,
        metadata.lighting_quality,
        metadata.alpha_quality,
    )
    return sum(1 for value in values if value.value == "unknown")


def _token_set(values: Sequence[str]) -> set[str]:
    return {token for value in values if (token := _normalize_token(value)) is not None}


def _normalize_token(value: Any) -> str | None:
    normalized = "_".join(str(value).strip().lower().replace("-", "_").split())
    return normalized or None


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


__all__ = [
    "AlphaQuality",
    "AssetCompatibilityMetadata",
    "AssetPairCompatibilityScore",
    "AssetResolutionClass",
    "CompatibilityDimension",
    "LightingDirection",
    "LightingQuality",
    "SurfacePlane",
    "ViewAngle",
    "compatibility_score",
]
