"""Overlay timeline helpers for deterministic FFmpeg drawtext rendering."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal, TypeAlias, cast

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

DEFAULT_OVERLAY_MARGIN_X = 80
DEFAULT_OVERLAY_MARGIN_Y = 160
DEFAULT_OVERLAY_FONT_SIZE = 64
DEFAULT_OVERLAY_FONT_COLOR = "white"
DEFAULT_OVERLAY_BORDER_COLOR = "black"
DEFAULT_OVERLAY_BORDER_WIDTH = 4
DEFAULT_OVERLAY_BOX_COLOR = "black@0.35"
DEFAULT_OVERLAY_BOX_BORDER_WIDTH = 24
DEFAULT_OVERLAY_LINE_SPACING = 12

# Phase-1 basic vertical editor and drawtext preflight (see `editor_basic.TARGET_WIDTH/HEIGHT`)
DEFAULT_OVERLAY_FRAME_WIDTH = 1080
DEFAULT_OVERLAY_FRAME_HEIGHT = 1920

HorizontalAlign: TypeAlias = Literal["left", "center", "right"]
VerticalAlign: TypeAlias = Literal["top", "center", "bottom"]
OverlayRole: TypeAlias = Literal["hook", "emphasis", "cta", "other"]
OverlayPosition: TypeAlias = str | int | float
OverlayInput: TypeAlias = "TextOverlay | EditInstruction | Mapping[str, object]"
OverlayTimeline: TypeAlias = Sequence[OverlayInput] | EditPlan


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
    overlay_role: OverlayRole = "other"
    hook_autofit: dict[str, object] | None = None

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
    frame_width: int = DEFAULT_OVERLAY_FRAME_WIDTH,
    frame_height: int = DEFAULT_OVERLAY_FRAME_HEIGHT,
    safe_insets: SafeAreaInsets9_16 = DEFAULT_SAFE_AREA_9_16,
) -> tuple[TextOverlay, ...]:
    """Normalize an overlay timeline from edit-plan or raw params inputs.

    Mapping-based overlays get role defaults (font, margins) from
    :func:`content_lab_editing.templates.get_overlay_style_preset` when those keys
    are omitted; roles are resolved with
    :func:`content_lab_editing.templates.resolve_canonical_overlay_role`.

    For ``hook`` (when the style preset allows it), and when ``x``/``y`` are
    default, :func:`layout.autofit_hook_overlay` may wrap to two lines and reduce
    font size. For ``emphasis`` / ``cta``, word and line limits are enforced via
    :class:`OverlayTextPolicyError` before any FFmpeg drawtext work.
    """

    if timeline is None:
        return ()

    items: Sequence[OverlayInput] = (
        timeline.instructions if isinstance(timeline, EditPlan) else timeline
    )

    normalized: list[TextOverlay] = []
    for item in items:
        if isinstance(item, TextOverlay):
            with_fidelity = replace(
                item,
                text=normalize_overlay_source_text(item.text),
            )
            current = _canonicalize_overlay_role(
                with_fidelity.normalize(clip_duration_seconds=clip_duration_seconds)
            )
            _validate_role_text_policy(current)
            normalized.append(
                _apply_hook_autofit_to_overlay(
                    current,
                    frame_width=frame_width,
                    frame_height=frame_height,
                    safe_insets=safe_insets,
                )
            )
            continue
        if isinstance(item, EditInstruction):
            if item.operation != EditOperation.OVERLAY_TEXT:
                continue
            current = TextOverlay.from_mapping(
                item.params, clip_duration_seconds=clip_duration_seconds
            )
            _validate_role_text_policy(current)
            normalized.append(
                _apply_hook_autofit_to_overlay(
                    current,
                    frame_width=frame_width,
                    frame_height=frame_height,
                    safe_insets=safe_insets,
                )
            )
            continue
        current = TextOverlay.from_mapping(item, clip_duration_seconds=clip_duration_seconds)
        _validate_role_text_policy(current)
        normalized.append(
            _apply_hook_autofit_to_overlay(
                current,
                frame_width=frame_width,
                frame_height=frame_height,
                safe_insets=safe_insets,
            )
        )

    normalized.sort(
        key=lambda overlay: (overlay.start_seconds, overlay.end_seconds or float("inf"))
    )
    return tuple(normalized)


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
) -> tuple[str, ...]:
    """Convert a timeline to FFmpeg drawtext clauses."""

    overlays = normalize_overlay_timeline(
        timeline,
        clip_duration_seconds=clip_duration_seconds,
        frame_width=frame_width,
        frame_height=frame_height,
        safe_insets=safe_insets,
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
    timeline: OverlayTimeline | None,
    clip_duration_seconds: float | None = None,
    frame_width: int = DEFAULT_OVERLAY_FRAME_WIDTH,
    frame_height: int = DEFAULT_OVERLAY_FRAME_HEIGHT,
    safe_insets: SafeAreaInsets9_16 = DEFAULT_SAFE_AREA_9_16,
    validate_layout: bool = True,
) -> str:
    """Append overlay drawtext filters to an existing video filter chain."""

    filters = build_drawtext_filters(
        timeline,
        clip_duration_seconds=clip_duration_seconds,
        frame_width=frame_width,
        frame_height=frame_height,
        safe_insets=safe_insets,
        validate_layout=validate_layout,
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
    "DEFAULT_OVERLAY_LINE_SPACING",
    "DEFAULT_OVERLAY_MARGIN_X",
    "DEFAULT_OVERLAY_MARGIN_Y",
    "OverlayInput",
    "OverlayLayoutError",
    "OverlayTextPolicyError",
    "OverlayTimeline",
    "SafeAreaInsets9_16",
    "TextOverlay",
    "build_drawtext_filters",
    "build_overlay_safe_area_report",
    "build_overlay_video_filter",
    "normalize_overlay_source_text",
    "normalize_overlay_timeline",
    "validate_overlay_fits_frame",
]
