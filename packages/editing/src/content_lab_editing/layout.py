"""9:16 (1080x1920) safe-area and overlay bound helpers for drawtext / FFmpeg preflight.

Estimates are conservative: real glyph metrics may differ by font, but are stable
for gating before render.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

# Shared with preflight: Latin-ish default sans at UI sizes (tune with field data).
ESTIMATED_GLYPH_WIDTH_FACTOR = 0.58

# Canonical phase-1 vertical canvas (Reels/Shorts).
FRAME_9_16_WIDTH = 1080
FRAME_9_16_HEIGHT = 1920


# Default safe insets (px) for 9:16 — keep copy clear of notches, status, thumb UI.
@dataclass(frozen=True, slots=True)
class SafeAreaInsets9_16:
    left: int = 64
    right: int = 64
    top: int = 100
    bottom: int = 100


DEFAULT_SAFE_AREA_9_16 = SafeAreaInsets9_16()


@dataclass(frozen=True, slots=True)
class TextBlockEstimate:
    max_line_text_width: int
    line_count: int
    text_block_height: int


@dataclass(frozen=True, slots=True)
class OuterRect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


def pad_per_side(*, has_box: bool, box_border_width: int, border_width: int) -> int:
    if has_box:
        return max(0, int(box_border_width) + int(border_width))
    return max(0, int(border_width))


def estimate_text_block(
    text: str,
    *,
    font_size: int,
    line_spacing: int,
    glyph_width_factor: float = ESTIMATED_GLYPH_WIDTH_FACTOR,
) -> TextBlockEstimate:
    lines = text.splitlines()
    if not lines:
        return TextBlockEstimate(0, 0, 0)
    max_line = 0
    for line in lines:
        width = int(len(line) * font_size * glyph_width_factor) + 1
        if width > max_line:
            max_line = width
    line_count = len(lines)
    block_h = line_count * font_size
    if line_count > 1:
        block_h += (line_count - 1) * line_spacing
    return TextBlockEstimate(
        max_line_text_width=max_line,
        line_count=line_count,
        text_block_height=block_h,
    )


def text_top_left(
    *,
    frame_width: int,
    frame_height: int,
    text_w: int,
    text_h: int,
    horizontal_align: str,
    vertical_align: str,
    margin_x: int,
    margin_y: int,
) -> tuple[int, int]:
    if horizontal_align == "left":
        text_left = margin_x
    elif horizontal_align == "right":
        text_left = frame_width - margin_x - text_w
    else:
        text_left = (frame_width - text_w) // 2
    if vertical_align == "top":
        text_top = margin_y
    elif vertical_align == "center":
        text_top = (frame_height - text_h) // 2
    else:
        text_top = frame_height - text_h - margin_y
    return text_left, text_top


def outer_rect_for_text(
    text_left: int,
    text_top: int,
    text_w: int,
    text_h: int,
    pad: int,
) -> OuterRect:
    return OuterRect(
        left=text_left - pad,
        top=text_top - pad,
        width=text_w + 2 * pad,
        height=text_h + 2 * pad,
    )


def _safe_content_bounds(
    frame_width: int,
    frame_height: int,
    insets: SafeAreaInsets9_16,
) -> tuple[int, int, int, int]:
    return (
        insets.left,
        insets.top,
        frame_width - insets.right,
        frame_height - insets.bottom,
    )


def rect_inside_bounds(
    outer: OuterRect,
    bounds_left: int,
    bounds_top: int,
    bounds_right: int,
    bounds_bottom: int,
) -> bool:
    if outer.width < 1 or outer.height < 1:
        return True
    return (
        outer.left >= bounds_left
        and outer.top >= bounds_top
        and outer.right <= bounds_right
        and outer.bottom <= bounds_bottom
    )


def compute_overlay_outer_rect(
    estimate: TextBlockEstimate,
    *,
    frame_width: int,
    frame_height: int,
    horizontal_align: str,
    vertical_align: str,
    margin_x: int,
    margin_y: int,
    has_box: bool,
    box_border_width: int,
    border_width: int,
) -> OuterRect:
    text_w = estimate.max_line_text_width
    text_h = max(0, estimate.text_block_height)
    pad = pad_per_side(
        has_box=has_box,
        box_border_width=box_border_width,
        border_width=border_width,
    )
    tlx, tly = text_top_left(
        frame_width=frame_width,
        frame_height=frame_height,
        text_w=text_w,
        text_h=text_h,
        horizontal_align=horizontal_align,
        vertical_align=vertical_align,
        margin_x=margin_x,
        margin_y=margin_y,
    )
    return outer_rect_for_text(tlx, tly, text_w, text_h, pad)


def rect_fits_safe_insets(
    outer: OuterRect, insets: SafeAreaInsets9_16, frame_width: int, frame_height: int
) -> bool:
    left, top, right, bot = _safe_content_bounds(frame_width, frame_height, insets)
    return rect_inside_bounds(outer, left, top, right, bot)


def rect_fits_frame(outer: OuterRect, frame_width: int, frame_height: int) -> bool:
    return rect_inside_bounds(outer, 0, 0, frame_width, frame_height)


# Hook overlays: at most two lines; shrink font down to this minimum (readability floor).
HOOK_MAX_LINES = 2
HOOK_MIN_FONT_SIZE = 28

# Non-hook overlays (e.g. role ``other`` / planner body copy): allow more wrapped lines.
OTHER_ROLE_OVERLAY_MAX_LINES = 8


def line_width_estimate_px(
    line: str,
    *,
    font_size: int,
    glyph_width_factor: float = ESTIMATED_GLYPH_WIDTH_FACTOR,
) -> int:
    if not line:
        return 0
    return int(len(line) * font_size * glyph_width_factor) + 1


def available_text_max_width(
    frame_width: int,
    insets: SafeAreaInsets9_16,
    *,
    has_box: bool,
    box_border_width: int,
    border_width: int,
) -> int:
    """Horizontal budget for a single line of text, inside safe insets, minus box/border padding."""

    pad = pad_per_side(
        has_box=has_box, box_border_width=box_border_width, border_width=border_width
    )
    inner = max(0, frame_width - insets.left - insets.right)
    return max(0, inner - 2 * pad)


@dataclass(frozen=True, slots=True)
class HookAutofitResult:
    """Result of hook word-wrap and optional downscaling."""

    text: str
    final_font_size: int
    lines: tuple[str, ...]
    base_font_size: int
    auto_fit: str  # none | wrapped | scaled_down | wrapped_and_scaled


def try_split_hook_to_at_most_two_lines(
    text: str,
    max_line_width_px: int,
    font_size: int,
    glyph_width_factor: float = ESTIMATED_GLYPH_WIDTH_FACTOR,
) -> list[str] | None:
    """Return one or two lines (word-wrapped) if they fit the width budget; else None."""

    words = text.split()
    if not words:
        return None
    one = " ".join(words)
    if (
        line_width_estimate_px(one, font_size=font_size, glyph_width_factor=glyph_width_factor)
        <= max_line_width_px
    ):
        return [one]
    if len(words) == 1:
        w = words[0]
        if (
            line_width_estimate_px(w, font_size=font_size, glyph_width_factor=glyph_width_factor)
            > max_line_width_px
        ):
            return None
        return [w]
    n = len(words)
    for split in range(1, n):
        a = " ".join(words[:split])
        b = " ".join(words[split:])
        if (
            line_width_estimate_px(a, font_size=font_size, glyph_width_factor=glyph_width_factor)
            <= max_line_width_px
            and line_width_estimate_px(
                b, font_size=font_size, glyph_width_factor=glyph_width_factor
            )
            <= max_line_width_px
        ):
            return [a, b]
    return None


def autofit_hook_overlay(
    text: str,
    base_font_size: int,
    line_spacing: int,
    *,
    frame_width: int,
    frame_height: int,
    insets: SafeAreaInsets9_16,
    has_box: bool,
    box_border_width: int,
    border_width: int,
    horizontal_align: str,
    vertical_align: str,
    margin_x: int,
    margin_y: int,
    min_font_size: int = HOOK_MIN_FONT_SIZE,
) -> HookAutofitResult:
    """Word-wrap a hook to at most two lines and reduce font if needed. Raises ValueError on failure."""

    if min_font_size < 8:
        raise ValueError("invalid min_font_size for hook")
    text_flat = " ".join(text.split())
    orig = int(base_font_size)
    base = max(orig, min_font_size)
    mtw = available_text_max_width(
        frame_width,
        insets,
        has_box=has_box,
        box_border_width=box_border_width,
        border_width=border_width,
    )
    for font in range(base, min_font_size - 1, -1):
        two = try_split_hook_to_at_most_two_lines(
            text_flat, mtw, font, ESTIMATED_GLYPH_WIDTH_FACTOR
        )
        if two is None or len(two) > HOOK_MAX_LINES:
            continue
        joined = "\n".join(two)
        est = estimate_text_block(
            joined,
            font_size=font,
            line_spacing=line_spacing,
            glyph_width_factor=ESTIMATED_GLYPH_WIDTH_FACTOR,
        )
        outer = compute_overlay_outer_rect(
            est,
            frame_width=frame_width,
            frame_height=frame_height,
            horizontal_align=horizontal_align,
            vertical_align=vertical_align,
            margin_x=margin_x,
            margin_y=margin_y,
            has_box=has_box,
            box_border_width=box_border_width,
            border_width=border_width,
        )
        if not rect_fits_frame(outer, frame_width, frame_height) or not rect_fits_safe_insets(
            outer, insets, frame_width, frame_height
        ):
            continue
        if font < orig and len(two) == 2:
            reason = "wrapped_and_scaled"
        elif font < orig:
            reason = "scaled_down"
        elif len(two) == 2:
            reason = "wrapped"
        else:
            reason = "none"
        return HookAutofitResult(
            text=joined,
            final_font_size=font,
            lines=tuple(two),
            base_font_size=orig,
            auto_fit=reason,
        )
    msg = "Hook text cannot be fit in at most two lines within frame and 9:16 safe area at minimum font"
    raise ValueError(msg)


def _split_word_to_fit_width(
    word: str,
    max_width_px: int,
    *,
    font_size: int,
    glyph_width_factor: float,
) -> list[str]:
    """Split a single token into substrings each no wider than ``max_width_px``."""

    if (
        not word
        or line_width_estimate_px(word, font_size=font_size, glyph_width_factor=glyph_width_factor)
        <= max_width_px
    ):
        return [word] if word else []
    chunks: list[str] = []
    chunk = ""
    for ch in word:
        trial = chunk + ch
        if (
            line_width_estimate_px(
                trial, font_size=font_size, glyph_width_factor=glyph_width_factor
            )
            <= max_width_px
        ):
            chunk = trial
        else:
            if chunk:
                chunks.append(chunk)
            chunk = ch
    if chunk:
        chunks.append(chunk)
    return chunks


def _tokens_each_fits_width(
    words: Sequence[str],
    max_width_px: int,
    *,
    font_size: int,
    glyph_width_factor: float,
) -> list[str]:
    tokens: list[str] = []
    for w in words:
        tokens.extend(
            _split_word_to_fit_width(
                w, max_width_px, font_size=font_size, glyph_width_factor=glyph_width_factor
            )
        )
    return tokens


def _greedy_wrap_tokens(
    tokens: Sequence[str],
    *,
    max_width_px: int,
    font_size: int,
    glyph_width_factor: float,
    max_lines: int,
) -> list[str] | None:
    if max_lines < 1:
        return None
    lines: list[str] = []
    current: list[str] = []

    def flush() -> bool:
        nonlocal current
        if not current:
            return True
        if len(lines) >= max_lines:
            return False
        lines.append(" ".join(current))
        current = []
        return True

    for tok in tokens:
        trial = " ".join(current + [tok]) if current else tok
        tw = line_width_estimate_px(
            trial, font_size=font_size, glyph_width_factor=glyph_width_factor
        )
        if tw <= max_width_px:
            current.append(tok)
            continue
        if not flush():
            return None
        if len(lines) >= max_lines:
            return None
        tw_one = line_width_estimate_px(
            tok, font_size=font_size, glyph_width_factor=glyph_width_factor
        )
        if tw_one > max_width_px:
            return None
        current = [tok]

    if current:
        if len(lines) >= max_lines:
            return None
        lines.append(" ".join(current))
    return lines


def autofit_standard_overlay(
    text: str,
    base_font_size: int,
    line_spacing: int,
    *,
    frame_width: int,
    frame_height: int,
    insets: SafeAreaInsets9_16,
    has_box: bool,
    box_border_width: int,
    border_width: int,
    horizontal_align: str,
    vertical_align: str,
    margin_x: int,
    margin_y: int,
    line_caps: Sequence[int],
    min_font_size: int = HOOK_MIN_FONT_SIZE,
) -> HookAutofitResult:
    """Shrink font and/or wrap lines so non-hook overlays fit the frame and 9:16 safe area.

    ``line_caps`` is an ordered list of maximum line counts to try (e.g. ``(1, 2)``
    for compact roles that prefer a single line, then allow a second wrap).
    """

    if min_font_size < 8:
        raise ValueError("invalid min_font_size for overlay autofit")
    text_flat = " ".join(text.split())
    if not text_flat:
        raise ValueError("overlay text is empty")
    orig = int(base_font_size)
    base = max(orig, min_font_size)
    caps = tuple(dict.fromkeys(int(c) for c in line_caps if int(c) > 0))
    if not caps:
        raise ValueError("line_caps must include at least one positive integer")

    mtw = available_text_max_width(
        frame_width,
        insets,
        has_box=has_box,
        box_border_width=box_border_width,
        border_width=border_width,
    )

    for line_cap in caps:
        for font in range(base, min_font_size - 1, -1):
            tokens = _tokens_each_fits_width(
                text_flat.split(),
                mtw,
                font_size=font,
                glyph_width_factor=ESTIMATED_GLYPH_WIDTH_FACTOR,
            )
            lines = _greedy_wrap_tokens(
                tokens,
                max_width_px=mtw,
                font_size=font,
                glyph_width_factor=ESTIMATED_GLYPH_WIDTH_FACTOR,
                max_lines=line_cap,
            )
            if lines is None:
                continue
            joined = "\n".join(lines)
            est = estimate_text_block(
                joined,
                font_size=font,
                line_spacing=line_spacing,
                glyph_width_factor=ESTIMATED_GLYPH_WIDTH_FACTOR,
            )
            outer = compute_overlay_outer_rect(
                est,
                frame_width=frame_width,
                frame_height=frame_height,
                horizontal_align=horizontal_align,
                vertical_align=vertical_align,
                margin_x=margin_x,
                margin_y=margin_y,
                has_box=has_box,
                box_border_width=box_border_width,
                border_width=border_width,
            )
            if not rect_fits_frame(outer, frame_width, frame_height) or not rect_fits_safe_insets(
                outer, insets, frame_width, frame_height
            ):
                continue

            if font < orig and len(lines) > 1:
                reason = "wrapped_and_scaled"
            elif font < orig:
                reason = "scaled_down"
            elif len(lines) > 1:
                reason = "wrapped"
            else:
                reason = "none"
            return HookAutofitResult(
                text=joined,
                final_font_size=font,
                lines=tuple(lines),
                base_font_size=orig,
                auto_fit=reason,
            )
    msg = (
        "Overlay text cannot be fit within frame and 9:16 safe area "
        f"at minimum font {min_font_size}px with line caps {caps}"
    )
    raise ValueError(msg)


__all__ = [
    "DEFAULT_SAFE_AREA_9_16",
    "ESTIMATED_GLYPH_WIDTH_FACTOR",
    "FRAME_9_16_HEIGHT",
    "FRAME_9_16_WIDTH",
    "HOOK_MAX_LINES",
    "HOOK_MIN_FONT_SIZE",
    "OTHER_ROLE_OVERLAY_MAX_LINES",
    "HookAutofitResult",
    "OuterRect",
    "SafeAreaInsets9_16",
    "TextBlockEstimate",
    "autofit_hook_overlay",
    "autofit_standard_overlay",
    "available_text_max_width",
    "compute_overlay_outer_rect",
    "estimate_text_block",
    "line_width_estimate_px",
    "outer_rect_for_text",
    "pad_per_side",
    "rect_fits_frame",
    "rect_fits_safe_insets",
    "rect_inside_bounds",
    "text_top_left",
    "try_split_hook_to_at_most_two_lines",
]
