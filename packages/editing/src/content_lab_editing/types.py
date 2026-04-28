"""Typed payloads for editing outputs (manifests, traces)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, cast


@dataclass(frozen=True, slots=True)
class RenderedOverlayManifestEntry:
    """One overlay the editor attempted to burn in via FFmpeg drawtext."""

    overlay_id: str
    timeline_source_path: str
    source_text: str | None
    final_render_text: str
    start_seconds: float
    end_seconds: float | None
    effective_visible_start_seconds: float
    effective_visible_end_seconds: float
    role: str | None
    style: dict[str, Any]
    wrap_lines: tuple[str, ...]
    safe_area: dict[str, Any]
    collision_group: int


@dataclass(frozen=True, slots=True)
class RenderedOverlayManifest:
    """Machine-readable summary of text overlays for QA without inspecting pixels."""

    schema_version: Literal["rendered_overlay_manifest_v1"]
    frame_width_px: int
    frame_height_px: int
    clip_duration_seconds: float
    overlays: tuple[RenderedOverlayManifestEntry, ...]

    def as_json_dict(self) -> dict[str, Any]:
        """JSON-serialize tuples as lists."""

        return cast(dict[str, Any], _as_json_safe(asdict(self)))


def _as_json_safe(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_as_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_as_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _as_json_safe(item) for key, item in value.items()}
    return value


__all__ = ["RenderedOverlayManifest", "RenderedOverlayManifestEntry"]
