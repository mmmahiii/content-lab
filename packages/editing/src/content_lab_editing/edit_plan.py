"""Scene-aware edit plan models and deterministic compilers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_PURPOSE_ORDER = {
    "hook": 0,
    "setup": 1,
    "value": 2,
    "payoff": 3,
    "close": 4,
}


class SceneEditPlanSegment(BaseModel):
    """One source segment placed onto the final reel timeline."""

    model_config = ConfigDict(extra="forbid")

    segment_id: str = Field(min_length=1, max_length=80)
    scene_id: str = Field(min_length=1, max_length=80)
    purpose: str = Field(min_length=1, max_length=40)
    source_uri: str = Field(min_length=1)
    source_start_seconds: float = Field(default=0.0, ge=0.0)
    duration_seconds: float = Field(gt=0.0, le=180.0)
    timeline_start_seconds: float = Field(ge=0.0)
    timeline_end_seconds: float | None = Field(default=None, gt=0.0)

    @model_validator(mode="after")
    def _validate_timing(self) -> SceneEditPlanSegment:
        expected_end = self.timeline_start_seconds + self.duration_seconds
        if self.timeline_end_seconds is None:
            self.timeline_end_seconds = expected_end
        if abs(self.timeline_end_seconds - expected_end) > 1e-6:
            raise ValueError("timeline_end_seconds must equal start plus duration")
        return self


class SceneAwareEditPlan(BaseModel):
    """A structured sequence of scene segments for the basic editor."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["phase_1"] = "phase_1"
    compiler_name: str = Field(default="deterministic_scene_edit_plan_v1", min_length=1)
    segments: list[SceneEditPlanSegment] = Field(default_factory=list, min_length=1, max_length=12)
    metadata: dict[str, object] = Field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        return self.segments[-1].timeline_end_seconds or 0.0

    @property
    def source_uris(self) -> tuple[str, ...]:
        return tuple(segment.source_uri for segment in self.segments)

    @model_validator(mode="after")
    def _validate_timeline(self) -> SceneAwareEditPlan:
        previous_end = 0.0
        for segment in self.segments:
            if segment.timeline_start_seconds < previous_end - 1e-6:
                raise ValueError("edit plan segments must be ordered and non-overlapping")
            if abs(segment.timeline_start_seconds - previous_end) > 1e-6:
                raise ValueError("edit plan segments must be contiguous")
            previous_end = segment.timeline_end_seconds or 0.0
        return self


def build_single_clip_edit_plan(
    *,
    source_uri: str,
    duration_seconds: float,
    purpose: str = "single_clip",
) -> SceneAwareEditPlan:
    """Build a one-segment plan for callers that want explicit fallback structure."""

    return SceneAwareEditPlan(
        segments=[
            SceneEditPlanSegment(
                segment_id="segment-001",
                scene_id="single-clip",
                purpose=purpose,
                source_uri=source_uri,
                duration_seconds=duration_seconds,
                timeline_start_seconds=0.0,
            )
        ],
        metadata={"fallback": "single_clip"},
    )


def build_scene_aware_edit_plan(
    *,
    scene_plan: Mapping[str, Any],
    scene_asset_uris: Mapping[str, str] | Sequence[str],
    default_source_uri: str | None = None,
) -> SceneAwareEditPlan:
    """Compile scene-plan nodes and source assets into a deterministic edit timeline."""

    scenes = _ordered_scenes(scene_plan)
    if not scenes:
        raise ValueError("scene_plan must contain at least one scene")

    segments: list[SceneEditPlanSegment] = []
    cursor = 0.0
    for index, scene in enumerate(scenes, start=1):
        scene_id = str(scene.get("scene_id") or f"scene-{index:03d}")
        start = float(scene.get("start_seconds") or 0.0)
        end = float(scene.get("end_seconds") or 0.0)
        duration = max(end - start, 0.0)
        if duration <= 0.0:
            raise ValueError(f"scene {scene_id} must have positive duration")
        source_uri = _source_uri_for_scene(
            scene_id=scene_id,
            scene_index=index - 1,
            scene_asset_uris=scene_asset_uris,
            default_source_uri=default_source_uri,
        )
        segments.append(
            SceneEditPlanSegment(
                segment_id=f"segment-{index:03d}",
                scene_id=scene_id,
                purpose=str(scene.get("purpose") or "scene"),
                source_uri=source_uri,
                source_start_seconds=0.0,
                duration_seconds=duration,
                timeline_start_seconds=cursor,
            )
        )
        cursor += duration

    return SceneAwareEditPlan(
        segments=segments,
        metadata={
            "source_scene_plan_schema": scene_plan.get("schema_version", "unknown"),
            "scene_count": len(segments),
        },
    )


def _ordered_scenes(scene_plan: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw_scenes = scene_plan.get("scenes")
    if not isinstance(raw_scenes, list):
        return []
    scenes = [scene for scene in raw_scenes if isinstance(scene, Mapping)]
    return sorted(
        scenes,
        key=lambda scene: (
            float(scene.get("start_seconds") or 0.0),
            _PURPOSE_ORDER.get(str(scene.get("purpose") or ""), 99),
            str(scene.get("scene_id") or ""),
        ),
    )


def _source_uri_for_scene(
    *,
    scene_id: str,
    scene_index: int,
    scene_asset_uris: Mapping[str, str] | Sequence[str],
    default_source_uri: str | None,
) -> str:
    if isinstance(scene_asset_uris, Mapping):
        source_uri = scene_asset_uris.get(scene_id) or default_source_uri
    else:
        source_uri = scene_asset_uris[scene_index] if scene_index < len(scene_asset_uris) else None
        source_uri = source_uri or default_source_uri
    if source_uri is None or not str(source_uri).strip():
        raise ValueError(f"Missing source asset URI for scene {scene_id}")
    return str(source_uri).strip()
