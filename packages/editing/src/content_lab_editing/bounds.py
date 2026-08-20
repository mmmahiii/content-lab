"""Normalized bounds helpers for renderer timeline objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class NormalizedObject(Protocol):
    x: float
    y: float
    scale: float
    width_normalised: float
    height_normalised: float


@dataclass(frozen=True, slots=True)
class NormalizedBounds:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return max(0.0, self.right - self.left)

    @property
    def height(self) -> float:
        return max(0.0, self.bottom - self.top)

    @property
    def area(self) -> float:
        return self.width * self.height

    def contains(self, other: NormalizedBounds) -> bool:
        return (
            other.left >= self.left
            and other.right <= self.right
            and other.top >= self.top
            and other.bottom <= self.bottom
        )


def normalized_bounds(item: NormalizedObject) -> NormalizedBounds:
    """Compute clamped normalized bounds from center coordinates and scale."""

    width = item.width_normalised * item.scale
    height = item.height_normalised * item.scale
    return NormalizedBounds(
        left=max(0.0, item.x - width / 2),
        top=max(0.0, item.y - height / 2),
        right=min(1.0, item.x + width / 2),
        bottom=min(1.0, item.y + height / 2),
    )


def overlap_ratio(item: NormalizedObject, other: NormalizedObject) -> float:
    """Return overlap area as a ratio of the first object's area."""

    item_bounds = normalized_bounds(item)
    other_bounds = normalized_bounds(other)
    overlap_width = max(0.0, min(item_bounds.right, other_bounds.right) - max(item_bounds.left, other_bounds.left))
    overlap_height = max(0.0, min(item_bounds.bottom, other_bounds.bottom) - max(item_bounds.top, other_bounds.top))
    overlap_area = overlap_width * overlap_height
    return overlap_area / max(0.0001, item_bounds.area)


__all__ = ["NormalizedBounds", "NormalizedObject", "normalized_bounds", "overlap_ratio"]
