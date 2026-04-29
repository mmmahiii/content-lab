"""Overlay timeline helpers for deterministic FFmpeg drawtext rendering."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal, TypeAlias, cast

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

HorizontalAlign: TypeAlias = Literal["left", "center", "right"]
VerticalAlign: TypeAlias = Literal["top", "center", "bottom"]
OverlayPosition: TypeAlias = str | int | float
OverlayInput: TypeAlias = "TextOverlay | EditInstruction | Mapping[str, object]"
OverlayTimeline: TypeAlias = Sequence[OverlayInput] | EditPlan


@dataclass(frozen=True, slots=True)
class TextOverlay:
    """Typed text overlay with safe defaults for vertical video rendering."""

    text: str
    start_seconds: float = 0.0
    end_seconds: float | None = None
    fade_in_seconds: float = 0.0
    fade_out_seconds: float = 0.0
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

        fade_in_raw = _read_optional_float(payload, "fade_in_seconds", "fade_in")
        fade_out_raw = _read_optional_float(payload, "fade_out_seconds", "fade_out")
        overlay = replace(
            overlay,
            fade_in_seconds=0.0 if fade_in_raw is None else max(0.0, float(fade_in_raw)),
            fade_out_seconds=0.0 if fade_out_raw is None else max(0.0, float(fade_out_raw)),
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

        alpha_expr = self._alpha_linear_product_expression()
        if alpha_expr is not None:
            options.append(f"alpha='{_escape_filter_value(alpha_expr)}'")

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
        start = _format_seconds(self.start_seconds)
        if self.end_seconds is None:
            return f"gte(t,{start})"
        end = _format_seconds(self.end_seconds)
        return f"gte(t,{start})*lt(t,{end})"

    def _alpha_linear_product_expression(self) -> str | None:
        """FFmpeg expr for piecewise-linear fades while the overlay is enabled."""

        fade_in = max(0.0, float(self.fade_in_seconds))
        fade_out = max(0.0, float(self.fade_out_seconds))
        if fade_in < 1e-12 and fade_out < 1e-12:
            return None
        if self.end_seconds is None:
            return None
        start = _format_seconds(self.start_seconds)
        end = _format_seconds(self.end_seconds)
        fin = "1" if fade_in < 1e-12 else f"min(1,max(0,(t-{start})/{fade_in}))"
        fout = "1" if fade_out < 1e-12 else f"min(1,max(0,({end}-t)/{fade_out}))"
        if fin == "1" and fout == "1":
            return None
        if fin == "1":
            return fout
        if fout == "1":
            return fin
        return f"{fin}*{fout}"


_PLATEAU_EPS = 1e-9


def overlay_opaque_plateau_interval(overlay: TextOverlay) -> tuple[float, float] | None:
    """Return the window where linear fades should be fully opaque (alpha≈1)."""

    if overlay.end_seconds is None:
        return None
    start = overlay.start_seconds
    end = overlay.end_seconds
    fade_in = max(0.0, overlay.fade_in_seconds)
    fade_out = max(0.0, overlay.fade_out_seconds)
    plateau_start = start + fade_in
    plateau_end = end - fade_out
    if plateau_end <= plateau_start + _PLATEAU_EPS:
        return None
    return (plateau_start, plateau_end)


def require_adjacent_overlay_intervals_non_overlapping(
    overlays: Sequence[TextOverlay],
    *,
    nominal_slop_seconds: float = 1e-4,
    plateau_slop_seconds: float = 1e-4,
) -> None:
    """Raise ``ValueError`` when cues leak past the next boundary (nominal or opaque plateau).

    ``nominal_slop_seconds`` catches split-second timeline mistakes (e.g. ending at 3.02 while
    the next cue starts at 3.0). ``plateau_slop_seconds`` catches fade math that would keep two
    fully-opaque stacks competing on screen.
    """

    ordered = tuple(sorted(overlays, key=lambda o: (o.start_seconds, o.end_seconds or 0.0)))
    if len(ordered) < 2:
        return
    for idx in range(len(ordered) - 1):
        previous, current = ordered[idx], ordered[idx + 1]
        prev_end = previous.end_seconds
        curr_start = current.start_seconds
        if prev_end is None or current.end_seconds is None:
            msg = "overlap checks require bounded overlay end times"
            raise ValueError(msg)
        if prev_end > curr_start + nominal_slop_seconds:
            msg = (
                "nominal overlay timeline overlap: previous ends at "
                f"{prev_end:.6f}s but next starts at {curr_start:.6f}s"
            )
            raise ValueError(msg)
        prev_plateau = overlay_opaque_plateau_interval(previous)
        curr_plateau = overlay_opaque_plateau_interval(current)
        if (
            prev_plateau is not None
            and curr_plateau is not None
            and prev_plateau[1] > curr_plateau[0] + plateau_slop_seconds
        ):
            msg = (
                "opaque plateau overlap after fades: "
                f"{prev_plateau} intersects {curr_plateau}"
            )
            raise ValueError(msg)


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


_DRAWTEXT_LITERAL_UNESCAPES: dict[str, str] = {
    "\\": "\\",
    "'": "'",
    ":": ":",
    ",": ",",
    "[": "[",
    "]": "]",
    "%": "%",
    "n": "\n",
}


def parse_drawtext_filter_text(clause: str) -> str:
    """Recover the original overlay string embedded in a ``drawtext=…`` filter clause.

    Intended for regression tests and tooling that need to verify FFmpeg text payloads
    round-trip without executing ffmpeg.
    """

    marker = "text='"
    start = clause.find(marker)
    if start == -1:
        raise ValueError("drawtext clause missing text='…' payload")
    index = start + len(marker)
    parts: list[str] = []
    while index < len(clause):
        ch = clause[index]
        if ch == "'":
            break
        if ch == "\\" and index + 1 < len(clause):
            decoded = _DRAWTEXT_LITERAL_UNESCAPES.get(clause[index + 1])
            if decoded is None:
                msg = f"unsupported drawtext literal escape: {clause[index : index + 2]!r}"
                raise ValueError(msg)
            parts.append(decoded)
            index += 2
            continue
        parts.append(ch)
        index += 1
    else:
        raise ValueError("unterminated text='…' segment in drawtext clause")
    return "".join(parts)


def estimate_wrapped_line_count(
    text: str,
    *,
    font_size_px: int,
    usable_width_px: float,
    avg_char_width_factor: float = 0.52,
) -> int:
    """Rough Latin word-wrap line count for bottom overlay regression checks."""

    words = [word for word in text.replace("\n", " ").split() if word]
    if not words:
        return 0
    char_width = max(4.0, float(font_size_px) * avg_char_width_factor)
    space_width = char_width * 0.35
    budget = max(char_width, usable_width_px)
    lines = 1
    used = 0.0
    for word in words:
        chunk_width = len(word) * char_width
        extra = space_width if used > 0 else 0.0
        if used + extra + chunk_width > budget + 1e-6:
            lines += 1
            used = chunk_width
        else:
            used += extra + chunk_width
    return lines


def estimate_drawtext_block_height_px(line_count: int, overlay: TextOverlay) -> int:
    """Approximate rendered block height (text + borders) for clearance heuristics."""

    if line_count <= 0:
        return 0
    body = line_count * overlay.font_size
    if line_count > 1:
        body += (line_count - 1) * overlay.line_spacing
    return int(body + 2 * overlay.border_width + 2 * overlay.box_border_width)


def bottom_overlay_has_vertical_safe_area(
    overlay: TextOverlay,
    *,
    frame_height_px: int,
    line_count: int,
    top_safe_px: int = 120,
) -> bool:
    """Return True when a bottom-aligned overlay should fit under a top inset (notch/title safe)."""

    block = estimate_drawtext_block_height_px(line_count, overlay)
    return overlay.margin_y + block <= frame_height_px - top_safe_px


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
    "OverlayTimeline",
    "TextOverlay",
    "bottom_overlay_has_vertical_safe_area",
    "build_drawtext_filters",
    "build_overlay_video_filter",
    "estimate_drawtext_block_height_px",
    "estimate_wrapped_line_count",
    "normalize_overlay_timeline",
    "overlay_opaque_plateau_interval",
    "parse_drawtext_filter_text",
    "require_adjacent_overlay_intervals_non_overlapping",
]
