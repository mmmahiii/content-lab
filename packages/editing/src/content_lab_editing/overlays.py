"""Overlay timeline helpers for deterministic FFmpeg drawtext rendering."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal, TypeAlias, cast

from content_lab_editing.instructions import EditInstruction, EditOperation, EditPlan
from content_lab_editing.types import RenderedOverlayManifest, RenderedOverlayManifestEntry

DEFAULT_OVERLAY_MARGIN_X = 80
DEFAULT_OVERLAY_MARGIN_Y = 160
DEFAULT_OVERLAY_FONT_SIZE = 64
DEFAULT_OVERLAY_FONT_COLOR = "white"
DEFAULT_OVERLAY_BORDER_COLOR = "black"
DEFAULT_OVERLAY_BORDER_WIDTH = 4
DEFAULT_OVERLAY_BOX_COLOR = "black@0.35"
DEFAULT_OVERLAY_BOX_BORDER_WIDTH = 24
DEFAULT_OVERLAY_LINE_SPACING = 12

HorizontalAlign: TypeAlias = Literal["left", "center", "right"]
VerticalAlign: TypeAlias = Literal["top", "center", "bottom"]
OverlayPosition: TypeAlias = str | int | float
OverlayInput: TypeAlias = "TextOverlay | EditInstruction | Mapping[str, object]"
OverlayTimeline: TypeAlias = Sequence[OverlayInput] | EditPlan

TimelineContainer: TypeAlias = Literal["sequence", "edit_plan"]
OverlaySourceKind: TypeAlias = Literal["mapping", "text_overlay", "edit_instruction_params"]


@dataclass(frozen=True, slots=True)
class OverlayRenderDiagnostic:
    """One overlay row: what was interpreted for FFmpeg drawtext and where it came from."""

    index: int
    source_path: str
    timeline_container: TimelineContainer
    source_kind: OverlaySourceKind
    render_authority: Literal["overlay_timeline_argument"]
    role: str | None
    style: dict[str, Any]
    font_size: int
    max_width_px: float | None
    x_expression: str
    y_expression: str
    start_seconds: float
    end_seconds: float | None
    payload_text_raw: str | None
    final_render_text: str
    truncation_before_render: Literal["none", "whitespace_strip", "overlay_parser_changed_text"]
    truncation_during_ffmpeg: Literal["none"]
    drawtext_filter: str


@dataclass(frozen=True, slots=True)
class TextOverlay:
    """Typed text overlay with safe defaults for vertical video rendering."""

    text: str
    start_seconds: float = 0.0
    end_seconds: float | None = None
    font_size: int = DEFAULT_OVERLAY_FONT_SIZE
    font_color: str = DEFAULT_OVERLAY_FONT_COLOR
    border_color: str = DEFAULT_OVERLAY_BORDER_COLOR
    border_width: int = DEFAULT_OVERLAY_BORDER_WIDTH
    box: bool = True
    box_color: str = DEFAULT_OVERLAY_BOX_COLOR
    box_border_width: int = DEFAULT_OVERLAY_BOX_BORDER_WIDTH
    line_spacing: int = DEFAULT_OVERLAY_LINE_SPACING
    x: OverlayPosition | None = None
    y: OverlayPosition | None = None
    horizontal_align: HorizontalAlign = "center"
    vertical_align: VerticalAlign = "bottom"
    margin_x: int = DEFAULT_OVERLAY_MARGIN_X
    margin_y: int = DEFAULT_OVERLAY_MARGIN_Y
    font_file: str | None = None

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, object],
        *,
        clip_duration_seconds: float | None = None,
    ) -> TextOverlay:
        """Build an overlay from instruction-style params."""

        overlay = cls(
            text=_require_text(payload),
            start_seconds=_read_optional_float(payload, "start_seconds", "start") or 0.0,
            end_seconds=_read_optional_float(payload, "end_seconds", "end"),
            font_size=_read_optional_int(
                payload,
                "font_size",
                default=DEFAULT_OVERLAY_FONT_SIZE,
            ),
            font_color=_read_str(
                payload,
                "font_color",
                default=DEFAULT_OVERLAY_FONT_COLOR,
            ),
            border_color=_read_str(
                payload,
                "border_color",
                default=DEFAULT_OVERLAY_BORDER_COLOR,
            ),
            border_width=_read_optional_int(
                payload,
                "border_width",
                default=DEFAULT_OVERLAY_BORDER_WIDTH,
            ),
            box=_read_optional_bool(payload, "box", default=True),
            box_color=_read_str(
                payload,
                "box_color",
                default=DEFAULT_OVERLAY_BOX_COLOR,
            ),
            box_border_width=_read_optional_int(
                payload,
                "box_border_width",
                default=DEFAULT_OVERLAY_BOX_BORDER_WIDTH,
            ),
            line_spacing=_read_optional_int(
                payload,
                "line_spacing",
                default=DEFAULT_OVERLAY_LINE_SPACING,
            ),
            x=_read_optional_position(payload, "x"),
            y=_read_optional_position(payload, "y"),
            horizontal_align=_read_optional_horizontal_align(payload, default="center"),
            vertical_align=_read_optional_vertical_align(payload, default="bottom"),
            margin_x=_read_optional_int(
                payload,
                "margin_x",
                default=DEFAULT_OVERLAY_MARGIN_X,
            ),
            margin_y=_read_optional_int(
                payload,
                "margin_y",
                default=DEFAULT_OVERLAY_MARGIN_Y,
            ),
            font_file=_read_optional_str(payload, "font_file", default=None),
        )

        duration_seconds = _read_optional_float(payload, "duration_seconds", "duration")
        if overlay.end_seconds is None and duration_seconds is not None:
            overlay = replace(overlay, end_seconds=overlay.start_seconds + duration_seconds)

        return overlay.normalize(clip_duration_seconds=clip_duration_seconds)

    def normalize(self, *, clip_duration_seconds: float | None = None) -> TextOverlay:
        """Clamp overlay timing into a deterministic, renderable window."""

        start_seconds = max(self.start_seconds, 0.0)
        end_seconds = self.end_seconds

        if clip_duration_seconds is not None:
            clip_duration_seconds = max(clip_duration_seconds, 0.0)
            start_seconds = min(start_seconds, clip_duration_seconds)
            if end_seconds is None:
                end_seconds = clip_duration_seconds
            else:
                end_seconds = min(max(end_seconds, 0.0), clip_duration_seconds)

        if end_seconds is not None and end_seconds <= start_seconds:
            raise ValueError(
                "Overlay end time must be greater than the start time after normalization"
            )

        return replace(self, start_seconds=start_seconds, end_seconds=end_seconds)

    def drawtext_filter(self) -> str:
        """Render this overlay as a single FFmpeg drawtext filter clause."""

        options = [
            f"text='{_escape_drawtext_text(self.text)}'",
            f"x={self._x_expression()}",
            f"y={self._y_expression()}",
            f"fontsize={self.font_size}",
            f"fontcolor={self.font_color}",
            f"line_spacing={self.line_spacing}",
            f"bordercolor={self.border_color}",
            f"borderw={self.border_width}",
            "fix_bounds=1",
            f"enable='{self._enable_expression()}'",
        ]

        if self.box:
            options.extend(
                [
                    "box=1",
                    f"boxcolor={self.box_color}",
                    f"boxborderw={self.box_border_width}",
                ]
            )

        if self.font_file is not None:
            options.append(f"fontfile='{_escape_filter_value(self.font_file)}'")

        return "drawtext=" + ":".join(options)

    def _x_expression(self) -> str:
        if self.x is not None:
            return _format_position(self.x)
        if self.horizontal_align == "left":
            return str(self.margin_x)
        if self.horizontal_align == "right":
            return f"w-text_w-{self.margin_x}"
        return "(w-text_w)/2"

    def _y_expression(self) -> str:
        if self.y is not None:
            return _format_position(self.y)
        if self.vertical_align == "top":
            return str(self.margin_y)
        if self.vertical_align == "center":
            return "(h-text_h)/2"
        return f"h-text_h-{self.margin_y}"

    def _enable_expression(self) -> str:
        if self.end_seconds is None:
            return f"gte(t,{_format_seconds(self.start_seconds)})"
        return (
            "between("
            f"t,{_format_seconds(self.start_seconds)},{_format_seconds(self.end_seconds)}"
            ")"
        )


def normalize_overlay_timeline(
    timeline: OverlayTimeline | None,
    *,
    clip_duration_seconds: float | None = None,
) -> tuple[TextOverlay, ...]:
    """Normalize an overlay timeline from edit-plan or raw params inputs."""

    if timeline is None:
        return ()

    items: Sequence[OverlayInput] = (
        timeline.instructions if isinstance(timeline, EditPlan) else timeline
    )

    normalized: list[TextOverlay] = []
    for item in items:
        if isinstance(item, TextOverlay):
            normalized.append(item.normalize(clip_duration_seconds=clip_duration_seconds))
            continue
        if isinstance(item, EditInstruction):
            if item.operation != EditOperation.OVERLAY_TEXT:
                continue
            normalized.append(
                TextOverlay.from_mapping(item.params, clip_duration_seconds=clip_duration_seconds)
            )
            continue
        normalized.append(
            TextOverlay.from_mapping(item, clip_duration_seconds=clip_duration_seconds)
        )

    normalized.sort(
        key=lambda overlay: (overlay.start_seconds, overlay.end_seconds or float("inf"))
    )
    return tuple(normalized)


def build_overlay_render_diagnostics(
    timeline: OverlayTimeline | None,
    *,
    clip_duration_seconds: float | None = None,
    sequence_source_prefix: str = "script.overlay_timeline",
) -> tuple[OverlayRenderDiagnostic, ...]:
    """Describe each overlay FFmpeg will render: provenance, timing, and final drawtext text."""

    if timeline is None:
        return ()

    items: Sequence[OverlayInput] = (
        timeline.instructions if isinstance(timeline, EditPlan) else timeline
    )

    work: list[
        tuple[
            str,
            TimelineContainer,
            OverlaySourceKind,
            str | None,
            TextOverlay,
            Mapping[str, object] | None,
        ]
    ] = []

    if isinstance(timeline, EditPlan):
        for idx, instruction in enumerate(timeline.instructions):
            if instruction.operation != EditOperation.OVERLAY_TEXT:
                continue
            payload = instruction.params
            raw_text = _peek_raw_text_field(payload)
            overlay = TextOverlay.from_mapping(
                payload,
                clip_duration_seconds=clip_duration_seconds,
            )
            source_path = f"edit_plan.instructions[{idx}]"
            work.append(
                (
                    source_path,
                    "edit_plan",
                    "edit_instruction_params",
                    raw_text,
                    overlay,
                    payload,
                )
            )
    else:
        for idx, item in enumerate(items):
            if isinstance(item, TextOverlay):
                normalized_overlay = item.normalize(clip_duration_seconds=clip_duration_seconds)
                source_path = f"{sequence_source_prefix}[{idx}]"
                work.append(
                    (
                        source_path,
                        "sequence",
                        "text_overlay",
                        item.text,
                        normalized_overlay,
                        None,
                    )
                )
                continue
            if isinstance(item, EditInstruction):
                if item.operation != EditOperation.OVERLAY_TEXT:
                    continue
                payload = item.params
                raw_text = _peek_raw_text_field(payload)
                overlay = TextOverlay.from_mapping(
                    payload,
                    clip_duration_seconds=clip_duration_seconds,
                )
                source_path = f"{sequence_source_prefix}[{idx}]"
                work.append(
                    (
                        source_path,
                        "sequence",
                        "edit_instruction_params",
                        raw_text,
                        overlay,
                        payload,
                    )
                )
                continue
            if isinstance(item, Mapping):
                raw_text = _peek_raw_text_field(item)
                overlay = TextOverlay.from_mapping(
                    item,
                    clip_duration_seconds=clip_duration_seconds,
                )
                source_path = f"{sequence_source_prefix}[{idx}]"
                work.append(
                    (source_path, "sequence", "mapping", raw_text, overlay, item)
                )
                continue
            raise TypeError(f"Unsupported overlay timeline entry type: {type(item)!r}")

    work.sort(
        key=lambda row: (row[4].start_seconds, row[4].end_seconds or float("inf")),
    )

    diagnostics: list[OverlayRenderDiagnostic] = []
    for idx, (source_path, container, source_kind, payload_raw, overlay, payload_mapping) in enumerate(
        work
    ):
        truncation_before, truncation_ffmpeg = _overlay_truncation_stages(payload_raw, overlay.text)
        diagnostics.append(
            OverlayRenderDiagnostic(
                index=idx,
                source_path=source_path,
                timeline_container=container,
                source_kind=source_kind,
                render_authority="overlay_timeline_argument",
                role=_role_from_payload(payload_mapping),
                style=_overlay_style_snapshot(overlay),
                font_size=overlay.font_size,
                max_width_px=None,
                x_expression=overlay._x_expression(),
                y_expression=overlay._y_expression(),
                start_seconds=overlay.start_seconds,
                end_seconds=overlay.end_seconds,
                payload_text_raw=payload_raw,
                final_render_text=overlay.text,
                truncation_before_render=truncation_before,
                truncation_during_ffmpeg=truncation_ffmpeg,
                drawtext_filter=overlay.drawtext_filter(),
            )
        )

    return tuple(diagnostics)


def scene_plan_overlay_text_references(
    scene_plan: Mapping[str, object] | None,
) -> tuple[dict[str, Any], ...]:
    """Surface scene_plan overlay_text fields for QA; they do not drive FFmpeg in this package."""

    if scene_plan is None:
        return ()

    scenes = scene_plan.get("scenes")
    if not isinstance(scenes, list):
        return ()

    references: list[dict[str, Any]] = []
    for idx, scene in enumerate(scenes):
        if not isinstance(scene, Mapping):
            continue
        raw_text = scene.get("overlay_text")
        if raw_text is None:
            continue
        text = str(raw_text).strip()
        if not text:
            continue
        references.append(
            {
                "scene_index": idx,
                "scene_id": scene.get("scene_id"),
                "purpose": scene.get("purpose"),
                "overlay_role": scene.get("overlay_role"),
                "overlay_text": text,
                "used_for_video_render": False,
                "note": (
                    "scene_plan overlay_text is informational unless mirrored into "
                    "script.overlay_timeline; FFmpeg uses overlay_timeline_argument only."
                ),
            }
        )

    return tuple(references)


def _peek_raw_text_field(payload: Mapping[str, object]) -> str | None:
    value = payload.get("text")
    if isinstance(value, str):
        return value
    return None


def _role_from_payload(payload: Mapping[str, object] | None) -> str | None:
    if payload is None:
        return None
    for key in ("emphasis", "role", "overlay_role"):
        value = payload.get(key)
        if value is None:
            continue
        label = str(value).strip()
        if label:
            return label
    return None


def _overlay_style_snapshot(overlay: TextOverlay) -> dict[str, Any]:
    return {
        "box": overlay.box,
        "box_color": overlay.box_color,
        "font_color": overlay.font_color,
        "horizontal_align": overlay.horizontal_align,
        "vertical_align": overlay.vertical_align,
        "border_width": overlay.border_width,
        "line_spacing": overlay.line_spacing,
    }


def _overlay_truncation_stages(
    payload_raw: str | None,
    final_text: str,
) -> tuple[
    Literal["none", "whitespace_strip", "overlay_parser_changed_text"],
    Literal["none"],
]:
    if payload_raw is None:
        return ("none", "none")
    if payload_raw == final_text:
        return ("none", "none")
    if payload_raw.strip() == final_text:
        return ("whitespace_strip", "none")
    return ("overlay_parser_changed_text", "none")


def build_drawtext_filters(
    timeline: OverlayTimeline | None,
    *,
    clip_duration_seconds: float | None = None,
) -> tuple[str, ...]:
    """Convert a timeline to FFmpeg drawtext clauses."""

    overlays = normalize_overlay_timeline(
        timeline,
        clip_duration_seconds=clip_duration_seconds,
    )
    return tuple(overlay.drawtext_filter() for overlay in overlays)


def build_overlay_video_filter(
    *,
    base_filter: str,
    timeline: OverlayTimeline | None,
    clip_duration_seconds: float | None = None,
) -> str:
    """Append overlay drawtext filters to an existing video filter chain."""

    filters = build_drawtext_filters(
        timeline,
        clip_duration_seconds=clip_duration_seconds,
    )
    if not filters:
        return base_filter
    return ",".join((base_filter, *filters))


def _require_text(payload: Mapping[str, object]) -> str:
    text = _read_optional_str(payload, "text", default=None)
    if text is None or not text.strip():
        raise ValueError("Overlay text must not be blank")
    return text


def _read_optional_float(payload: Mapping[str, object], *keys: str) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, bool):
            break
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                continue
            try:
                return float(stripped)
            except ValueError as exc:
                raise ValueError(f"Overlay field '{key}' must be numeric") from exc
        raise ValueError(f"Overlay field '{key}' must be numeric")
    return None


def _read_optional_int(payload: Mapping[str, object], key: str, *, default: int) -> int:
    value = payload.get(key)
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        raise ValueError(f"Overlay field '{key}' must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return int(float(stripped))
        except ValueError as exc:
            raise ValueError(f"Overlay field '{key}' must be an integer") from exc
    raise ValueError(f"Overlay field '{key}' must be an integer")


def _read_optional_bool(payload: Mapping[str, object], key: str, *, default: bool) -> bool:
    value = payload.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            return default
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"Overlay field '{key}' must be boolean-like")


def _read_optional_str(
    payload: Mapping[str, object],
    key: str,
    *,
    default: str | None,
) -> str | None:
    value = payload.get(key)
    if value is None:
        return default
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else default
    return str(value)


def _read_str(payload: Mapping[str, object], key: str, *, default: str) -> str:
    value = _read_optional_str(payload, key, default=default)
    if value is None:
        return default
    return value


def _read_optional_position(payload: Mapping[str, object], key: str) -> OverlayPosition | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"Overlay field '{key}' must be a number or FFmpeg expression")
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        return stripped
    raise ValueError(f"Overlay field '{key}' must be a number or FFmpeg expression")


def _read_optional_horizontal_align(
    payload: Mapping[str, object],
    *,
    default: HorizontalAlign,
) -> HorizontalAlign:
    value = _read_str(payload, "horizontal_align", default=default)
    if value in {"left", "center", "right"}:
        return cast(HorizontalAlign, value)
    raise ValueError("Overlay field 'horizontal_align' must be left, center, or right")


def _read_optional_vertical_align(
    payload: Mapping[str, object],
    *,
    default: VerticalAlign,
) -> VerticalAlign:
    value = _read_str(payload, "vertical_align", default=default)
    if value in {"top", "center", "bottom"}:
        return cast(VerticalAlign, value)
    raise ValueError("Overlay field 'vertical_align' must be top, center, or bottom")


def _format_position(value: OverlayPosition) -> str:
    if isinstance(value, str):
        return value
    return f"{float(value):g}"


def _format_seconds(value: float) -> str:
    return f"{value:.3f}"


def _escape_filter_value(value: str) -> str:
    escaped = value.replace("\\", r"\\")
    escaped = escaped.replace("'", r"\'")
    escaped = escaped.replace(":", r"\:")
    escaped = escaped.replace(",", r"\,")
    escaped = escaped.replace("[", r"\[")
    escaped = escaped.replace("]", r"\]")
    return escaped


def _escape_drawtext_text(value: str) -> str:
    escaped = _escape_filter_value(value)
    escaped = escaped.replace("%", r"\%")
    return escaped.replace("\n", r"\n")


def build_overlay_render_report(
    *,
    timeline: OverlayTimeline | None,
    clip_duration_seconds: float | None = None,
    sequence_source_prefix: str = "script.overlay_timeline",
    scene_plan: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Aggregate FFmpeg-bound overlays plus scene_plan overlay_text references for QA traces."""

    diagnostics = build_overlay_render_diagnostics(
        timeline,
        clip_duration_seconds=clip_duration_seconds,
        sequence_source_prefix=sequence_source_prefix,
    )
    references = scene_plan_overlay_text_references(scene_plan)
    return {
        "render_authority": "overlay_timeline_argument_only",
        "scene_plan_overlay_text_drives_render": False,
        "ffmpeg_drawtext_truncation": "none_pipeline_has_no_text_max_width",
        "overlays": [asdict(entry) for entry in diagnostics],
        "scene_plan_overlay_text_references": list(references),
    }


def build_rendered_overlay_manifest(
    *,
    timeline: OverlayTimeline | None,
    clip_duration_seconds: float,
    frame_width_px: int,
    frame_height_px: int,
    sequence_source_prefix: str = "script.overlay_timeline",
) -> RenderedOverlayManifest:
    """Structured manifest of drawtext overlays for QA without inspecting decoded frames."""

    overlays_norm = normalize_overlay_timeline(
        timeline,
        clip_duration_seconds=clip_duration_seconds,
    )
    diagnostics = build_overlay_render_diagnostics(
        timeline,
        clip_duration_seconds=clip_duration_seconds,
        sequence_source_prefix=sequence_source_prefix,
    )

    if len(overlays_norm) != len(diagnostics):
        raise RuntimeError("overlay diagnostics drifted from normalized overlays")

    effective_windows = [
        _effective_visible_window(
            overlay.start_seconds,
            overlay.end_seconds,
            clip_duration_seconds,
        )
        for overlay in overlays_norm
    ]
    collision_labels = _collision_group_ids(effective_windows)

    entries: list[RenderedOverlayManifestEntry] = []
    for idx, (diag, overlay, effective, collision_group) in enumerate(
        zip(diagnostics, overlays_norm, effective_windows, collision_labels, strict=True)
    ):
        wrap_lines = _manifest_wrap_lines(diag.final_render_text)
        style = _manifest_style_snapshot(overlay)
        safe_area = _manifest_safe_area(
            overlay=overlay,
            diagnostic=diag,
            frame_width_px=frame_width_px,
            frame_height_px=frame_height_px,
        )
        entries.append(
            RenderedOverlayManifestEntry(
                overlay_id=f"overlay-{idx:03d}",
                timeline_source_path=diag.source_path,
                source_text=diag.payload_text_raw,
                final_render_text=diag.final_render_text,
                start_seconds=diag.start_seconds,
                end_seconds=diag.end_seconds,
                effective_visible_start_seconds=effective[0],
                effective_visible_end_seconds=effective[1],
                role=diag.role,
                style=style,
                wrap_lines=wrap_lines,
                safe_area=safe_area,
                collision_group=collision_group,
            )
        )

    return RenderedOverlayManifest(
        schema_version="rendered_overlay_manifest_v1",
        frame_width_px=frame_width_px,
        frame_height_px=frame_height_px,
        clip_duration_seconds=float(clip_duration_seconds),
        overlays=tuple(entries),
    )


def _effective_visible_window(
    start_seconds: float,
    end_seconds: float | None,
    clip_duration_seconds: float,
) -> tuple[float, float]:
    clip_duration_seconds = max(float(clip_duration_seconds), 0.0)
    span_end = end_seconds if end_seconds is not None else clip_duration_seconds
    lo = max(float(start_seconds), 0.0)
    hi = min(float(span_end), clip_duration_seconds)
    if hi < lo:
        pivot = min(max(float(start_seconds), 0.0), clip_duration_seconds)
        return (pivot, pivot)
    return (lo, hi)


def _collision_group_ids(intervals: list[tuple[float, float]]) -> list[int]:
    """Assign overlapping effective-visible intervals to shared collision groups."""

    count = len(intervals)
    if count == 0:
        return []

    parent = list(range(count))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for i in range(count):
        for j in range(i + 1, count):
            a_lo, a_hi = intervals[i]
            b_lo, b_hi = intervals[j]
            if a_lo < b_hi and b_lo < a_hi:
                union(i, j)

    root_labels: dict[int, int] = {}
    labels: list[int] = []
    next_label = 0
    for index in range(count):
        root = find(index)
        if root not in root_labels:
            root_labels[root] = next_label
            next_label += 1
        labels.append(root_labels[root])

    return labels


def _manifest_wrap_lines(text: str) -> tuple[str, ...]:
    lines = tuple(line for line in text.splitlines())
    return lines if lines else ("",)


def _manifest_style_snapshot(overlay: TextOverlay) -> dict[str, Any]:
    base = _overlay_style_snapshot(overlay)
    merged = dict(base)
    merged.update(
        {
            "font_size": overlay.font_size,
            "margin_x_px": overlay.margin_x,
            "margin_y_px": overlay.margin_y,
        }
    )
    return merged


def _manifest_safe_area(
    *,
    overlay: TextOverlay,
    diagnostic: OverlayRenderDiagnostic,
    frame_width_px: int,
    frame_height_px: int,
) -> dict[str, Any]:
    return {
        "frame_width_px": frame_width_px,
        "frame_height_px": frame_height_px,
        "margin_x_px": overlay.margin_x,
        "margin_y_px": overlay.margin_y,
        "horizontal_align": overlay.horizontal_align,
        "vertical_align": overlay.vertical_align,
        "x_expression": diagnostic.x_expression,
        "y_expression": diagnostic.y_expression,
        "placement_model": "ffmpeg_drawtext",
        "note": (
            "Bounding box is not rasterized; FFmpeg positions glyphs using expressions "
            "that reference w, h, text_w, and text_h after scaling/padding to the frame."
        ),
    }


__all__ = [
    "DEFAULT_OVERLAY_BORDER_COLOR",
    "DEFAULT_OVERLAY_BORDER_WIDTH",
    "DEFAULT_OVERLAY_BOX_BORDER_WIDTH",
    "DEFAULT_OVERLAY_BOX_COLOR",
    "DEFAULT_OVERLAY_FONT_COLOR",
    "DEFAULT_OVERLAY_FONT_SIZE",
    "DEFAULT_OVERLAY_LINE_SPACING",
    "DEFAULT_OVERLAY_MARGIN_X",
    "DEFAULT_OVERLAY_MARGIN_Y",
    "OverlayInput",
    "OverlayRenderDiagnostic",
    "OverlayTimeline",
    "TextOverlay",
    "build_drawtext_filters",
    "build_overlay_render_diagnostics",
    "build_overlay_render_report",
    "build_rendered_overlay_manifest",
    "build_overlay_video_filter",
    "normalize_overlay_timeline",
    "scene_plan_overlay_text_references",
]
