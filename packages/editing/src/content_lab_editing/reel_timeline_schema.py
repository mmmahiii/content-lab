"""Renderer-oriented timeline projection for cinematic reel plans."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReelTimelineObject(BaseModel):
    model_config = ConfigDict(extra="allow")

    object_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    scene_id: str = Field(min_length=1)
    start_time: float = Field(ge=0.0)
    end_time: float = Field(gt=0.0)
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    z: float = Field(ge=0.0, le=1.0)
    scale: float = Field(gt=0.0)
    width_normalised: float = Field(gt=0.0, le=1.0)
    height_normalised: float = Field(gt=0.0, le=1.0)
    source_width: int | None = Field(default=None, gt=0)
    source_height: int | None = Field(default=None, gt=0)
    opacity: float = Field(ge=0.0, le=1.0)
    role: str = "independent"
    support_object_id: str | None = None
    support_surface_mask_uri: str | None = None
    spatial_relationship: Literal[
        "on_surface",
        "inside",
        "behind",
        "in_front_of",
        "attached_to",
        "adjacent_to",
        "overlay_on",
        "atmospheric",
        "independent",
    ] = "independent"
    required_overlap_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    max_overlap_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    support_contact_required: bool = False
    must_remain_inside_support_bounds: bool = False
    relative_depth_rule: Literal[
        "above_support",
        "below_hero",
        "behind_hero",
        "same_plane",
        "independent",
    ] = "independent"
    contact_shadow_target_object_id: str | None = None
    relationship_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    relationship_reason: str = "No explicit physical dependency."
    view_angle: Literal["top_down", "front", "side", "three_quarter", "overhead", "unknown"] = (
        "unknown"
    )
    surface_plane: Literal["horizontal", "vertical", "angled", "floating", "unknown"] = "unknown"
    lighting_direction: Literal[
        "upper_left",
        "upper_right",
        "overhead",
        "front",
        "mixed",
        "unknown",
    ] = "unknown"
    preferred_screen_regions: list[str] = Field(default_factory=list)
    forbidden_screen_regions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_span(self) -> ReelTimelineObject:
        if self.end_time <= self.start_time:
            raise ValueError("timeline object end_time must be greater than start_time")
        if (
            self.spatial_relationship
            in {"on_surface", "inside", "attached_to", "overlay_on"}
            and not self.support_object_id
        ):
            raise ValueError(f"{self.spatial_relationship} relationship requires support_object_id")
        if self.support_contact_required and not self.contact_shadow_target_object_id:
            raise ValueError(
                "support_contact_required=true requires contact_shadow_target_object_id"
            )
        if self.spatial_relationship == "inside" and self.required_overlap_ratio < 0.5:
            raise ValueError("inside relationship requires required_overlap_ratio >= 0.5")
        if self.spatial_relationship == "atmospheric" and self.support_contact_required:
            raise ValueError("atmospheric objects cannot require hard contact shadows")
        if self.required_overlap_ratio > self.max_overlap_ratio:
            raise ValueError("required_overlap_ratio cannot exceed max_overlap_ratio")
        return self


class ReelTimeline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(min_length=1)
    total_duration_seconds: float = Field(gt=0.0)
    fps: int = Field(gt=0)
    canvas: dict[str, Any]
    render_strategy: str = "realistic_single_scene"
    objects: list[ReelTimelineObject] = Field(default_factory=list)
    captions: list[dict[str, Any]] = Field(default_factory=list)
    camera_moves: list[dict[str, Any]] = Field(default_factory=list)
    audio_layers: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_bounds(self) -> ReelTimeline:
        for item in self.objects:
            if item.end_time > self.total_duration_seconds:
                raise ValueError(f"object {item.object_id} exceeds timeline duration")
        return self


__all__ = ["ReelTimeline", "ReelTimelineObject"]
