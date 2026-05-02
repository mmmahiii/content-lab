"""Canonical timeline contract for MED-001 timing authority."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_AUDIO_FADE_IN_SECONDS = 0.12
DEFAULT_AUDIO_FADE_OUT_SECONDS = 0.18


class TimelineSourceClip(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clip_id: str = Field(min_length=1, max_length=120)
    duration_seconds: float = Field(gt=0.0)
    uri: str | None = None


class TimelineScene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(min_length=1, max_length=120)
    start_seconds: float = Field(ge=0.0)
    end_seconds: float = Field(gt=0.0)
    source_clip_id: str = Field(min_length=1, max_length=120)
    source_start_seconds: float = Field(ge=0.0, default=0.0)
    source_end_seconds: float | None = Field(default=None, gt=0.0)
    purpose: str | None = None

    @model_validator(mode="after")
    def _validate_span(self) -> TimelineScene:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("scene end_seconds must be greater than start_seconds")
        if (
            self.source_end_seconds is not None
            and self.source_end_seconds <= self.source_start_seconds
        ):
            raise ValueError("scene source_end_seconds must be greater than source_start_seconds")
        return self


class TimelineEditSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: str = Field(min_length=1, max_length=120)
    timeline_start_seconds: float = Field(ge=0.0)
    timeline_end_seconds: float = Field(gt=0.0)
    source_clip_id: str = Field(min_length=1, max_length=120)
    source_start_seconds: float = Field(ge=0.0, default=0.0)
    source_end_seconds: float = Field(gt=0.0)
    scene_id: str | None = None
    purpose: str | None = None

    @property
    def duration_seconds(self) -> float:
        return self.timeline_end_seconds - self.timeline_start_seconds

    @model_validator(mode="after")
    def _validate_span(self) -> TimelineEditSegment:
        if self.timeline_end_seconds <= self.timeline_start_seconds:
            raise ValueError(
                "segment timeline_end_seconds must be greater than timeline_start_seconds"
            )
        if self.source_end_seconds <= self.source_start_seconds:
            raise ValueError("segment source_end_seconds must be greater than source_start_seconds")
        return self


class TimelineOverlay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overlay_id: str = Field(min_length=1, max_length=120)
    start_seconds: float = Field(ge=0.0)
    end_seconds: float = Field(gt=0.0)
    text: str = Field(min_length=1)
    role: str = Field(default="other", min_length=1, max_length=40)
    track: str = Field(default="primary", min_length=1, max_length=40)
    allow_overlap: bool = False

    @model_validator(mode="after")
    def _validate_span(self) -> TimelineOverlay:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("overlay end_seconds must be greater than start_seconds")
        return self


class TimelineAudioTrack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    track_id: str = Field(min_length=1, max_length=120)
    role: Literal["narration", "music", "sfx", "master"] = "master"
    start_seconds: float = Field(ge=0.0, default=0.0)
    end_seconds: float = Field(gt=0.0)
    fade_in_seconds: float = Field(ge=0.0, default=0.0)
    fade_out_seconds: float = Field(ge=0.0, default=0.0)

    @model_validator(mode="after")
    def _validate_span(self) -> TimelineAudioTrack:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("audio end_seconds must be greater than start_seconds")
        span = self.end_seconds - self.start_seconds
        if self.fade_in_seconds + self.fade_out_seconds > span + 1e-6:
            raise ValueError("audio fade_in_seconds + fade_out_seconds exceeds track span")
        return self


class CanonicalTimeline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["med-001.v1"] = "med-001.v1"
    timeline_id: str = Field(min_length=1, max_length=120)
    duration_seconds: float = Field(gt=0.0)
    cover_frame_timestamp_seconds: float = Field(ge=0.0)
    source_clips: list[TimelineSourceClip] = Field(default_factory=list, min_length=1)
    scenes: list[TimelineScene] = Field(default_factory=list, min_length=1)
    edit_segments: list[TimelineEditSegment] = Field(default_factory=list, min_length=1)
    overlays: list[TimelineOverlay] = Field(default_factory=list)
    audio_tracks: list[TimelineAudioTrack] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_contract(self) -> CanonicalTimeline:
        tol = 1e-6
        if self.cover_frame_timestamp_seconds > self.duration_seconds + tol:
            raise ValueError("cover_frame_timestamp_seconds exceeds timeline duration")

        _require_contiguous_spans(
            "scenes",
            [(it.start_seconds, it.end_seconds) for it in self.scenes],
            expected_duration=self.duration_seconds,
        )
        _require_contiguous_spans(
            "edit_segments",
            [(it.timeline_start_seconds, it.timeline_end_seconds) for it in self.edit_segments],
            expected_duration=self.duration_seconds,
        )
        for ov in self.overlays:
            if ov.end_seconds > self.duration_seconds + tol:
                raise ValueError(f"overlay {ov.overlay_id} exceeds timeline duration")
        self._validate_overlay_overlap_policy()
        for track in self.audio_tracks:
            if track.end_seconds > self.duration_seconds + tol:
                raise ValueError(f"audio track {track.track_id} exceeds timeline duration")
        return self

    def _validate_overlay_overlap_policy(self) -> None:
        ordered = sorted(self.overlays, key=lambda item: (item.start_seconds, item.end_seconds))
        for idx in range(len(ordered) - 1):
            current = ordered[idx]
            following = ordered[idx + 1]
            if current.end_seconds <= following.start_seconds + 1e-6:
                continue
            if current.allow_overlap or following.allow_overlap:
                continue
            raise ValueError(
                "overlay transitions cannot overlap unless explicitly allowed: "
                f"{current.overlay_id} ({current.start_seconds:.3f}-{current.end_seconds:.3f}) vs "
                f"{following.overlay_id} ({following.start_seconds:.3f}-{following.end_seconds:.3f})"
            )

    def as_overlay_timeline(self) -> list[dict[str, Any]]:
        return [
            {
                "overlay_id": item.overlay_id,
                "start_seconds": item.start_seconds,
                "end_seconds": item.end_seconds,
                "text": item.text,
                "overlay_role": item.role,
                "emphasis": item.role,
                "track": item.track,
                "allow_overlap": item.allow_overlap,
            }
            for item in self.overlays
        ]

    def as_scene_plan(self) -> dict[str, Any]:
        return {
            "schema_version": "canonical_timeline_projection_v1",
            "duration_seconds": self.duration_seconds,
            "scenes": [
                {
                    "scene_id": item.scene_id,
                    "purpose": item.purpose,
                    "start_seconds": item.start_seconds,
                    "end_seconds": item.end_seconds,
                }
                for item in self.scenes
            ],
        }


def build_canonical_timeline(
    *,
    timeline_id: str,
    duration_seconds: float,
    source_uri: str,
    scene_plan: Mapping[str, Any],
    overlay_timeline: Sequence[Mapping[str, Any]] | None,
    spoken_script: Sequence[Mapping[str, Any]] | None,
    cover_frame_timestamp_seconds: float = 0.0,
) -> CanonicalTimeline:
    source_clip_id = "source-001"
    scenes: list[TimelineScene] = []
    segments: list[TimelineEditSegment] = []
    raw_scenes = scene_plan.get("scenes")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        raise ValueError("scene_plan.scenes must be a non-empty list")
    for index, raw in enumerate(raw_scenes, start=1):
        if not isinstance(raw, Mapping):
            continue
        start = float(raw.get("start_seconds") or 0.0)
        end = float(raw.get("end_seconds") or 0.0)
        if end <= start:
            raise ValueError(f"scene {index} must have positive duration")
        scene_id = str(raw.get("scene_id") or f"scene-{index:03d}")
        purpose = str(raw.get("purpose") or "scene")
        scenes.append(
            TimelineScene(
                scene_id=scene_id,
                start_seconds=start,
                end_seconds=end,
                source_clip_id=source_clip_id,
                source_start_seconds=start,
                source_end_seconds=end,
                purpose=purpose,
            )
        )
        segments.append(
            TimelineEditSegment(
                segment_id=f"segment-{index:03d}",
                timeline_start_seconds=start,
                timeline_end_seconds=end,
                source_clip_id=source_clip_id,
                source_start_seconds=start,
                source_end_seconds=end,
                scene_id=scene_id,
                purpose=purpose,
            )
        )

    overlays: list[TimelineOverlay] = []
    scene_by_id: dict[str, TimelineScene] = {item.scene_id: item for item in scenes}
    for index, raw in enumerate(overlay_timeline or (), start=1):
        scene_ref = str(raw.get("scene_id") or "").strip()
        scene: TimelineScene | None = None
        if scene_ref:
            scene = scene_by_id.get(scene_ref)
            if scene is None:
                raise ValueError(f"overlay {index} references unknown scene_id={scene_ref!r}")
        elif index <= len(scenes):
            scene = scenes[index - 1]
        else:
            scene = scenes[-1]
        start = float(scene.start_seconds)
        end = float(scene.end_seconds)
        role = str(raw.get("emphasis") or raw.get("overlay_role") or "other")
        overlays.append(
            TimelineOverlay(
                overlay_id=str(raw.get("overlay_id") or f"overlay-{index:03d}"),
                start_seconds=start,
                end_seconds=end,
                text=str(raw.get("text") or raw.get("overlay_text") or "").strip(),
                role=role if role else "other",
                allow_overlap=bool(raw.get("allow_overlap", False)),
            )
        )

    master_fade_in, master_fade_out = _deterministic_audio_fades(float(duration_seconds))
    audio_tracks: list[TimelineAudioTrack] = [
        TimelineAudioTrack(
            track_id="audio-master",
            role="master",
            start_seconds=0.0,
            end_seconds=float(duration_seconds),
            fade_in_seconds=master_fade_in,
            fade_out_seconds=master_fade_out,
        )
    ]
    if isinstance(spoken_script, Sequence):
        for index, beat in enumerate(spoken_script, start=1):
            if not isinstance(beat, Mapping):
                continue
            narration_start = _read_float(beat, "start_seconds", "start")
            narration_end = _read_float(beat, "end_seconds", "end")
            if narration_start is None or narration_end is None:
                continue
            fade_in, fade_out = _deterministic_audio_fades(
                float(narration_end) - float(narration_start)
            )
            audio_tracks.append(
                TimelineAudioTrack(
                    track_id=f"narration-{index:03d}",
                    role="narration",
                    start_seconds=narration_start,
                    end_seconds=narration_end,
                    fade_in_seconds=fade_in,
                    fade_out_seconds=fade_out,
                )
            )

    timeline = CanonicalTimeline(
        timeline_id=timeline_id,
        duration_seconds=float(duration_seconds),
        cover_frame_timestamp_seconds=float(cover_frame_timestamp_seconds),
        source_clips=[
            TimelineSourceClip(
                clip_id=source_clip_id,
                duration_seconds=float(duration_seconds),
                uri=source_uri,
            )
        ],
        scenes=scenes,
        edit_segments=segments,
        overlays=overlays,
        audio_tracks=audio_tracks,
    )
    return timeline


def _read_float(payload: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value: object = payload.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, bool):
            return None
        if not isinstance(value, int | float | str | bytes | bytearray):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def _require_contiguous_spans(
    label: str,
    spans: Sequence[tuple[float, float]],
    *,
    expected_duration: float,
) -> None:
    if not spans:
        raise ValueError(f"{label} must not be empty")
    ordered = sorted(spans, key=lambda it: it[0])
    cursor = 0.0
    tol = 1e-6
    for index, (start, end) in enumerate(ordered):
        if start < cursor - tol:
            raise ValueError(f"{label}[{index}] overlaps previous span")
        if abs(start - cursor) > tol:
            raise ValueError(f"{label}[{index}] is non-contiguous (expected {cursor}, got {start})")
        if end <= start:
            raise ValueError(f"{label}[{index}] has invalid span")
        cursor = end
    if abs(cursor - expected_duration) > 1e-5:
        raise ValueError(
            f"{label} terminal end ({cursor}) does not match duration_seconds ({expected_duration})"
        )


def _deterministic_audio_fades(track_span_seconds: float) -> tuple[float, float]:
    span = max(float(track_span_seconds), 0.0)
    if span <= 0.0:
        return (0.0, 0.0)
    fade_in = min(DEFAULT_AUDIO_FADE_IN_SECONDS, span / 2.0)
    fade_out = min(DEFAULT_AUDIO_FADE_OUT_SECONDS, span / 2.0)
    if fade_in + fade_out > span:
        ratio = span / (fade_in + fade_out)
        fade_in *= ratio
        fade_out *= ratio
    return (round(fade_in, 3), round(fade_out, 3))


__all__ = [
    "CanonicalTimeline",
    "TimelineAudioTrack",
    "TimelineEditSegment",
    "TimelineOverlay",
    "TimelineScene",
    "TimelineSourceClip",
    "DEFAULT_AUDIO_FADE_IN_SECONDS",
    "DEFAULT_AUDIO_FADE_OUT_SECONDS",
    "build_canonical_timeline",
]
