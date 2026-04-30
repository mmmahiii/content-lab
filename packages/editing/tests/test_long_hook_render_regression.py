"""TEST-G002: long hook text must round-trip into drawtext without silent truncation."""

from __future__ import annotations

import pytest

from content_lab_editing.overlays import (
    DEFAULT_OVERLAY_FONT_SIZE,
    DEFAULT_OVERLAY_MARGIN_X,
    TextOverlay,
    bottom_overlay_has_vertical_safe_area,
    build_drawtext_filters,
    estimate_drawtext_block_height_px,
    estimate_wrapped_line_count,
    parse_drawtext_filter_text,
)

# Golden copy from packaged creative traces (do not shorten — tests below require the suffix).
LONG_HOOK_OPERATIONS_RESET_G002 = "The operations reset busy founders can do today"


@pytest.mark.parametrize(
    "required_tail",
    ["can do today", LONG_HOOK_OPERATIONS_RESET_G002],
    ids=["suffix_can_do_today", "full_phrase"],
)
def test_g002_long_hook_constant_includes_non_optional_tail(required_tail: str) -> None:
    """Changing the golden hook must keep `can do today` or this suite loses meaning."""

    assert required_tail in LONG_HOOK_OPERATIONS_RESET_G002
    assert LONG_HOOK_OPERATIONS_RESET_G002.endswith("can do today")


def test_long_hook_source_equals_final_drawtext_literal() -> None:
    overlay = TextOverlay.from_mapping(
        {
            "text": LONG_HOOK_OPERATIONS_RESET_G002,
            "start_seconds": 0,
            "end_seconds": 3,
        },
        clip_duration_seconds=12.0,
    )
    clause = overlay.drawtext_filter()
    parsed = parse_drawtext_filter_text(clause)
    assert parsed == LONG_HOOK_OPERATIONS_RESET_G002
    assert "can do today" in parsed
    assert "fix_bounds=1" in clause


def test_autofit_hook_drawtext_uses_real_newline_not_literal_backslash_n() -> None:
    clause = build_drawtext_filters(
        [
            TextOverlay(
                text=LONG_HOOK_OPERATIONS_RESET_G002,
                overlay_role="hook",
                start_seconds=0,
                end_seconds=3,
            )
        ],
        clip_duration_seconds=12.0,
    )[0]

    assert "\\n" not in clause
    assert "busynfounders" not in clause
    assert "busy\nfounders" in clause
    assert parse_drawtext_filter_text(clause) == "The operations reset busy\nfounders can do today"


def test_long_hook_layout_fits_vertical_safe_area_and_readable_wrapping() -> None:
    frame_w, frame_h = 1080, 1920
    overlay = TextOverlay.from_mapping(
        {"text": LONG_HOOK_OPERATIONS_RESET_G002, "start": 0, "duration": 3},
        clip_duration_seconds=12.0,
    )

    usable_w = float(frame_w - 2 * overlay.margin_x)
    lines = estimate_wrapped_line_count(
        LONG_HOOK_OPERATIONS_RESET_G002,
        font_size_px=overlay.font_size,
        usable_width_px=usable_w,
    )
    assert 2 <= lines <= 5

    assert overlay.font_size >= 52
    assert overlay.font_size == DEFAULT_OVERLAY_FONT_SIZE
    assert overlay.margin_x == DEFAULT_OVERLAY_MARGIN_X

    block_h = estimate_drawtext_block_height_px(lines, overlay)
    assert overlay.margin_y + block_h < frame_h

    assert bottom_overlay_has_vertical_safe_area(
        overlay,
        frame_height_px=frame_h,
        line_count=lines,
        top_safe_px=120,
    )

    char_w = max(4.0, overlay.font_size * 0.52)
    longest = max(LONG_HOOK_OPERATIONS_RESET_G002.split(), key=len)
    assert len(longest) * char_w <= usable_w + 1.0
