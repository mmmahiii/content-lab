"""Overlay timeline helpers for deterministic FFmpeg drawtext rendering."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal, NamedTuple, TypeAlias, cast

from content_lab_editing.instructions import EditInstruction, EditOperation, EditPlan
from content_lab_editing.layout import (
    DEFAULT_SAFE_AREA_9_16,
    ESTIMATED_GLYPH_WIDTH_FACTOR,
    SafeAreaInsets9_16,
    autofit_hook_overlay,
    compute_overlay_outer_rect,
    estimate_text_block,
    rect_fits_frame,
    rect_fits_safe_insets,
)
from content_lab_editing.templates import (
    get_overlay_style_preset,
    resolve_canonical_overlay_role,
)
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
DEFAULT_OVERLAY_HANDOFF_GAP_SECONDS = 0.0

# Phase-1 basic vertical editor and drawtext preflight (see `editor_basic.TARGET_WIDTH/HEIGHT`)
DEFAULT_OVERLAY_FRAME_WIDTH = 1080
DEFAULT_OVERLAY_FRAME_HEIGHT = 1920

HorizontalAlign: TypeAlias = Literal["left", "center", "right"]
VerticalAlign: TypeAlias = Literal["top", "center", "bottom"]
OverlayRole: TypeAlias = Literal["hook", "emphasis", "cta", "other"]
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


class OverlayTextPolicyError(ValueError):
    """Raised when on-screen text violates role-specific copy limits (emphasis/CTA)."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        role: str,
        text: str,
        word_count: int,
        line_count: int,
        max_word_count: int | None,
        max_text_lines: int | None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.role = role
        self.text = text
        self.word_count = word_count
        self.line_count = line_count
        self.max_word_count = max_word_count
        self.max_text_lines = max_text_lines

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "overlay_text_policy",
            "code": self.code,
            "role": self.role,
            "text": self.text,
            "word_count": self.word_count,
            "line_count": self.line_count,
            "max_word_count": self.max_word_count,
            "max_text_lines": self.max_text_lines,
        }


class OverlayLayoutError(ValueError):
    """Raised when overlay text/box is outside the frame or 9:16 safe area (no silent clip)."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        text: str,
        font_size: int,
        line_spacing: int,
        margin_x: int,
        margin_y: int,
        frame_width: int,
        frame_height: int,
        available_width: int,
        available_height: int,
        max_line_width_estimate: int,
        block_height_estimate: int,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.text = text
        self.font_size = font_size
        self.line_spacing = line_spacing
        self.margin_x = margin_x
        self.margin_y = margin_y
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.available_width = available_width
        self.available_height = available_height
        self.max_line_width_estimate = max_line_width_estimate
        self.block_height_estimate = block_height_estimate
        self.details = details or {}

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "overlay_layout",
            "code": self.code,
            "text": self.text,
            "font_size": self.font_size,
            "line_spacing": self.line_spacing,
            "margin_x": self.margin_x,
            "margin_y": self.margin_y,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "available_width": self.available_width,
            "available_height": self.available_height,
            "max_line_width_estimate": self.max_line_width_estimate,
            "block_height_estimate": self.block_height_estimate,
            "details": dict(self.details),
        }


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
    overlay_role: OverlayRole = "other"
    hook_autofit: dict[str, object] | None = None
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
            text=_require_overlay_text(payload),
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
            overlay_role=_read_overlay_role(payload),
            hook_autofit=None,
            enter_duration_ms=_read_optional_float_ms(payload, "enter_duration_ms"),
            exit_duration_ms=_read_optional_float_ms(payload, "exit_duration_ms"),
            overlay_id=_read_overlay_id(payload),
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

        overlay = overlay.normalize(clip_duration_seconds=clip_duration_seconds)
        return _merge_style_preset(overlay, payload)

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

        linear_alpha_expr = self._alpha_linear_product_expression()
        if linear_alpha_expr is not None:
            options.append(f"alpha='{_escape_filter_value(linear_alpha_expr)}'")

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
            msg = "opaque plateau overlap after fades: " f"{prev_plateau} intersects {curr_plateau}"
            raise ValueError(msg)


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
    frame_width: int = DEFAULT_OVERLAY_FRAME_WIDTH,
    frame_height: int = DEFAULT_OVERLAY_FRAME_HEIGHT,
    safe_insets: SafeAreaInsets9_16 = DEFAULT_SAFE_AREA_9_16,
    allow_overlay_stack: bool = False,
    handoff_gap_seconds: float = DEFAULT_OVERLAY_HANDOFF_GAP_SECONDS,
    transition: OverlayTransitionSettings | None = None,
) -> tuple[TextOverlay, ...]:
    """Normalize an overlay timeline from edit-plan or raw params inputs.

    Mapping-based overlays get role defaults (font, margins) from
    :func:`content_lab_editing.templates.get_overlay_style_preset` when those keys
    are omitted; roles are resolved with
    :func:`content_lab_editing.templates.resolve_canonical_overlay_role`.

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

    prepared: list[TextOverlay] = []
    for overlay in ordered:
        current = _canonicalize_overlay_role(
            replace(overlay, text=normalize_overlay_source_text(overlay.text))
        )
        _validate_role_text_policy(current)
        prepared.append(
            _apply_hook_autofit_to_overlay(
                current,
                frame_width=frame_width,
                frame_height=frame_height,
                safe_insets=safe_insets,
            )
        )
    ordered = prepared

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
                work.append((source_path, "sequence", "mapping", raw_text, overlay, item))
                continue
            raise TypeError(f"Unsupported overlay timeline entry type: {type(item)!r}")

    work.sort(
        key=lambda row: (row[4].start_seconds, row[4].end_seconds or float("inf")),
    )

    diagnostics: list[OverlayRenderDiagnostic] = []
    for idx, (
        source_path,
        container,
        source_kind,
        payload_raw,
        overlay,
        payload_mapping,
    ) in enumerate(work):
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


def _apply_hook_autofit_to_overlay(
    overlay: TextOverlay,
    *,
    frame_width: int,
    frame_height: int,
    safe_insets: SafeAreaInsets9_16,
) -> TextOverlay:
    if overlay.overlay_role != "hook":
        return replace(overlay, hook_autofit=None)
    if overlay.x is not None or overlay.y is not None:
        return replace(overlay, hook_autofit=None)
    if not overlay.text.strip():
        return replace(overlay, hook_autofit=None)

    est0 = estimate_text_block(
        overlay.text,
        font_size=overlay.font_size,
        line_spacing=overlay.line_spacing,
        glyph_width_factor=ESTIMATED_GLYPH_WIDTH_FACTOR,
    )
    available_w = max(0, frame_width - safe_insets.left - safe_insets.right)
    available_h = max(0, frame_height - safe_insets.top - safe_insets.bottom)
    try:
        result = autofit_hook_overlay(
            overlay.text,
            overlay.font_size,
            overlay.line_spacing,
            frame_width=frame_width,
            frame_height=frame_height,
            insets=safe_insets,
            has_box=overlay.box,
            box_border_width=overlay.box_border_width,
            border_width=overlay.border_width,
            horizontal_align=overlay.horizontal_align,
            vertical_align=overlay.vertical_align,
            margin_x=overlay.margin_x,
            margin_y=overlay.margin_y,
        )
    except ValueError as exc:
        base_details: dict[str, object] = {
            "reason": "hook_autofit",
        }
        raise OverlayLayoutError(
            f"Hook overlay cannot be read in at most two lines within safe bounds: {exc}",
            code="hook_unreadable",
            text=overlay.text,
            font_size=overlay.font_size,
            line_spacing=overlay.line_spacing,
            margin_x=overlay.margin_x,
            margin_y=overlay.margin_y,
            frame_width=frame_width,
            frame_height=frame_height,
            available_width=available_w,
            available_height=available_h,
            max_line_width_estimate=est0.max_line_text_width,
            block_height_estimate=est0.text_block_height,
            details=base_details,
        ) from exc

    meta: dict[str, object] = {
        "base_font_size": result.base_font_size,
        "final_font_size": result.final_font_size,
        "lines": list(result.lines),
        "line_count": len(result.lines),
        "auto_fit": result.auto_fit,
    }
    return replace(
        overlay,
        text=result.text,
        font_size=result.final_font_size,
        hook_autofit=meta,
    )


def normalize_overlay_source_text(value: str) -> str:
    """Trim leading and trailing whitespace only; preserve all inner characters."""

    return value.strip()


def validate_overlay_fits_frame(
    overlay: TextOverlay,
    *,
    frame_width: int = DEFAULT_OVERLAY_FRAME_WIDTH,
    frame_height: int = DEFAULT_OVERLAY_FRAME_HEIGHT,
    safe_insets: SafeAreaInsets9_16 = DEFAULT_SAFE_AREA_9_16,
) -> None:
    """Raise :class:`OverlayLayoutError` when the estimated text+box is outside the frame or safe area.

    Skips validation when the overlay uses a custom ``x``/``y`` expression; callers
    that pin coordinates must keep bounds in range themselves.
    """

    if overlay.x is not None or overlay.y is not None:
        return
    if frame_width < 1 or frame_height < 1:
        return
    if not overlay.text.splitlines():
        return

    est = estimate_text_block(
        overlay.text,
        font_size=overlay.font_size,
        line_spacing=overlay.line_spacing,
        glyph_width_factor=ESTIMATED_GLYPH_WIDTH_FACTOR,
    )
    outer = compute_overlay_outer_rect(
        est,
        frame_width=frame_width,
        frame_height=frame_height,
        horizontal_align=overlay.horizontal_align,
        vertical_align=overlay.vertical_align,
        margin_x=overlay.margin_x,
        margin_y=overlay.margin_y,
        has_box=overlay.box,
        box_border_width=overlay.box_border_width,
        border_width=overlay.border_width,
    )
    available_width = max(0, frame_width - safe_insets.left - safe_insets.right)
    available_height = max(0, frame_height - safe_insets.top - safe_insets.bottom)
    base_details: dict[str, object] = {
        "outer_rect": {
            "left": outer.left,
            "top": outer.top,
            "width": outer.width,
            "height": outer.height,
        },
        "safe_insets": {
            "left": safe_insets.left,
            "right": safe_insets.right,
            "top": safe_insets.top,
            "bottom": safe_insets.bottom,
        },
    }

    if not rect_fits_frame(outer, frame_width, frame_height):
        raise OverlayLayoutError(
            "Overlay text/box would extend outside the video frame. "
            "Reduce copy, add line breaks, lower font size, or adjust margins and padding.",
            code="exceeds_frame",
            text=overlay.text,
            font_size=overlay.font_size,
            line_spacing=overlay.line_spacing,
            margin_x=overlay.margin_x,
            margin_y=overlay.margin_y,
            frame_width=frame_width,
            frame_height=frame_height,
            available_width=available_width,
            available_height=available_height,
            max_line_width_estimate=est.max_line_text_width,
            block_height_estimate=est.text_block_height,
            details=base_details,
        )
    if not rect_fits_safe_insets(outer, safe_insets, frame_width, frame_height):
        raise OverlayLayoutError(
            "Overlay text/box is outside the 9:16 title-safe area. "
            "Tighten copy, add line breaks, or reduce font size so the box stays within safe margins.",
            code="exceeds_safe_area",
            text=overlay.text,
            font_size=overlay.font_size,
            line_spacing=overlay.line_spacing,
            margin_x=overlay.margin_x,
            margin_y=overlay.margin_y,
            frame_width=frame_width,
            frame_height=frame_height,
            available_width=available_width,
            available_height=available_height,
            max_line_width_estimate=est.max_line_text_width,
            block_height_estimate=est.text_block_height,
            details=base_details,
        )


def build_overlay_safe_area_report(
    timeline: OverlayTimeline | None,
    *,
    clip_duration_seconds: float | None = None,
    frame_width: int = DEFAULT_OVERLAY_FRAME_WIDTH,
    frame_height: int = DEFAULT_OVERLAY_FRAME_HEIGHT,
    insets: SafeAreaInsets9_16 = DEFAULT_SAFE_AREA_9_16,
) -> dict[str, object]:
    """Return a JSON-friendly summary for manifests (pass/fail per overlay, no FFmpeg required)."""

    overlays = normalize_overlay_timeline(
        timeline,
        clip_duration_seconds=clip_duration_seconds,
        frame_width=frame_width,
        frame_height=frame_height,
        safe_insets=insets,
    )
    if not overlays:
        return {
            "schema_version": 1,
            "status": "skipped",
            "reason": "no_overlays",
        }

    entries: list[dict[str, object]] = []
    for index, item in enumerate(overlays):
        if item.x is not None or item.y is not None:
            entries.append(
                {
                    "index": index,
                    "status": "skipped",
                    "reason": "custom_x_or_y",
                }
            )
            continue
        est = estimate_text_block(
            item.text,
            font_size=item.font_size,
            line_spacing=item.line_spacing,
            glyph_width_factor=ESTIMATED_GLYPH_WIDTH_FACTOR,
        )
        outer = compute_overlay_outer_rect(
            est,
            frame_width=frame_width,
            frame_height=frame_height,
            horizontal_align=item.horizontal_align,
            vertical_align=item.vertical_align,
            margin_x=item.margin_x,
            margin_y=item.margin_y,
            has_box=item.box,
            box_border_width=item.box_border_width,
            border_width=item.border_width,
        )
        fits_frame = rect_fits_frame(outer, frame_width, frame_height)
        fits_safe = rect_fits_safe_insets(outer, insets, frame_width, frame_height)
        entry_status = "pass" if (fits_frame and fits_safe) else "fail"
        entry: dict[str, object] = {
            "index": index,
            "status": entry_status,
            "fits_frame": fits_frame,
            "fits_safe_area": fits_safe,
            "overlay_role": item.overlay_role,
            "max_text_width_estimate_px": est.max_line_text_width,
            "text_block_height_estimate_px": est.text_block_height,
            "outer_rect_px": {
                "left": outer.left,
                "top": outer.top,
                "width": outer.width,
                "height": outer.height,
            },
        }
        if item.hook_autofit is not None:
            entry["hook_autofit"] = dict(item.hook_autofit)
        entries.append(entry)

    if any(e.get("status") == "fail" for e in entries):
        overall = "fail"
    elif entries and all(e.get("status") == "skipped" for e in entries):
        overall = "skipped"
    else:
        overall = "pass"

    return {
        "schema_version": 1,
        "status": overall,
        "frame": {"width": frame_width, "height": frame_height},
        "safe_insets_px": {
            "left": insets.left,
            "right": insets.right,
            "top": insets.top,
            "bottom": insets.bottom,
        },
        "overlays": entries,
    }


def build_drawtext_filters(
    timeline: OverlayTimeline | None,
    *,
    clip_duration_seconds: float | None = None,
    frame_width: int = DEFAULT_OVERLAY_FRAME_WIDTH,
    frame_height: int = DEFAULT_OVERLAY_FRAME_HEIGHT,
    safe_insets: SafeAreaInsets9_16 = DEFAULT_SAFE_AREA_9_16,
    validate_layout: bool = True,
    allow_overlay_stack: bool = False,
    handoff_gap_seconds: float = DEFAULT_OVERLAY_HANDOFF_GAP_SECONDS,
    transition: OverlayTransitionSettings | None = None,
    normalized_timeline: tuple[TextOverlay, ...] | None = None,
) -> tuple[str, ...]:
    """Convert a timeline to FFmpeg drawtext clauses."""

    overlays = normalized_timeline
    if overlays is None:
        overlays = normalize_overlay_timeline(
            timeline,
            clip_duration_seconds=clip_duration_seconds,
            frame_width=frame_width,
            frame_height=frame_height,
            safe_insets=safe_insets,
            allow_overlay_stack=allow_overlay_stack,
            handoff_gap_seconds=handoff_gap_seconds,
            transition=transition,
        )
    if validate_layout:
        for overlay in overlays:
            validate_overlay_fits_frame(
                overlay,
                frame_width=frame_width,
                frame_height=frame_height,
                safe_insets=safe_insets,
            )
    return tuple(overlay.drawtext_filter() for overlay in overlays)


def build_overlay_video_filter(
    *,
    base_filter: str,
    timeline: OverlayTimeline | None = None,
    clip_duration_seconds: float | None = None,
    frame_width: int = DEFAULT_OVERLAY_FRAME_WIDTH,
    frame_height: int = DEFAULT_OVERLAY_FRAME_HEIGHT,
    safe_insets: SafeAreaInsets9_16 = DEFAULT_SAFE_AREA_9_16,
    validate_layout: bool = True,
    allow_overlay_stack: bool = False,
    handoff_gap_seconds: float = DEFAULT_OVERLAY_HANDOFF_GAP_SECONDS,
    transition: OverlayTransitionSettings | None = None,
    normalized_timeline: tuple[TextOverlay, ...] | None = None,
) -> str:
    """Append overlay drawtext filters to an existing video filter chain."""

    filters = build_drawtext_filters(
        timeline,
        clip_duration_seconds=clip_duration_seconds,
        frame_width=frame_width,
        frame_height=frame_height,
        safe_insets=safe_insets,
        validate_layout=validate_layout,
        allow_overlay_stack=allow_overlay_stack,
        handoff_gap_seconds=handoff_gap_seconds,
        transition=transition,
        normalized_timeline=normalized_timeline,
    )
    if not filters:
        return base_filter
    return ",".join((base_filter, *filters))


def _merge_style_preset(
    overlay: TextOverlay,
    payload: Mapping[str, object],
) -> TextOverlay:
    """Apply role defaults for missing style keys (mapping-based overlays only)."""

    preset = get_overlay_style_preset(overlay.overlay_role)
    if preset is None:
        return overlay
    updated = overlay
    if "font_size" not in payload:
        updated = replace(updated, font_size=preset.default_font_size)
    if "line_spacing" not in payload:
        updated = replace(updated, line_spacing=preset.default_line_spacing)
    if "margin_x" not in payload:
        updated = replace(updated, margin_x=preset.default_margin_x)
    if "margin_y" not in payload:
        updated = replace(updated, margin_y=preset.default_margin_y)
    return updated


def _canonicalize_overlay_role(overlay: TextOverlay) -> TextOverlay:
    """Map legacy script/scene tokens to :class:`OverlayRole` on direct :class:`TextOverlay` instances."""

    raw = str(overlay.overlay_role).strip().lower()
    if raw in {"value", "context"}:
        return replace(overlay, overlay_role="emphasis")
    if raw == "disclosure":
        return replace(overlay, overlay_role="cta")
    if raw in {"hook", "emphasis", "cta", "other"}:
        if raw != overlay.overlay_role:
            return replace(overlay, overlay_role=cast(OverlayRole, raw))
        return overlay
    return replace(overlay, overlay_role="other")


def _validate_role_text_policy(overlay: TextOverlay) -> None:
    preset = get_overlay_style_preset(overlay.overlay_role)
    if preset is None:
        return
    text = overlay.text
    line_count = len(text.splitlines())
    word_count = len(text.split())

    if preset.max_text_lines is not None and line_count > preset.max_text_lines:
        raise OverlayTextPolicyError(
            f"Overlay role {preset.name!r} allows at most {preset.max_text_lines} text line(s); "
            f"got {line_count} line(s).",
            code="role_text_too_long",
            role=preset.name,
            text=text,
            word_count=word_count,
            line_count=line_count,
            max_word_count=preset.max_word_count,
            max_text_lines=preset.max_text_lines,
        )
    if preset.max_word_count is not None and word_count > preset.max_word_count:
        raise OverlayTextPolicyError(
            f"Overlay role {preset.name!r} allows at most {preset.max_word_count} word(s); "
            f"got {word_count}.",
            code="role_text_too_long",
            role=preset.name,
            text=text,
            word_count=word_count,
            line_count=line_count,
            max_word_count=preset.max_word_count,
            max_text_lines=preset.max_text_lines,
        )


def _require_overlay_text(payload: Mapping[str, object]) -> str:
    value = payload.get("text")
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError("Overlay text must not be blank")
    if isinstance(value, str):
        return normalize_overlay_source_text(value)
    return normalize_overlay_source_text(str(value))


def _read_overlay_id(payload: Mapping[str, object]) -> str | None:
    for key in ("overlay_id", "id", "cue_id"):
        value = _read_optional_str(payload, key, default=None)
        if value is None:
            continue
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _read_overlay_role(payload: Mapping[str, object]) -> OverlayRole:
    r = resolve_canonical_overlay_role(payload)
    if r in ("hook", "emphasis", "cta"):
        return cast(OverlayRole, r)
    return "other"


def _read_optional_float(
    payload: Mapping[str, object],
    *keys: str,
) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, bool):
            raise ValueError(f"Overlay field '{key}' must be numeric")
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
    "DEFAULT_SAFE_AREA_9_16",
    "DEFAULT_OVERLAY_BORDER_COLOR",
    "DEFAULT_OVERLAY_BORDER_WIDTH",
    "DEFAULT_OVERLAY_BOX_BORDER_WIDTH",
    "DEFAULT_OVERLAY_BOX_COLOR",
    "DEFAULT_OVERLAY_FONT_COLOR",
    "DEFAULT_OVERLAY_FONT_SIZE",
    "DEFAULT_OVERLAY_FRAME_HEIGHT",
    "DEFAULT_OVERLAY_FRAME_WIDTH",
    "DEFAULT_OVERLAY_HANDOFF_GAP_SECONDS",
    "DEFAULT_OVERLAY_LINE_SPACING",
    "DEFAULT_OVERLAY_MARGIN_X",
    "DEFAULT_OVERLAY_MARGIN_Y",
    "OverlayInput",
    "OverlayLayoutError",
    "OverlayRenderDiagnostic",
    "OverlayTextPolicyError",
    "OverlayTimeline",
    "OverlayTimelineSlot",
    "OverlayTransitionSettings",
    "SafeAreaInsets9_16",
    "TextOverlay",
    "bottom_overlay_has_vertical_safe_area",
    "build_drawtext_filters",
    "build_overlay_safe_area_report",
    "build_overlay_render_diagnostics",
    "build_overlay_render_report",
    "build_rendered_overlay_manifest",
    "build_overlay_video_filter",
    "bottom_overlay_has_vertical_safe_area",
    "estimate_drawtext_block_height_px",
    "estimate_wrapped_line_count",
    "list_pre_handoff_overlay_slots",
    "normalize_overlay_source_text",
    "normalize_overlay_timeline",
    "overlay_opaque_plateau_interval",
    "parse_drawtext_filter_text",
    "require_adjacent_overlay_intervals_non_overlapping",
    "scene_plan_overlay_text_references",
    "validate_overlay_fits_frame",
]
