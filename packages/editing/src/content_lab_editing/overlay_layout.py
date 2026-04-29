"""Heuristic overlay layout / safe-area metrics for QA (phase-1 drawtext templates)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from content_lab_editing.overlays import (
    DEFAULT_OVERLAY_MARGIN_X,
    TextOverlay,
)

_CHAR_WIDTH_RATIO = 0.52
_HORIZONTAL_FIT_HEURISTIC_SLACK_PX = 56.0
_EPS_PX = 2.0


def default_overlay_safe_area(*, frame_width: int, frame_height: int) -> dict[str, int]:
    """Title-style safe rectangles for vertical 9:16 (notch + bottom chrome)."""

    bottom_inset = max(96, frame_height // 18)
    return {
        "frame_width": frame_width,
        "frame_height": frame_height,
        "inset_left": max(48, frame_width // 20, DEFAULT_OVERLAY_MARGIN_X // 2),
        "inset_right": max(48, frame_width // 20, DEFAULT_OVERLAY_MARGIN_X // 2),
        "inset_top": max(120, frame_height // 14),
        "inset_bottom": bottom_inset,
    }


def minimum_readable_font_size(*, frame_height: int) -> int:
    """Scale a small-font threshold with output resolution."""

    return max(24, frame_height // 72)


def compute_overlay_layout_payload(
    overlay: TextOverlay,
    *,
    frame_width: int,
    frame_height: int,
    safe_area: Mapping[str, int],
) -> dict[str, Any]:
    """Return manifest-ready layout metrics for one overlay."""

    safe_l = int(safe_area["inset_left"])
    safe_t = int(safe_area["inset_top"])
    safe_r = frame_width - int(safe_area["inset_right"])
    safe_b = frame_height - int(safe_area["inset_bottom"])

    min_font = minimum_readable_font_size(frame_height=frame_height)
    font_unreadably_small = overlay.font_size < min_font

    if isinstance(overlay.x, str) or isinstance(overlay.y, str):
        return {
            "layout_verified": False,
            "layout_skip_reason": "custom_expression_position",
            "font_size": overlay.font_size,
            "font_unreadably_small": font_unreadably_small,
            "safe_area": {
                "inner_left": safe_l,
                "inner_top": safe_t,
                "inner_right": safe_r,
                "inner_bottom": safe_b,
            },
        }

    lines = overlay.text.split("\n") if overlay.text else [""]
    n_lines = len(lines)
    max_chars = max((len(line) for line in lines), default=0)
    char_w = overlay.font_size * _CHAR_WIDTH_RATIO
    text_w = max(float(overlay.font_size), char_w * max(1, max_chars))
    text_h = n_lines * overlay.font_size + max(0, n_lines - 1) * overlay.line_spacing

    box_pad = float(overlay.box_border_width) if overlay.box else 0.0

    lx_text, ty_text = _text_anchor_top_left(
        overlay,
        frame_width=frame_width,
        frame_height=frame_height,
        text_w=text_w,
        text_h=text_h,
    )

    left = lx_text - box_pad
    top = ty_text - box_pad
    right = lx_text + text_w + box_pad
    bottom = ty_text + text_h + box_pad

    out_of_bounds = (
        left < -_EPS_PX
        or top < -_EPS_PX
        or right > frame_width + _EPS_PX
        or bottom > frame_height + _EPS_PX
    )

    fits_safe_area = (
        left >= safe_l - _EPS_PX
        and top >= safe_t - _EPS_PX
        and right <= safe_r + _EPS_PX
        and bottom <= safe_b + _EPS_PX
    )

    max_line_width = _max_line_width(lines, char_w)
    usable_w = _usable_horizontal_width(overlay, frame_width=frame_width)
    did_not_fit_horizontally = max_line_width > usable_w + _HORIZONTAL_FIT_HEURISTIC_SLACK_PX

    clipped = out_of_bounds or (not fits_safe_area)

    return {
        "layout_verified": True,
        "frame_width": frame_width,
        "frame_height": frame_height,
        "estimated_text_width_px": round(text_w, 2),
        "estimated_text_height_px": round(text_h, 2),
        "block_left_px": round(left, 2),
        "block_top_px": round(top, 2),
        "block_right_px": round(right, 2),
        "block_bottom_px": round(bottom, 2),
        "font_size": overlay.font_size,
        "horizontal_align": overlay.horizontal_align,
        "vertical_align": overlay.vertical_align,
        "margin_x": overlay.margin_x,
        "margin_y": overlay.margin_y,
        "usable_max_text_width_px": round(usable_w, 2),
        "max_line_width_px": round(max_line_width, 2),
        "clipped": clipped,
        "out_of_bounds": out_of_bounds,
        "fits_safe_area": fits_safe_area,
        "did_not_fit_horizontally": did_not_fit_horizontally,
        "font_unreadably_small": font_unreadably_small,
        "safe_area": {
            "inner_left": safe_l,
            "inner_top": safe_t,
            "inner_right": safe_r,
            "inner_bottom": safe_b,
        },
    }


def build_overlay_render_manifest_for_qa(
    overlays: Sequence[TextOverlay],
    *,
    frame_width: int,
    frame_height: int,
    safe_area: Mapping[str, int] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Build manifest rows + safe-area block for overlay QA."""

    area = (
        dict(safe_area)
        if safe_area is not None
        else default_overlay_safe_area(frame_width=frame_width, frame_height=frame_height)
    )
    # Ensure frame dimensions are present for consumers.
    area.setdefault("frame_width", frame_width)
    area.setdefault("frame_height", frame_height)

    rows: list[dict[str, Any]] = []
    for overlay in overlays:
        layout = compute_overlay_layout_payload(
            overlay,
            frame_width=frame_width,
            frame_height=frame_height,
            safe_area=area,
        )
        rows.append(
            {
                "text": overlay.text,
                "start_seconds": overlay.start_seconds,
                "end_seconds": overlay.end_seconds,
                "layout": layout,
            }
        )
    return rows, area


def _usable_horizontal_width(overlay: TextOverlay, *, frame_width: int) -> float:
    """Upper bound for single-line width before horizontal crowding."""

    mx = float(overlay.margin_x)
    return float(frame_width) - 2.0 * mx


def _max_line_width(lines: list[str], char_w: float) -> float:
    if not lines:
        return 0.0
    return max(char_w * max(1, len(line)) for line in lines)


def _text_anchor_top_left(
    overlay: TextOverlay,
    *,
    frame_width: int,
    frame_height: int,
    text_w: float,
    text_h: float,
) -> tuple[float, float]:
    if overlay.x is not None and not isinstance(overlay.x, str):
        lx = float(overlay.x)
    elif overlay.horizontal_align == "left":
        lx = float(overlay.margin_x)
    elif overlay.horizontal_align == "right":
        lx = float(frame_width) - float(overlay.margin_x) - text_w
    else:
        lx = (float(frame_width) - text_w) / 2.0

    if overlay.y is not None and not isinstance(overlay.y, str):
        ty = float(overlay.y)
    elif overlay.vertical_align == "top":
        ty = float(overlay.margin_y)
    elif overlay.vertical_align == "center":
        ty = (float(frame_height) - text_h) / 2.0
    else:
        ty = float(frame_height) - float(overlay.margin_y) - text_h

    return lx, ty


__all__ = [
    "build_overlay_render_manifest_for_qa",
    "compute_overlay_layout_payload",
    "default_overlay_safe_area",
    "minimum_readable_font_size",
]
