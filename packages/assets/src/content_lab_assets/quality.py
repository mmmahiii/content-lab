"""Quality scoring for physical asset placement decisions."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from content_lab_assets.compatibility import AssetCompatibilityMetadata, AssetResolutionClass

SHARP_FULL_FRAME_MIN_WIDTH = 1080
SHARP_FULL_FRAME_MIN_HEIGHT = 1600


class FullFrameQualityScore(BaseModel):
    """Explain whether an asset is safe as a full-frame reel base."""

    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0.0, le=1.0)
    can_use_full_frame: bool
    warnings: list[str] = Field(default_factory=list)


class EnvironmentBaseQualityResult(BaseModel):
    """Quality gate result for using an environment as a scene base."""

    model_config = ConfigDict(extra="forbid")

    can_use_sharp_full_frame: bool
    allowed_as_texture_backdrop: bool
    recommended_render_strategy: str
    realism_risk_delta: float = Field(ge=0.0, le=1.0)
    require_foreground_detail: bool
    render_notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def score_full_frame_quality(metadata: AssetCompatibilityMetadata) -> FullFrameQualityScore:
    """Score whether an asset can safely serve as a full-frame environment/base."""

    score = 0.9
    warnings: list[str] = []
    if not metadata.can_be_full_frame_base:
        score -= 0.35
        warnings.append("asset is not marked as a full-frame base")
    if metadata.asset_resolution_class is AssetResolutionClass.LOW:
        score -= 0.35
        warnings.append("low-resolution assets should not be treated as sharp full-frame environments")
    elif metadata.asset_resolution_class is AssetResolutionClass.MEDIUM:
        score -= 0.08
    if metadata.alpha_quality.value not in {"none", "unknown"}:
        score -= 0.15
        warnings.append("transparent assets are risky as full-frame bases")
    if metadata.view_angle.value == "unknown" or metadata.surface_plane.value == "unknown":
        score -= 0.12
        warnings.append("unknown physical metadata increases full-frame realism risk")
    score -= min(0.25, metadata.realism_risk_score * 0.2)
    score = round(max(0.0, min(1.0, score)), 4)
    return FullFrameQualityScore(
        score=score,
        can_use_full_frame=metadata.can_be_full_frame_base and score >= 0.55,
        warnings=warnings,
    )


def evaluate_environment_base_quality(
    *,
    width: int | None,
    height: int | None,
    can_be_full_frame_base: bool = True,
) -> EnvironmentBaseQualityResult:
    """Determine whether an environment asset can be used as a sharp 9:16 base."""

    meets_dimensions = (
        width is not None
        and height is not None
        and (width >= SHARP_FULL_FRAME_MIN_WIDTH or height >= SHARP_FULL_FRAME_MIN_HEIGHT)
    )
    if can_be_full_frame_base and meets_dimensions:
        return EnvironmentBaseQualityResult(
            can_use_sharp_full_frame=True,
            allowed_as_texture_backdrop=True,
            recommended_render_strategy="realistic_single_scene",
            realism_risk_delta=0.0,
            require_foreground_detail=False,
            render_notes=["Environment base is eligible for sharp full-frame use."],
        )

    dimension_text = (
        "unknown source dimensions" if width is None or height is None else f"{width}x{height}"
    )
    return EnvironmentBaseQualityResult(
        can_use_sharp_full_frame=False,
        allowed_as_texture_backdrop=True,
        recommended_render_strategy="low_res_texture_backdrop",
        realism_risk_delta=0.25,
        require_foreground_detail=True,
        render_notes=[
            f"Environment source is {dimension_text}; do not stretch as a sharp full-frame scene.",
            "Use blurred, padded, cropped, or texture-backdrop treatment.",
            "Foreground assets must carry the sharp visual detail.",
        ],
        warnings=["environment base is below sharp full-frame threshold"],
    )


__all__ = [
    "EnvironmentBaseQualityResult",
    "FullFrameQualityScore",
    "SHARP_FULL_FRAME_MIN_HEIGHT",
    "SHARP_FULL_FRAME_MIN_WIDTH",
    "evaluate_environment_base_quality",
    "score_full_frame_quality",
]
