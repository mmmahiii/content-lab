"""Renderer preflight entrypoints for timeline composition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from content_lab_editing.reel_timeline_schema import ReelTimeline
from content_lab_editing.relationship_layout import (
    RelationshipLayoutReport,
    enforce_relationship_layout,
)
from content_lab_editing.support_surface_overlap import OverlapValidationContext


@dataclass(frozen=True, slots=True)
class CompositorPreflightReport:
    relationship_layout: RelationshipLayoutReport

    @property
    def passed(self) -> bool:
        return self.relationship_layout.passed

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "compositor_preflight_v1",
            "passed": self.passed,
            "relationship_layout": self.relationship_layout.as_dict(),
        }


def preflight_compositor_timeline(
    payload: Mapping[str, Any],
    *,
    overlap_context: OverlapValidationContext | None = None,
) -> CompositorPreflightReport:
    """Validate renderer-side physical relationships before composition starts."""

    timeline = ReelTimeline.model_validate(dict(payload))
    return CompositorPreflightReport(
        relationship_layout=enforce_relationship_layout(
            timeline,
            overlap_context=overlap_context,
        ),
    )


__all__ = ["CompositorPreflightReport", "preflight_compositor_timeline"]
