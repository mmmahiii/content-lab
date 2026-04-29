"""Overlay timeline helpers for deterministic FFmpeg drawtext rendering."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal, NamedTuple, TypeAlias, cast

from content_lab_editing.instructions import EditInstruction, EditOperation, EditPlan

DEFAULT_OVERLAY_MARGIN_X = 80
DEFAULT_OVERLAY_MARGIN_Y = 160
DEFAULT_OVERLAY_FONT_SIZE = 64
DEFAULT_OVERLAY_FONT_COLOR = "white"
DEFAULT_OVERLAY_BORDER_COLOR = "black"
DEFAULT_OVERLAY_BORDER_WIDTH = 4
DEFAULT_OVERLAY_BOX_COLOR = "black@0.35"
DEFAULT_OVERLAY_BOX_BORDER_WIDTH = 24
DEFAULT_OVERLAY_LINE_SPACING = 12
DEFAULT_OVERLAY_HANDOFF_GAP_SECONDS = 0.0

HorizontalAlign: TypeAlias = Literal["left", "center", "right"]
VerticalAlign: TypeAlias = Literal["top", "center", "bottom"]
OverlayPosition: TypeAlias = str | int | float
OverlayInput: TypeAlias = "TextOverlay | EditInstruction | Mapping[str, object]"
OverlayTimeline: TypeAlias = Sequence[OverlayInput] | EditPlan


class OverlayTimelineSlot(NamedTuple):
    """One overlay cue after timing normalization and fade merge, before primary-track trim."""

    source_index: int
    stable_id: str
    overlay: TextOverlay


@dataclass(frozen=True, slots=True)
class OverlayTransitionSettings:
    """Defaults for text overlay fades and handoff behavior."""

    enter_duration_ms: float = 0.0
    exit_duration_ms: float = 0.0
    handoff_gap_ms: float = 0.0
    allow_crossfade_overlap: bool = False

    def __post_init__(self) -> None:
        for name, value in (
            ("enter_duration_ms", self.enter_duration_ms),
            ("exit_duration_ms", self.exit_duration_ms),
            ("handoff_gap_ms", self.handoff_gap_ms),
        ):
            if value < 0:
                raise ValueError(f"{name} must be non-negative")


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
    enter_duration_ms: float | None = None
    exit_duration_ms: float | None = None
    overlay_id: str | None = None

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
            enter_duration_ms=_read_optional_float_ms(payload, "enter_duration_ms"),
            exit_duration_ms=_read_optional_float_ms(payload, "exit_duration_ms"),
            overlay_id=_read_overlay_id(payload),
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

        enter_ms, exit_ms = _resolved_fade_milliseconds(self)
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
        if enter_ms > 0.0 or exit_ms > 0.0:
            if self.end_seconds is None:
                msg = "Faded overlays require a finite end_seconds for alpha timing"
                raise ValueError(msg)
            alpha_expr = _alpha_fade_expression(
                self.start_seconds,
                self.end_seconds,
                enter_ms,
                exit_ms,
            )
            options.append(f"alpha='{alpha_expr}'")

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
        """Half-open [start, end) window so adjacent cues never share an instant."""

        if self.end_seconds is None:
            return f"gte(t,{_format_seconds(self.start_seconds)})"
        return (
            f"gte(t,{_format_seconds(self.start_seconds)})"
            f"*lt(t,{_format_seconds(self.end_seconds)})"
        )


def _read_optional_float_ms(
    payload: Mapping[str, object],
    key: str,
) -> float | None:
    value = _read_optional_float(payload, key)
    if value is None:
        return None
    return float(value)


def _resolved_fade_milliseconds(overlay: TextOverlay) -> tuple[float, float]:
    enter = 0.0 if overlay.enter_duration_ms is None else overlay.enter_duration_ms
    exit_ = 0.0 if overlay.exit_duration_ms is None else overlay.exit_duration_ms
    return enter, exit_


def _clamp_fade_milliseconds(
    span_seconds: float,
    enter_ms: float,
    exit_ms: float,
) -> tuple[float, float]:
    if span_seconds <= 0:
        return 0.0, 0.0
    max_total_ms = span_seconds * 1000.0
    enter_ms = max(enter_ms, 0.0)
    exit_ms = max(exit_ms, 0.0)
    total = enter_ms + exit_ms
    if total <= max_total_ms:
        return enter_ms, exit_ms
    if total <= 0:
        return 0.0, 0.0
    scale = max_total_ms / total
    return enter_ms * scale, exit_ms * scale


def _merge_transition_into_overlay(
    overlay: TextOverlay,
    settings: OverlayTransitionSettings | None,
) -> TextOverlay:
    if settings is None:
        enter = max(_resolved_fade_milliseconds(overlay)[0], 0.0)
        exit_ = max(_resolved_fade_milliseconds(overlay)[1], 0.0)
    else:
        enter = max(
            overlay.enter_duration_ms
            if overlay.enter_duration_ms is not None
            else settings.enter_duration_ms,
            0.0,
        )
        exit_ = max(
            overlay.exit_duration_ms
            if overlay.exit_duration_ms is not None
            else settings.exit_duration_ms,
            0.0,
        )

    if overlay.end_seconds is None:
        return replace(overlay, enter_duration_ms=enter, exit_duration_ms=exit_)

    span = overlay.end_seconds - overlay.start_seconds
    enter_ms, exit_ms = _clamp_fade_milliseconds(span, enter, exit_)
    return replace(overlay, enter_duration_ms=enter_ms, exit_duration_ms=exit_ms)


def _alpha_fade_expression(
    start_seconds: float,
    end_seconds: float,
    enter_ms: float,
    exit_ms: float,
) -> str:
    enter_s = enter_ms / 1000.0
    exit_s = exit_ms / 1000.0
    s_s = _format_seconds(start_seconds)
    e_s = _format_seconds(end_seconds)
    eps = "0.000010"
    if enter_s <= 0.0:
        fade_in = f"if(gte(t,{s_s}),1,0)"
    else:
        e_in = _format_seconds(enter_s)
        fade_in = f"min(max((t-{s_s})/max({e_in},{eps}),0),1)"
    if exit_s <= 0.0:
        fade_out = "1"
    else:
        x_out = _format_seconds(exit_s)
        fade_out = f"min(max(({e_s}-t)/max({x_out},{eps}),0),1)"
    return f"{fade_in}*{fade_out}"


def _effective_overlay_end(
    overlay: TextOverlay,
    clip_duration_seconds: float | None,
) -> float:
    if overlay.end_seconds is not None:
        return float(overlay.end_seconds)
    if clip_duration_seconds is not None:
        return float(clip_duration_seconds)
    return float("inf")


def _apply_non_overlapping_primary_track(
    overlays: list[TextOverlay],
    *,
    clip_duration_seconds: float | None,
    handoff_gap_seconds: float,
) -> list[TextOverlay]:
    """Trim or delay overlays so only one primary cue is active at a time."""

    if handoff_gap_seconds < 0:
        msg = "handoff_gap_seconds must be non-negative"
        raise ValueError(msg)

    items = list(overlays)
    i = 0
    while i < len(items) - 1:
        cur = items[i]
        nxt = items[i + 1]
        cur_end = _effective_overlay_end(cur, clip_duration_seconds)
        boundary = nxt.start_seconds - handoff_gap_seconds
        if cur_end <= boundary:
            i += 1
            continue

        new_end = boundary
        if new_end > cur.start_seconds:
            items[i] = replace(cur, end_seconds=new_end)
            i += 1
            continue

        new_start = cur_end + handoff_gap_seconds
        nxt_end = nxt.end_seconds
        if nxt_end is not None and new_start >= nxt_end:
            items.pop(i + 1)
            continue

        items[i + 1] = replace(nxt, start_seconds=new_start)
        i += 1

    result: list[TextOverlay] = []
    for ov in items:
        end = ov.end_seconds
        if end is not None and end <= ov.start_seconds:
            continue
        result.append(ov)
    return result


def _collect_sorted_overlay_items(
    timeline: OverlayTimeline | None,
    *,
    clip_duration_seconds: float | None = None,
) -> list[tuple[int, TextOverlay]]:
    if timeline is None:
        return []

    items: Sequence[OverlayInput] = (
        timeline.instructions if isinstance(timeline, EditPlan) else timeline
    )

    normalized: list[tuple[int, TextOverlay]] = []
    for index, item in enumerate(items):
        if isinstance(item, TextOverlay):
            normalized.append((index, item.normalize(clip_duration_seconds=clip_duration_seconds)))
            continue
        if isinstance(item, EditInstruction):
            if item.operation != EditOperation.OVERLAY_TEXT:
                continue
            normalized.append(
                (
                    index,
                    TextOverlay.from_mapping(
                        item.params, clip_duration_seconds=clip_duration_seconds
                    ),
                )
            )
            continue
        normalized.append(
            (
                index,
                TextOverlay.from_mapping(item, clip_duration_seconds=clip_duration_seconds),
            )
        )

    normalized.sort(
        key=lambda indexed: (
            indexed[1].start_seconds,
            indexed[1].end_seconds or float("inf"),
            indexed[0],
        )
    )
    return normalized


def list_pre_handoff_overlay_slots(
    timeline: OverlayTimeline | None,
    *,
    clip_duration_seconds: float | None = None,
    transition: OverlayTransitionSettings | None = None,
) -> tuple[OverlayTimelineSlot, ...]:
    """Overlays in render order with merged fades, **before** primary-track trimming."""

    slots: list[OverlayTimelineSlot] = []
    for source_index, overlay in _collect_sorted_overlay_items(
        timeline,
        clip_duration_seconds=clip_duration_seconds,
    ):
        merged = _merge_transition_into_overlay(overlay, transition)
        label = (merged.overlay_id or "").strip()
        if not label:
            label = f"overlay[{source_index}]"
        slots.append(OverlayTimelineSlot(source_index, label, merged))
    return tuple(slots)


def normalize_overlay_timeline(
    timeline: OverlayTimeline | None,
    *,
    clip_duration_seconds: float | None = None,
    allow_overlay_stack: bool = False,
    handoff_gap_seconds: float = DEFAULT_OVERLAY_HANDOFF_GAP_SECONDS,
    transition: OverlayTransitionSettings | None = None,
) -> tuple[TextOverlay, ...]:
    """Normalize an overlay timeline from edit-plan or raw params inputs.

    By default only one primary overlay is visible at a time: overlaps are trimmed
    so the earlier cue ends where the next begins (optional gap). Adjacent
    boundaries use half-open intervals in FFmpeg enable expressions so shared
    endpoints do not render twice.

    Fade durations (``enter_duration_ms`` / ``exit_duration_ms``) are merged from
    per-cue fields and :class:`OverlayTransitionSettings`, clamped to each cue's
    final span, and rendered via FFmpeg drawtext ``alpha`` expressions. Unless
    ``allow_overlay_stack`` or ``transition.allow_crossfade_overlap`` is true,
    geometry is resolved first so fade ramps cannot crossfade two cues unless
    explicitly allowed.

    Set ``allow_overlay_stack=True`` to keep authored overlaps (still half-open
    at exact touch points).
    """

    if timeline is None:
        return ()

    normalized = _collect_sorted_overlay_items(
        timeline,
        clip_duration_seconds=clip_duration_seconds,
    )
    ordered = [overlay for _, overlay in normalized]

    effective_gap = handoff_gap_seconds
    if transition is not None:
        effective_gap = effective_gap + transition.handoff_gap_ms / 1000.0

    allow_overlap = allow_overlay_stack or (
        transition is not None and transition.allow_crossfade_overlap
    )
    if not allow_overlap:
        ordered = _apply_non_overlapping_primary_track(
            ordered,
            clip_duration_seconds=clip_duration_seconds,
            handoff_gap_seconds=effective_gap,
        )
    ordered = [_merge_transition_into_overlay(overlay, transition) for overlay in ordered]
    return tuple(ordered)


def build_drawtext_filters(
    timeline: OverlayTimeline | None,
    *,
    clip_duration_seconds: float | None = None,
    allow_overlay_stack: bool = False,
    handoff_gap_seconds: float = DEFAULT_OVERLAY_HANDOFF_GAP_SECONDS,
    transition: OverlayTransitionSettings | None = None,
) -> tuple[str, ...]:
    """Convert a timeline to FFmpeg drawtext clauses."""

    overlays = normalize_overlay_timeline(
        timeline,
        clip_duration_seconds=clip_duration_seconds,
        allow_overlay_stack=allow_overlay_stack,
        handoff_gap_seconds=handoff_gap_seconds,
        transition=transition,
    )
    return tuple(overlay.drawtext_filter() for overlay in overlays)


def build_overlay_video_filter(
    *,
    base_filter: str,
    timeline: OverlayTimeline | None,
    clip_duration_seconds: float | None = None,
    allow_overlay_stack: bool = False,
    handoff_gap_seconds: float = DEFAULT_OVERLAY_HANDOFF_GAP_SECONDS,
    transition: OverlayTransitionSettings | None = None,
) -> str:
    """Append overlay drawtext filters to an existing video filter chain."""

    filters = build_drawtext_filters(
        timeline,
        clip_duration_seconds=clip_duration_seconds,
        allow_overlay_stack=allow_overlay_stack,
        handoff_gap_seconds=handoff_gap_seconds,
        transition=transition,
    )
    if not filters:
        return base_filter
    return ",".join((base_filter, *filters))


def _read_overlay_id(payload: Mapping[str, object]) -> str | None:
    for key in ("overlay_id", "id", "cue_id"):
        value = _read_optional_str(payload, key, default=None)
        if value is None:
            continue
        stripped = value.strip()
        if stripped:
            return stripped
    return None


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


__all__ = [
    "DEFAULT_OVERLAY_BORDER_COLOR",
    "DEFAULT_OVERLAY_BORDER_WIDTH",
    "DEFAULT_OVERLAY_BOX_BORDER_WIDTH",
    "DEFAULT_OVERLAY_BOX_COLOR",
    "DEFAULT_OVERLAY_FONT_COLOR",
    "DEFAULT_OVERLAY_FONT_SIZE",
    "DEFAULT_OVERLAY_HANDOFF_GAP_SECONDS",
    "DEFAULT_OVERLAY_LINE_SPACING",
    "DEFAULT_OVERLAY_MARGIN_X",
    "DEFAULT_OVERLAY_MARGIN_Y",
    "OverlayInput",
    "OverlayTimeline",
    "OverlayTimelineSlot",
    "OverlayTransitionSettings",
    "TextOverlay",
    "build_drawtext_filters",
    "build_overlay_video_filter",
    "list_pre_handoff_overlay_slots",
    "normalize_overlay_timeline",
]
