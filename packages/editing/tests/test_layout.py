"""Tests for 9:16 safe-area geometry helpers."""

from __future__ import annotations

from content_lab_editing.layout import (
    DEFAULT_SAFE_AREA_9_16,
    OuterRect,
    SafeAreaInsets9_16,
    rect_fits_frame,
    rect_fits_safe_insets,
    rect_inside_bounds,
)


def test_default_safe_area_insets_are_symmetric_horizontally() -> None:
    assert DEFAULT_SAFE_AREA_9_16.left == DEFAULT_SAFE_AREA_9_16.right == 64


def test_rect_fits_safe_insets_respects_left_and_right() -> None:
    tight = SafeAreaInsets9_16(left=500, right=500, top=0, bottom=0)
    wide = OuterRect(left=50, top=100, width=900, height=40)
    assert not rect_fits_safe_insets(wide, tight, 1080, 1920)


def test_rect_inside_bounds_frame() -> None:
    r = OuterRect(left=0, top=0, width=1080, height=100)
    assert rect_fits_frame(r, 1080, 1920)
    r2 = OuterRect(left=-1, top=0, width=10, height=10)
    assert not rect_fits_frame(r2, 1080, 1920)


def test_rect_inside_bounds_closes_on_edges() -> None:
    r = OuterRect(left=0, top=0, width=1080, height=1920)
    assert rect_inside_bounds(r, 0, 0, 1080, 1920)
