"""Strict contracts for single-prompt cinematic reel plans."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from content_lab_creative.prompt_paths import PROMPT_PATHS, normalize_prompt_paths

CINEMATIC_ROLES: tuple[str, ...] = (
    "hero_subject",
    "supporting_subject",
    "environment_base",
    "background_reveal",
    "foreground_texture",
    "atmospheric_layer",
    "motion_layer",
    "audio_layer",
    "caption_support",
    "transition_element",
    "brand_marker",
    "narrative_payoff",
)

CAMERA_MOVES: tuple[str, ...] = (
    "static_lockoff",
    "handheld_micro_motion",
    "slow_push_in",
    "slow_pull_out",
    "slight_pan_left",
    "slight_pan_right",
    "parallax_push",
    "snap_reframe",
    "speed_ramp_focus",
)

AUDIO_ROLES: tuple[str, ...] = (
    "sensory_sizzle",
    "ambient_room",
    "soft_whoosh",
    "transition_hit",
    "subtle_riser",
    "impact",
    "silence_gap",
    "voiceover_placeholder",
)

FORBIDDEN_GENERATION_TERMS: tuple[str, ...] = (
    "generate image",
    "generate video",
    "create image",
    "create video",
    "call runway",
    "call midjourney",
    "call dalle",
    "external video api",
    "external image api",
    "screenshot",
    "copy existing reel",
)


class CanvasSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aspect_ratio: Literal["9:16"] = "9:16"
    width: int = Field(default=1080, gt=0)
    height: int = Field(default=1920, gt=0)


class MotionCurve(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1, max_length=80)
    start_value: dict[str, Any] = Field(default_factory=dict)
    end_value: dict[str, Any] = Field(default_factory=dict)
    easing: str = Field(min_length=1, max_length=80)
    jitter_allowed: bool = False
    speed: float = Field(ge=0)
    sync_to_audio: str | None = Field(default=None, max_length=120)


class ShadowSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    source_light_id: str | None = Field(default=None, max_length=120)
    offset_x: float = Field(ge=-1.0, le=1.0)
    offset_y: float = Field(ge=-1.0, le=1.0)
    blur: float = Field(ge=0.0, le=1.0)
    opacity: float = Field(ge=0.0, le=1.0)
    softness: float = Field(ge=0.0, le=1.0)
    derived_from_z_depth: bool = True
    contact_shadow_required: bool = False


class BlurSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    radius: float = Field(default=0.0, ge=0.0, le=1.0)
    background_blur: float = Field(default=0.0, ge=0.0, le=1.0)
    motion_blur: float = Field(default=0.0, ge=0.0, le=1.0)


class TimelineObject(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    object_id: str = Field(min_length=1, max_length=120)
    asset_id: str = Field(min_length=1, max_length=160)
    asset_label: str = Field(min_length=1, max_length=240)
    role: str = Field(min_length=1, max_length=80)
    scene_id: str = Field(min_length=1, max_length=120)
    start_time: float = Field(
        ge=0.0,
        validation_alias=AliasChoices("start_time", "start_seconds"),
    )
    end_time: float = Field(gt=0.0, validation_alias=AliasChoices("end_time", "end_seconds"))
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    z: float = Field(ge=0.0, le=1.0)
    scale: float = Field(gt=0.0, le=5.0)
    width_normalised: float = Field(gt=0.0, le=1.0)
    height_normalised: float = Field(gt=0.0, le=1.0)
    rotation: float = Field(ge=-360.0, le=360.0)
    opacity: float = Field(ge=0.0, le=1.0)
    anchor_point: Literal[
        "center",
        "top_left",
        "top_center",
        "top_right",
        "center_left",
        "center_right",
        "bottom_left",
        "bottom_center",
        "bottom_right",
    ] = "center"
    motion_curve: MotionCurve
    shadow_spec: ShadowSpec
    blur_spec: BlurSpec
    occlusion_group: str = Field(min_length=1, max_length=120)
    realism_reason: str = Field(min_length=1, max_length=500)

    @field_validator("role")
    @classmethod
    def _validate_role(cls, value: str) -> str:
        if value not in CINEMATIC_ROLES:
            raise ValueError(f"unknown cinematic role: {value}")
        return value

    @model_validator(mode="after")
    def _validate_span(self) -> TimelineObject:
        if self.end_time <= self.start_time:
            raise ValueError("timeline object end_time must be greater than start_time")
        if (
            self.role in {"hero_subject", "supporting_subject", "foreground_texture"}
            and self.shadow_spec.enabled
            and not self.shadow_spec.contact_shadow_required
        ):
            raise ValueError("foreground objects require contact_shadow_required=true")
        return self


class CameraMove(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    move_type: str = Field(min_length=1, max_length=80)
    start_time: float = Field(
        ge=0.0,
        validation_alias=AliasChoices("start_time", "start_seconds"),
    )
    end_time: float = Field(gt=0.0, validation_alias=AliasChoices("end_time", "end_seconds"))
    crop_x: float = Field(ge=0.0, le=1.0)
    crop_y: float = Field(ge=0.0, le=1.0)
    zoom: float = Field(gt=0.0, le=5.0)
    rotation: float = Field(ge=-30.0, le=30.0)
    shake_intensity: float = Field(ge=0.0, le=1.0)
    shake_frequency: float = Field(ge=0.0, le=60.0)
    motion_curve: MotionCurve

    @field_validator("move_type")
    @classmethod
    def _validate_move_type(cls, value: str) -> str:
        if value not in CAMERA_MOVES:
            raise ValueError(f"unknown camera move: {value}")
        return value

    @model_validator(mode="after")
    def _validate_span(self) -> CameraMove:
        if self.end_time <= self.start_time:
            raise ValueError("camera move end_time must be greater than start_time")
        return self


class CaptionSafeArea(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top: float = Field(default=0.08, ge=0.0, le=0.5)
    right: float = Field(default=0.06, ge=0.0, le=0.5)
    bottom: float = Field(default=0.08, ge=0.0, le=0.5)
    left: float = Field(default=0.06, ge=0.0, le=0.5)


class CaptionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    caption_id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=160)
    role: Literal["hook", "context", "payoff", "CTA"]
    start_time: float = Field(
        ge=0.0,
        validation_alias=AliasChoices("start_time", "start_seconds"),
    )
    end_time: float = Field(gt=0.0, validation_alias=AliasChoices("end_time", "end_seconds"))
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    max_width: float = Field(gt=0.0, le=1.0)
    font_size: int = Field(gt=0, le=160)
    weight: Literal["regular", "medium", "semibold", "bold"] = "semibold"
    alignment: Literal["left", "center", "right"] = "center"
    animation: str = Field(min_length=1, max_length=80)
    safe_area: CaptionSafeArea = Field(default_factory=CaptionSafeArea)
    safe_area_compliant: bool = True
    renderer_text_only: bool = True

    @model_validator(mode="after")
    def _validate_caption(self) -> CaptionPlan:
        if self.end_time <= self.start_time:
            raise ValueError("caption end_time must be greater than start_time")
        if not self.safe_area_compliant or not self.renderer_text_only:
            raise ValueError("captions must be safe-area compliant renderer text")
        if self.x < self.safe_area.left or self.x > 1.0 - self.safe_area.right:
            raise ValueError("caption x violates safe area")
        if self.y < self.safe_area.top or self.y > 1.0 - self.safe_area.bottom:
            raise ValueError("caption y violates safe area")
        if self.max_width > 1.0 - self.safe_area.left - self.safe_area.right:
            raise ValueError("caption max_width violates safe area")
        lowered = self.text.lower()
        if any(term in lowered for term in ("generate image", "baked text", "fake ui")):
            raise ValueError("caption text contains forbidden renderer/image instruction")
        return self


class AudioSyncPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time: float = Field(ge=0.0)
    label: str = Field(min_length=1, max_length=120)
    target_object_id: str | None = Field(default=None, max_length=120)


class AudioLayer(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    audio_id: str = Field(min_length=1, max_length=120)
    asset_id: str | None = Field(default=None, max_length=160)
    role: str = Field(min_length=1, max_length=80)
    start_time: float = Field(
        ge=0.0,
        validation_alias=AliasChoices("start_time", "start_seconds"),
    )
    end_time: float = Field(gt=0.0, validation_alias=AliasChoices("end_time", "end_seconds"))
    volume: float = Field(ge=0.0, le=1.5)
    fade_in: float = Field(ge=0.0)
    fade_out: float = Field(ge=0.0)
    sync_points: list[AudioSyncPoint] = Field(default_factory=list)

    @field_validator("role")
    @classmethod
    def _validate_role(cls, value: str) -> str:
        if value not in AUDIO_ROLES:
            raise ValueError(f"unknown audio role: {value}")
        return value

    @model_validator(mode="after")
    def _validate_span(self) -> AudioLayer:
        if self.end_time <= self.start_time:
            raise ValueError("audio layer end_time must be greater than start_time")
        if self.role not in {"silence_gap", "voiceover_placeholder"} and not self.asset_id:
            raise ValueError("known audio roles require asset_id unless silence/voiceover placeholder")
        return self


class LightSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    light_id: str = Field(min_length=1, max_length=120)
    type: Literal["softbox", "window", "overhead", "practical", "screen_glow"]
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    z: float = Field(ge=0.0, le=1.0)
    intensity: float = Field(ge=0.0, le=3.0)
    colour_temperature: int = Field(ge=1000, le=12000)
    softness: float = Field(ge=0.0, le=1.0)


class PerObjectShadowSpec(ShadowSpec):
    object_id: str = Field(min_length=1, max_length=120)


class LightingPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lights: list[LightSpec] = Field(default_factory=list, min_length=1)
    per_object_shadow_specs: list[PerObjectShadowSpec] = Field(default_factory=list)
    global_colour_temperature: int = Field(ge=1000, le=12000)
    contrast_level: Literal["low", "medium", "high"] = "medium"


class AudioPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layers: list[AudioLayer] = Field(default_factory=list)
    sync_points: list[AudioSyncPoint] = Field(default_factory=list)
    sensory_moments: list[str] = Field(default_factory=list)


class RealismConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dominant_subject_required: bool = True
    max_foreground_objects: int = Field(default=3, ge=1, le=8)
    require_contact_shadows: bool = True
    forbid_floating_assets: bool = True
    forbid_baked_text: bool = True
    forbid_fake_ui: bool = True
    require_depth_consistency: bool = True
    require_caption_safe_area: bool = True
    require_motion_continuity: bool = True


class RejectedAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1, max_length=160)
    reason: str = Field(min_length=1, max_length=500)


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_page_context_hash: str = Field(min_length=64, max_length=64)
    selected_asset_ids: list[str] = Field(default_factory=list, min_length=1)
    selected_prompt_paths: list[str] = Field(default_factory=list, min_length=1)
    planning_prompt_version: str = Field(min_length=1, max_length=80)
    plan_hash: str = Field(default="", max_length=64)
    rejected_assets: list[RejectedAsset] = Field(default_factory=list)
    realism_risk_score: float = Field(ge=0.0, le=1.0)

    @field_validator("selected_asset_ids")
    @classmethod
    def _dedupe_asset_ids(cls, value: list[str]) -> list[str]:
        return _dedupe(value)

    @field_validator("selected_prompt_paths")
    @classmethod
    def _validate_prompt_paths(cls, value: list[str]) -> list[str]:
        return normalize_prompt_paths(value)


class ScenePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    scene_id: str = Field(min_length=1, max_length=120)
    start_time: float = Field(
        ge=0.0,
        validation_alias=AliasChoices("start_time", "start_seconds"),
    )
    end_time: float = Field(gt=0.0, validation_alias=AliasChoices("end_time", "end_seconds"))
    purpose: str = Field(min_length=1, max_length=240)
    dominant_focal_role: str = Field(min_length=1, max_length=80)
    emotional_intent: str = Field(min_length=1, max_length=240)
    visual_density: Literal["low", "medium", "high"]
    camera_move: CameraMove
    objects: list[TimelineObject] = Field(default_factory=list, min_length=1)
    captions: list[CaptionPlan] = Field(default_factory=list)
    audio_layers: list[AudioLayer] = Field(default_factory=list)
    transition_in: str | None = Field(default=None, max_length=120)
    transition_out: str | None = Field(default=None, max_length=120)

    @field_validator("dominant_focal_role")
    @classmethod
    def _validate_dominant_role(cls, value: str) -> str:
        if value not in CINEMATIC_ROLES:
            raise ValueError(f"unknown dominant focal role: {value}")
        return value

    @model_validator(mode="after")
    def _validate_scene(self) -> ScenePlan:
        if self.end_time <= self.start_time:
            raise ValueError("scene end_time must be greater than start_time")
        object_roles = {item.role for item in self.objects}
        if self.dominant_focal_role not in object_roles:
            raise ValueError("dominant_focal_role must match a role used by a scene object")
        for item in self.objects:
            if item.scene_id != self.scene_id:
                raise ValueError("timeline object scene_id must match parent scene")
            if item.start_time < self.start_time or item.end_time > self.end_time:
                raise ValueError("timeline object timing must stay inside parent scene")
        for caption in self.captions:
            if caption.start_time < self.start_time or caption.end_time > self.end_time:
                raise ValueError("caption timing must stay inside parent scene")
        if self.camera_move.start_time < self.start_time or self.camera_move.end_time > self.end_time:
            raise ValueError("camera move timing must stay inside parent scene")
        return self


class NarrativeArc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hook: str = Field(min_length=1, max_length=240)
    development: str = Field(min_length=1, max_length=240)
    reveal_payoff: str = Field(min_length=1, max_length=240)
    closing_retention_loop: str = Field(min_length=1, max_length=240)


class CinematicReelPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(min_length=1, max_length=120)
    page_context_summary: str = Field(min_length=1, max_length=1000)
    content_goal: str | None = Field(default=None, max_length=1000)
    selected_prompt_paths: list[str] = Field(default_factory=list, min_length=1)
    narrative_arc: NarrativeArc
    total_duration_seconds: float = Field(gt=0.0, le=180.0)
    fps: int = Field(default=24, ge=1, le=120)
    canvas: CanvasSpec = Field(default_factory=CanvasSpec)
    scenes: list[ScenePlan] = Field(default_factory=list, min_length=1, max_length=12)
    global_camera_style: str = Field(min_length=1, max_length=500)
    global_lighting_style: str = Field(min_length=1, max_length=500)
    caption_strategy: str = Field(min_length=1, max_length=500)
    audio_strategy: str = Field(min_length=1, max_length=500)
    lighting_shadow_plan: LightingPlan
    audio_plan: AudioPlan
    realism_constraints: RealismConstraints
    render_notes: list[str] = Field(default_factory=list)
    provenance: Provenance

    @field_validator("selected_prompt_paths")
    @classmethod
    def _validate_paths(cls, value: list[str]) -> list[str]:
        return normalize_prompt_paths(value)

    @model_validator(mode="after")
    def _validate_plan(self) -> CinematicReelPlan:
        if self.provenance.selected_prompt_paths != self.selected_prompt_paths:
            raise ValueError("provenance.selected_prompt_paths must match selected_prompt_paths")
        _require_contiguous(
            [(scene.start_time, scene.end_time) for scene in self.scenes],
            expected_duration=self.total_duration_seconds,
            label="scenes",
        )
        selected_asset_ids = set(self.provenance.selected_asset_ids)
        used_asset_ids = self.used_asset_ids()
        unknown = sorted(asset_id for asset_id in used_asset_ids if asset_id not in selected_asset_ids)
        if unknown:
            raise ValueError(f"plan references unselected assets: {', '.join(unknown)}")
        rejected = {item.asset_id for item in self.provenance.rejected_assets}
        missing_rejections = sorted(selected_asset_ids - used_asset_ids - rejected)
        if missing_rejections:
            raise ValueError(
                "unused selected assets require provenance.rejected_assets entries: "
                + ", ".join(missing_rejections)
            )
        if used_asset_ids.intersection(rejected):
            raise ValueError("used assets cannot also be listed as rejected")
        if self.realism_constraints.dominant_subject_required and not self._has_hero_subject():
            raise ValueError("plan requires at least one hero_subject timeline object")
        if self._foreground_object_peak() > self.realism_constraints.max_foreground_objects:
            raise ValueError("too many simultaneous foreground objects")
        _validate_light_references(self)
        _validate_no_generation_instructions(self)
        return self

    def used_asset_ids(self) -> set[str]:
        asset_ids = {item.asset_id for scene in self.scenes for item in scene.objects}
        asset_ids.update(
            audio.asset_id
            for audio in self.audio_plan.layers
            if audio.asset_id is not None
        )
        for scene in self.scenes:
            asset_ids.update(
                audio.asset_id
                for audio in scene.audio_layers
                if audio.asset_id is not None
            )
        return asset_ids

    def _has_hero_subject(self) -> bool:
        return any(item.role == "hero_subject" for scene in self.scenes for item in scene.objects)

    def _foreground_object_peak(self) -> int:
        points = sorted(
            {
                point
                for scene in self.scenes
                for item in scene.objects
                if item.role in {"hero_subject", "supporting_subject", "foreground_texture"}
                for point in (item.start_time, item.end_time)
            }
        )
        peak = 0
        for point in points:
            active = sum(
                1
                for scene in self.scenes
                for item in scene.objects
                if item.role in {"hero_subject", "supporting_subject", "foreground_texture"}
                and item.start_time <= point < item.end_time
            )
            peak = max(peak, active)
        return peak


def _validate_light_references(plan: CinematicReelPlan) -> None:
    light_ids = {light.light_id for light in plan.lighting_shadow_plan.lights}
    object_ids = {item.object_id for scene in plan.scenes for item in scene.objects}
    for shadow_spec in plan.lighting_shadow_plan.per_object_shadow_specs:
        if shadow_spec.object_id not in object_ids:
            raise ValueError(f"shadow spec references unknown object_id: {shadow_spec.object_id}")
        if shadow_spec.enabled and shadow_spec.source_light_id not in light_ids:
            raise ValueError(f"shadow spec references unknown light_id: {shadow_spec.source_light_id}")
    for scene in plan.scenes:
        for item in scene.objects:
            shadow = item.shadow_spec
            if shadow.enabled and shadow.source_light_id not in light_ids:
                raise ValueError(f"object {item.object_id} references unknown light_id")


def _validate_no_generation_instructions(plan: CinematicReelPlan) -> None:
    material = " ".join(
        [
            plan.page_context_summary,
            plan.global_camera_style,
            plan.global_lighting_style,
            plan.caption_strategy,
            plan.audio_strategy,
            *plan.render_notes,
            *(scene.purpose for scene in plan.scenes),
            *(item.realism_reason for scene in plan.scenes for item in scene.objects),
        ]
    ).lower()
    if any(term in material for term in FORBIDDEN_GENERATION_TERMS):
        raise ValueError("plan contains forbidden external generation or screenshot instructions")


def _require_contiguous(
    spans: Iterable[tuple[float, float]],
    *,
    expected_duration: float,
    label: str,
) -> None:
    ordered = sorted(spans, key=lambda item: item[0])
    cursor = 0.0
    tolerance = 1e-6
    for index, (start, end) in enumerate(ordered):
        if abs(start - cursor) > tolerance:
            raise ValueError(f"{label}[{index}] is non-contiguous")
        if end <= start:
            raise ValueError(f"{label}[{index}] has invalid timing")
        cursor = end
    if abs(cursor - expected_duration) > 1e-6:
        raise ValueError(f"{label} must cover total_duration_seconds")


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


__all__ = [
    "AUDIO_ROLES",
    "CAMERA_MOVES",
    "CINEMATIC_ROLES",
    "PROMPT_PATHS",
    "AudioLayer",
    "AudioPlan",
    "AudioSyncPoint",
    "BlurSpec",
    "CameraMove",
    "CanvasSpec",
    "CaptionPlan",
    "CaptionSafeArea",
    "CinematicReelPlan",
    "LightSpec",
    "LightingPlan",
    "MotionCurve",
    "NarrativeArc",
    "PerObjectShadowSpec",
    "Provenance",
    "RealismConstraints",
    "RejectedAsset",
    "ScenePlan",
    "ShadowSpec",
    "TimelineObject",
]
