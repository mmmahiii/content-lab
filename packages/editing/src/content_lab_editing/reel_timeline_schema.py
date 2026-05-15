"""Renderer-oriented timeline projection for cinematic reel plans."""

from __future__ import annotations

from typing import Any

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
    opacity: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_span(self) -> ReelTimelineObject:
        if self.end_time <= self.start_time:
            raise ValueError("timeline object end_time must be greater than start_time")
        return self


class ReelTimeline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(min_length=1)
    total_duration_seconds: float = Field(gt=0.0)
    fps: int = Field(gt=0)
    canvas: dict[str, Any]
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
