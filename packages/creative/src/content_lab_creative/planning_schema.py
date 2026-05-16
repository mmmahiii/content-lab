"""Strict contracts for single-prompt cinematic reel plans."""

from __future__ import annotations

import re
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

_FORBIDDEN_TEXT_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("generate image", "use selected image asset"),
    ("generate video", "use selected video asset"),
    ("create image", "use selected image asset"),
    ("create video", "use selected video asset"),
    ("call runway", "use stored provider output"),
    ("call midjourney", "use stored image asset"),
    ("call dalle", "use stored image asset"),
    ("external video api", "stored video asset"),
    ("external image api", "stored image asset"),
    ("screenshot", "reference frame"),
    ("copy existing reel", "follow the approved reel structure"),
)

_ROLE_ALIASES: dict[str, str] = {
    "base_ingredient_layer": "supporting_subject",
    "colour_contrast_ingredient": "supporting_subject",
    "colour_contrast_subject": "supporting_subject",
    "completed_prep_composition": "narrative_payoff",
    "continuity_hero_ingredient": "hero_subject",
    "dominant_prep_ingredient": "hero_subject",
    "dominant_subject": "hero_subject",
    "eggplant_tactile_hook": "hero_subject",
    "final_composed_prep_frame": "narrative_payoff",
    "final_garnish": "narrative_payoff",
    "final_payoff_prop": "narrative_payoff",
    "final_prep_anchor": "supporting_subject",
    "final_texture_topping": "foreground_texture",
    "finished_prep_bowl_and_topping": "narrative_payoff",
    "finished_topping_reveal": "narrative_payoff",
    "fresh_finish_detail": "foreground_texture",
    "fresh_finish_subject": "narrative_payoff",
    "fresh_loop_detail": "foreground_texture",
    "hero_ingredient": "hero_subject",
    "hero_tomato": "hero_subject",
    "hero_tomato_loop": "hero_subject",
    "hero_tomato_slice": "hero_subject",
    "ingredient_step": "supporting_subject",
    "loop_anchor_ingredient": "supporting_subject",
    "loop_bridge_ingredient": "supporting_subject",
    "loop_edge_anchor": "transition_element",
    "loop_subject": "hero_subject",
    "mise_en_place_ingredient_build": "supporting_subject",
    "payoff_basil_garnish": "narrative_payoff",
    "payoff_garnish": "narrative_payoff",
    "payoff_prep_bowl": "narrative_payoff",
    "payoff_prop": "narrative_payoff",
    "prep_bowl_anchor": "supporting_subject",
    "ratatouille_background_reveal": "background_reveal",
    "support_eggplant_cut": "supporting_subject",
    "supporting_colour_base": "supporting_subject",
    "supporting_ingredient": "supporting_subject",
    "supporting_ingredient_colour": "supporting_subject",
    "supporting_prep_base": "supporting_subject",
    "texture_accent": "foreground_texture",
    "tomato_foreground_texture": "foreground_texture",
    "vegetable_layer_assembly": "supporting_subject",
}

_CAMERA_MOVE_ALIASES: dict[str, str] = {
    "handheld": "handheld_micro_motion",
    "lateral_slide": "slight_pan_right",
    "locked": "static_lockoff",
    "locked_off": "static_lockoff",
    "micro_motion": "handheld_micro_motion",
    "micro_pullback": "slow_pull_out",
    "pan_left": "slight_pan_left",
    "pan_right": "slight_pan_right",
    "pan_right_push": "parallax_push",
    "pull_back": "slow_pull_out",
    "pullback": "slow_pull_out",
    "push_in": "slow_push_in",
    "slide_left": "slight_pan_left",
    "slide_right": "slight_pan_right",
    "speed_ramp_push": "speed_ramp_focus",
    "static": "static_lockoff",
    "tilt_down": "slight_pan_right",
    "tilt_up": "slight_pan_left",
}

_AUDIO_ROLE_ALIASES: dict[str, str] = {
    "ambient_kitchen_bed": "ambient_room",
    "ambient_rhythmic_kitchen_bed": "ambient_room",
    "diegetic_food_movement_accents": "impact",
    "final_ambience_hold": "ambient_room",
    "foley_accents": "impact",
    "ingredient_placement_foley": "impact",
    "loop_tail": "soft_whoosh",
    "music_bed": "ambient_room",
    "payoff_accent": "impact",
    "payoff_lift": "subtle_riser",
    "payoff_reveal_lift": "subtle_riser",
    "scene_slide_accent": "impact",
    "tomato_and_pepper_placement_accents": "impact",
}

_NORMALIZED_OBJECT_FIELDS: tuple[str, ...] = (
    "x",
    "y",
    "z",
    "opacity",
    "width_normalised",
    "height_normalised",
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
        value = normalize_cinematic_role_value(value) or value
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
        value = normalize_camera_move_value(value) or value
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

    @model_validator(mode="before")
    @classmethod
    def _canonicalize_audio_layer_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        audio_layer = dict(value)
        role = normalize_audio_role_value(audio_layer.get("role"))
        if role is not None:
            audio_layer["role"] = role
        return audio_layer

    @field_validator("role")
    @classmethod
    def _validate_role(cls, value: str) -> str:
        value = normalize_audio_role_value(value) or value
        if value not in AUDIO_ROLES:
            raise ValueError(f"unknown audio role: {value}")
        return value

    @model_validator(mode="after")
    def _validate_span(self) -> AudioLayer:
        if self.end_time <= self.start_time:
            raise ValueError("audio layer end_time must be greater than start_time")
        if (
            self.role not in {"silence_gap", "voiceover_placeholder"}
            and not self.asset_id
            and not _is_placeholder_audio_layer(self)
        ):
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

    @model_validator(mode="before")
    @classmethod
    def _canonicalize_audio_plan_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        audio_plan = dict(value)
        for audio_layer in _iter_raw_dicts(audio_plan.get("layers")):
            role = normalize_audio_role_value(audio_layer.get("role"))
            if role is not None:
                audio_layer["role"] = role
        return audio_plan


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

    @model_validator(mode="before")
    @classmethod
    def _canonicalize_scene_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        scene = dict(value)
        for item in _iter_raw_dicts(scene.get("objects")):
            role = normalize_cinematic_role_value(item.get("role"))
            if role is not None:
                item["role"] = role
            for field_name in _NORMALIZED_OBJECT_FIELDS:
                _clamp_raw_numeric_field(
                    item,
                    field_name,
                    lower=0.01 if field_name in {"width_normalised", "height_normalised"} else 0.0,
                    upper=1.0,
                )
            _clamp_raw_numeric_field(item, "scale", lower=0.01, upper=5.0)
            _clamp_raw_numeric_field(item, "rotation", lower=-360.0, upper=360.0)
            _enforce_raw_subject_minimum_footprint(item)
        camera_move = scene.get("camera_move")
        if isinstance(camera_move, dict):
            move_type = normalize_camera_move_value(camera_move.get("move_type"))
            if move_type is not None:
                camera_move["move_type"] = move_type
        for audio_layer in _iter_raw_dicts(scene.get("audio_layers")):
            role = normalize_audio_role_value(audio_layer.get("role"))
            if role is not None:
                audio_layer["role"] = role
        original_focal_role = scene.get("dominant_focal_role")
        focal_role = normalize_cinematic_role_value(original_focal_role)
        if focal_role is not None:
            scene["dominant_focal_role"] = focal_role
        object_roles = {
            item.get("role")
            for item in _iter_raw_dicts(scene.get("objects"))
            if item.get("role") in CINEMATIC_ROLES
        }
        original_focal_is_canonical = (
            isinstance(original_focal_role, str)
            and original_focal_role.strip().lower() in CINEMATIC_ROLES
        )
        if (
            not original_focal_is_canonical
            and scene.get("dominant_focal_role") not in object_roles
            and object_roles
        ):
            scene["dominant_focal_role"] = _preferred_raw_dominant_role(scene)
        _limit_raw_scene_high_priority_roles(scene)
        return scene

    @field_validator("dominant_focal_role")
    @classmethod
    def _validate_dominant_role(cls, value: str) -> str:
        value = normalize_cinematic_role_value(value) or value
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

    @model_validator(mode="before")
    @classmethod
    def _canonicalize_plan_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        _canonicalize_raw_light_references(payload)
        _sanitize_raw_generation_instruction_text(payload)
        return payload

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
        _repair_model_light_references(self)
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


def _repair_model_light_references(plan: CinematicReelPlan) -> None:
    light_ids = [light.light_id for light in plan.lighting_shadow_plan.lights]
    if not light_ids:
        return
    known_light_ids = set(light_ids)
    fallback_light_id = light_ids[0]
    for shadow_spec in plan.lighting_shadow_plan.per_object_shadow_specs:
        if not shadow_spec.enabled:
            shadow_spec.source_light_id = None
        elif shadow_spec.source_light_id not in known_light_ids:
            shadow_spec.source_light_id = fallback_light_id
    for scene in plan.scenes:
        for item in scene.objects:
            shadow = item.shadow_spec
            if not shadow.enabled:
                shadow.source_light_id = None
            elif shadow.source_light_id not in known_light_ids:
                shadow.source_light_id = fallback_light_id


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


def _sanitize_raw_generation_instruction_text(payload: dict[str, Any]) -> None:
    for key in (
        "page_context_summary",
        "global_camera_style",
        "global_lighting_style",
        "caption_strategy",
        "audio_strategy",
    ):
        payload[key] = _sanitized_text(payload.get(key))
    render_notes = payload.get("render_notes")
    if isinstance(render_notes, list):
        payload["render_notes"] = [
            _sanitized_text(note) if isinstance(note, str) else note for note in render_notes
        ]
    for scene in _iter_raw_dicts(payload.get("scenes")):
        scene["purpose"] = _sanitized_text(scene.get("purpose"))
        for item in _iter_raw_dicts(scene.get("objects")):
            item["realism_reason"] = _sanitized_text(item.get("realism_reason"))


def _sanitized_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    sanitized = value
    for forbidden, replacement in _FORBIDDEN_TEXT_REPLACEMENTS:
        sanitized = re.sub(re.escape(forbidden), replacement, sanitized, flags=re.IGNORECASE)
    return sanitized


def _canonicalize_raw_light_references(payload: dict[str, Any]) -> None:
    lighting_plan = payload.get("lighting_shadow_plan")
    if not isinstance(lighting_plan, dict):
        return
    light_ids = [
        light.get("light_id")
        for light in _iter_raw_dicts(lighting_plan.get("lights"))
        if isinstance(light.get("light_id"), str) and light.get("light_id")
    ]
    if not light_ids:
        return
    fallback_light_id = str(light_ids[0])
    known_light_ids = set(light_ids)
    for scene in _iter_raw_dicts(payload.get("scenes")):
        for item in _iter_raw_dicts(scene.get("objects")):
            shadow = item.get("shadow_spec")
            if isinstance(shadow, dict):
                _canonicalize_raw_shadow_light_id(
                    shadow,
                    known_light_ids=known_light_ids,
                    fallback_light_id=fallback_light_id,
                )
    for shadow in _iter_raw_dicts(lighting_plan.get("per_object_shadow_specs")):
        _canonicalize_raw_shadow_light_id(
            shadow,
            known_light_ids=known_light_ids,
            fallback_light_id=fallback_light_id,
        )


def _canonicalize_raw_shadow_light_id(
    shadow: dict[str, Any],
    *,
    known_light_ids: set[str],
    fallback_light_id: str,
) -> None:
    if shadow.get("enabled") is False:
        shadow["source_light_id"] = None
        return
    if shadow.get("source_light_id") not in known_light_ids:
        shadow["source_light_id"] = fallback_light_id


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


def normalize_cinematic_role_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    lowered = value.strip().lower()
    if lowered in CINEMATIC_ROLES:
        return lowered
    alias_key = _alias_key(lowered)
    if alias_key in _ROLE_ALIASES:
        return _ROLE_ALIASES[alias_key]
    if "transition" in lowered:
        return "transition_element"
    if "caption" in lowered:
        return "caption_support"
    if "logo" in lowered or "brand" in lowered:
        return "brand_marker"
    if "steam" in lowered or "atmosphere" in lowered or "overlay" in lowered:
        return "atmospheric_layer"
    if "motion" in lowered:
        return "motion_layer"
    if "audio" in lowered or "sound" in lowered:
        return "audio_layer"
    if any(
        token in lowered
        for token in ("payoff", "final", "finish", "finished", "complete", "completed", "topping")
    ):
        return "narrative_payoff"
    if "background" in lowered or "reveal" in lowered:
        return "background_reveal"
    if "environment" in lowered or "base" in lowered:
        return "environment_base"
    if any(token in lowered for token in ("texture", "foreground", "detail")):
        return "foreground_texture"
    if "hero" in lowered or "main" in lowered or "hook" in lowered or alias_key.endswith("_subject"):
        return "hero_subject"
    if any(
        token in lowered
        for token in ("ingredient", "vegetable", "garnish", "bowl", "prop", "support", "prep", "layer")
    ):
        return "supporting_subject"
    return "supporting_subject"


def normalize_camera_move_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    lowered = value.strip().lower()
    if lowered in CAMERA_MOVES:
        return lowered
    alias_key = _alias_key(lowered)
    if alias_key in _CAMERA_MOVE_ALIASES:
        return _CAMERA_MOVE_ALIASES[alias_key]
    if "speed" in lowered and "ramp" in lowered:
        return "speed_ramp_focus"
    if "snap" in lowered or "reframe" in lowered:
        return "snap_reframe"
    if "parallax" in lowered:
        return "parallax_push"
    if "push" in lowered:
        return "slow_push_in"
    if "pull" in lowered or "back" in lowered:
        return "slow_pull_out"
    if ("slide" in lowered or "truck" in lowered) and "left" in lowered:
        return "slight_pan_left"
    if ("slide" in lowered or "truck" in lowered) and "right" in lowered:
        return "slight_pan_right"
    if "pan" in lowered and "left" in lowered:
        return "slight_pan_left"
    if "pan" in lowered and "right" in lowered:
        return "slight_pan_right"
    if "tilt" in lowered or "lateral" in lowered or lowered == "slide":
        return "slight_pan_right"
    if "handheld" in lowered or "micro" in lowered:
        return "handheld_micro_motion"
    if "static" in lowered or "lock" in lowered:
        return "static_lockoff"
    return "static_lockoff"


def normalize_audio_role_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    lowered = value.strip().lower()
    if lowered in AUDIO_ROLES:
        return lowered
    alias_key = _alias_key(lowered)
    if alias_key in _AUDIO_ROLE_ALIASES:
        return _AUDIO_ROLE_ALIASES[alias_key]
    if "sizzle" in lowered:
        return "sensory_sizzle"
    if "whoosh" in lowered or "loop" in lowered:
        return "soft_whoosh"
    if "transition" in lowered and "hit" in lowered:
        return "transition_hit"
    if any(token in lowered for token in ("hit", "accent", "foley", "impact", "placement")):
        return "impact"
    if "riser" in lowered or "lift" in lowered:
        return "subtle_riser"
    if "silence" in lowered:
        return "silence_gap"
    if "voice" in lowered:
        return "voiceover_placeholder"
    if any(
        token in lowered
        for token in ("ambient", "ambience", "ambiance", "music", "bed", "room", "kitchen")
    ):
        return "ambient_room"
    return "ambient_room"


def _iter_raw_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _preferred_raw_dominant_role(scene: dict[str, Any]) -> str:
    roles = [
        item.get("role")
        for item in _iter_raw_dicts(scene.get("objects"))
        if item.get("role") in CINEMATIC_ROLES
    ]
    for preferred in ("hero_subject", "narrative_payoff", "foreground_texture", "supporting_subject"):
        if preferred in roles:
            return preferred
    return str(roles[0])


def _limit_raw_scene_high_priority_roles(scene: dict[str, Any]) -> None:
    objects = _iter_raw_dicts(scene.get("objects"))
    hero_objects = [item for item in objects if item.get("role") == "hero_subject"]
    payoff_objects = [item for item in objects if item.get("role") == "narrative_payoff"]
    keep_high_priority: set[int] = set()
    if hero_objects:
        keep_high_priority.add(id(hero_objects[0]))
    if payoff_objects:
        keep_high_priority.add(id(payoff_objects[0]))
    if scene.get("dominant_focal_role") == "hero_subject" and hero_objects:
        keep_high_priority.add(id(hero_objects[0]))
    if scene.get("dominant_focal_role") == "narrative_payoff" and payoff_objects:
        keep_high_priority.add(id(payoff_objects[0]))
    for item in objects:
        if item.get("role") in {"hero_subject", "narrative_payoff"} and id(item) not in keep_high_priority:
            item["role"] = "supporting_subject"
    object_roles = {item.get("role") for item in objects if item.get("role") in CINEMATIC_ROLES}
    if (
        scene.get("dominant_focal_role") in {"hero_subject", "narrative_payoff"}
        and scene.get("dominant_focal_role") not in object_roles
        and object_roles
    ):
        scene["dominant_focal_role"] = _preferred_raw_dominant_role(scene)


def _enforce_raw_subject_minimum_footprint(item: dict[str, Any]) -> None:
    if item.get("role") not in {"hero_subject", "supporting_subject"}:
        return
    width = item.get("width_normalised")
    height = item.get("height_normalised")
    scale = item.get("scale")
    if not isinstance(width, int | float) or not isinstance(height, int | float):
        return
    scale_value = float(scale) if isinstance(scale, int | float) else 1.0
    area = float(width) * float(height) * scale_value * scale_value
    if area >= 0.015:
        return
    min_side = 0.13
    item["width_normalised"] = max(float(width), min_side)
    item["height_normalised"] = max(float(height), min_side)


def _clamp_raw_numeric_field(
    target: dict[str, Any],
    field_name: str,
    *,
    lower: float,
    upper: float,
) -> None:
    value = target.get(field_name)
    if isinstance(value, int | float):
        target[field_name] = min(max(float(value), lower), upper)


def _is_placeholder_audio_layer(layer: AudioLayer) -> bool:
    material = " ".join(
        item
        for item in (
            layer.audio_id,
            layer.role,
            *(sync_point.label for sync_point in layer.sync_points),
        )
        if item
    ).lower()
    return any(token in material for token in ("placeholder", "temp", "scratch", "planned"))


def _alias_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


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
