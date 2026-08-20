"""Renderer-side physical relationship enforcement for reel timelines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from content_lab_editing.bounds import normalized_bounds, overlap_ratio
from content_lab_editing.reel_timeline_schema import ReelTimeline, ReelTimelineObject
from content_lab_editing.support_surface_overlap import (
    OverlapValidationContext,
    evaluate_on_surface_support_region,
    overlap_artifacts_for_support,
    resolve_support_overlap_ratio,
)

RelationshipSeverity = Literal["warn", "fail"]


@dataclass(frozen=True, slots=True)
class RelationshipLayoutFinding:
    code: str
    severity: RelationshipSeverity
    message: str
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class RelationshipLayoutReport:
    findings: tuple[RelationshipLayoutFinding, ...]

    @property
    def passed(self) -> bool:
        return not any(finding.severity == "fail" for finding in self.findings)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "relationship_layout_v1",
            "passed": self.passed,
            "findings": [finding.as_dict() for finding in self.findings],
            "failure_codes": [
                finding.code for finding in self.findings if finding.severity == "fail"
            ],
            "warning_codes": [
                finding.code for finding in self.findings if finding.severity == "warn"
            ],
        }


def enforce_relationship_layout(
    timeline: ReelTimeline,
    *,
    overlap_context: OverlapValidationContext | None = None,
) -> RelationshipLayoutReport:
    """Return render-blocking findings for physically invalid object relationships."""

    findings: list[RelationshipLayoutFinding] = []
    objects_by_scene: dict[str, dict[str, ReelTimelineObject]] = {}
    for item in timeline.objects:
        objects_by_scene.setdefault(item.scene_id, {})[item.object_id] = item

    for scene_objects in objects_by_scene.values():
        heroes = [item for item in scene_objects.values() if item.role == "hero_subject"]
        hero = max(heroes, key=_visual_priority) if heroes else None
        for item in scene_objects.values():
            support = scene_objects.get(item.support_object_id or "")
            if _needs_support(item) and support is None:
                findings.append(
                    _finding(
                        "support_object_not_found",
                        "support_object_id must reference an object in the same scene.",
                        object_id=item.object_id,
                        support_object_id=item.support_object_id,
                    )
                )
                continue
            if support is not None:
                _check_support_relationship(item, support, findings, overlap_context=overlap_context)
            if hero is not None and item.object_id != hero.object_id:
                _check_hero_relationship(item, hero, findings)
            _check_contact_shadow(item, scene_objects, findings)

    return RelationshipLayoutReport(findings=tuple(findings))


def object_bounds(item: ReelTimelineObject) -> dict[str, float]:
    """Return renderer-debuggable normalized bounds for one object."""

    bounds = normalized_bounds(item)
    return {
        "left": bounds.left,
        "top": bounds.top,
        "right": bounds.right,
        "bottom": bounds.bottom,
        "width": bounds.width,
        "height": bounds.height,
        "area": bounds.area,
    }


def _check_support_relationship(
    item: ReelTimelineObject,
    support: ReelTimelineObject,
    findings: list[RelationshipLayoutFinding],
    *,
    overlap_context: OverlapValidationContext | None = None,
) -> None:
    artifacts = overlap_artifacts_for_support(support, overlap_context)
    if item.spatial_relationship == "on_surface":
        region = evaluate_on_surface_support_region(
            item,
            support,
            artifacts,
            required_overlap_ratio=item.required_overlap_ratio,
        )
        if region.mask_expected and not region.mask_available:
            findings.append(
                _finding(
                    "on_surface_support_mask_unavailable",
                    "Support surface mask was expected but was not loaded; renderer must not fall back to bbox placement.",
                    object_id=item.object_id,
                    support_object_id=support.object_id,
                    **region.as_dict(),
                )
            )
        if not region.passed:
            failure_code = region.failure_code or "relationship_required_overlap_not_met"
            message = (
                "Object on_surface is outside the occupied support-surface region."
                if failure_code == "on_surface_outside_support_region"
                else "Object does not meet required support overlap at render time."
            )
            findings.append(
                _finding(
                    failure_code,
                    message,
                    object_id=item.object_id,
                    support_object_id=support.object_id,
                    required_overlap_ratio=item.required_overlap_ratio,
                    **region.as_dict(),
                )
            )
    else:
        overlap, overlap_method = resolve_support_overlap_ratio(item, support, artifacts)
        if overlap < item.required_overlap_ratio:
            findings.append(
                _finding(
                    "relationship_required_overlap_not_met",
                    "Object does not meet required support overlap at render time.",
                    object_id=item.object_id,
                    support_object_id=support.object_id,
                    overlap_ratio=round(overlap, 4),
                    required_overlap_ratio=item.required_overlap_ratio,
                    overlap_method=overlap_method,
                )
            )
    if item.spatial_relationship == "inside":
        support_bounds = normalized_bounds(support)
        item_bounds = normalized_bounds(item)
        if item.z <= support.z:
            findings.append(
                _finding(
                    "inside_depth_invalid",
                    "Object inside a support must sit above the support in z-depth.",
                    object_id=item.object_id,
                    support_object_id=support.object_id,
                )
            )
        if item.must_remain_inside_support_bounds and not support_bounds.contains(item_bounds):
            findings.append(
                _finding(
                    "inside_bounds_invalid",
                    "Object marked inside must remain inside support bounds.",
                    object_id=item.object_id,
                    support_object_id=support.object_id,
                )
            )
    if item.relative_depth_rule == "above_support" and item.z <= support.z:
        findings.append(
            _finding(
                "above_support_depth_invalid",
                "Object marked above_support must have higher z than support.",
                object_id=item.object_id,
                support_object_id=support.object_id,
            )
        )
    if item.relative_depth_rule == "same_plane" and abs(item.z - support.z) > 0.12:
        findings.append(
            _finding(
                "same_plane_depth_invalid",
                "Object marked same_plane is too far from support z-depth.",
                object_id=item.object_id,
                support_object_id=support.object_id,
            )
        )


def _check_hero_relationship(
    item: ReelTimelineObject,
    hero: ReelTimelineObject,
    findings: list[RelationshipLayoutFinding],
) -> None:
    if item.relative_depth_rule == "behind_hero" and item.z > hero.z:
        findings.append(
            _finding(
                "behind_hero_depth_invalid",
                "Object marked behind_hero cannot have higher z than the hero.",
                object_id=item.object_id,
                hero_object_id=hero.object_id,
            )
        )
    if item.role == "background_reveal":
        ratio = overlap_ratio(item, hero)
        max_hero_overlap = _background_reveal_max_hero_overlap(item)
        if item.z >= hero.z:
            findings.append(
                _finding(
                    "background_reveal_depth_invalid",
                    "Background reveal must stay behind the hero in z-depth.",
                    object_id=item.object_id,
                    hero_object_id=hero.object_id,
                    z=item.z,
                    hero_z=hero.z,
                    problem=(
                        f"{item.object_id} is visually in front of or level with "
                        f"hero_subject {hero.object_id}."
                    ),
                    failure_code="background_reveal_depth_invalid",
                )
            )
        if ratio > max_hero_overlap:
            findings.append(
                _finding(
                    "background_reveal_overlaps_hero",
                    "Background reveal overlaps the hero above the safe threshold.",
                    object_id=item.object_id,
                    hero_object_id=hero.object_id,
                    overlap_ratio=round(ratio, 4),
                    max_overlap_ratio=max_hero_overlap,
                    problem=f"{item.object_id} overlaps hero_subject by {ratio:.2f}.",
                    suggested_fix=(
                        "Move it to upper-right/upper-left background, reduce scale/opacity, "
                        "lower z, or reject it."
                    ),
                    failure_code="background_reveal_overlaps_hero",
                )
            )
        region_problem = _background_reveal_region_problem(item)
        if region_problem is not None:
            findings.append(
                _finding(
                    "background_reveal_region_invalid",
                    "Background reveal violates declared screen-region constraints.",
                    object_id=item.object_id,
                    x=item.x,
                    y=item.y,
                    preferred_screen_regions=item.preferred_screen_regions,
                    forbidden_screen_regions=item.forbidden_screen_regions,
                    problem=region_problem,
                    failure_code="background_reveal_region_invalid",
                )
            )


def _check_contact_shadow(
    item: ReelTimelineObject,
    scene_objects: dict[str, ReelTimelineObject],
    findings: list[RelationshipLayoutFinding],
) -> None:
    if not item.support_contact_required:
        return
    if not item.contact_shadow_target_object_id:
        findings.append(
            _finding(
                "missing_contact_shadow_target",
                "Contact-shadow-required object has no target object.",
                object_id=item.object_id,
            )
        )
        return
    if item.contact_shadow_target_object_id not in scene_objects:
        findings.append(
            _finding(
                "contact_shadow_target_not_found",
                "contact_shadow_target_object_id must reference an object in the same scene.",
                object_id=item.object_id,
                contact_shadow_target_object_id=item.contact_shadow_target_object_id,
            )
        )
    shadow_spec = _extra_mapping(item, "shadow_spec")
    if shadow_spec and not bool(shadow_spec.get("contact_shadow_required", False)):
        findings.append(
            _finding(
                "contact_shadow_not_enabled",
                "Renderer received a contact target but shadow_spec does not require contact shadow.",
                object_id=item.object_id,
            )
        )


def _needs_support(item: ReelTimelineObject) -> bool:
    return item.spatial_relationship in {"on_surface", "inside", "attached_to", "overlay_on"}


def _extra_mapping(item: ReelTimelineObject, key: str) -> dict[str, Any]:
    value = (item.model_extra or {}).get(key)
    return dict(value) if isinstance(value, dict) else {}


def _visual_priority(item: ReelTimelineObject) -> float:
    area = item.width_normalised * item.height_normalised * item.scale * item.scale
    duration = max(0.0, item.end_time - item.start_time)
    return (item.z * 0.25) + (area * 0.4) + (item.opacity * 0.2) + (duration * 0.015)


def _background_reveal_max_hero_overlap(item: ReelTimelineObject) -> float:
    if item.max_overlap_ratio >= 1.0:
        return 0.1
    return item.max_overlap_ratio


def _background_reveal_region_problem(item: ReelTimelineObject) -> str | None:
    if item.preferred_screen_regions and not any(
        _point_in_screen_region(item.x, item.y, region)
        for region in item.preferred_screen_regions
    ):
        return (
            f"{item.object_id} is outside preferred regions "
            f"{', '.join(item.preferred_screen_regions)}."
        )
    if item.forbidden_screen_regions and any(
        _background_reveal_forbidden_region_hit(item, region)
        for region in item.forbidden_screen_regions
    ):
        return (
            f"{item.object_id} is inside forbidden regions "
            f"{', '.join(item.forbidden_screen_regions)}."
        )
    return None


def _background_reveal_forbidden_region_hit(item: ReelTimelineObject, region: str) -> bool:
    normalized = region.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized == "full_frame":
        bounds = normalized_bounds(item)
        return bounds.area >= 0.72
    return _point_in_screen_region(item.x, item.y, region)


def _point_in_screen_region(x: float, y: float, region: str) -> bool:
    normalized = region.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized == "full_frame":
        return True
    if normalized in {"background", "rear", "background_rear"}:
        return y <= 0.62
    if normalized == "side":
        return x <= 0.35 or x >= 0.65
    if normalized in {"upper", "top"}:
        return y <= 0.4
    if normalized in {"lower", "bottom"}:
        return y >= 0.6
    if normalized in {"left", "background_left"}:
        return x <= 0.4
    if normalized in {"right", "background_right"}:
        return x >= 0.6
    if normalized in {"upper_left", "top_left"}:
        return x <= 0.45 and y <= 0.45
    if normalized in {"upper_right", "top_right"}:
        return x >= 0.55 and y <= 0.45
    if normalized in {"lower_left", "bottom_left"}:
        return x <= 0.45 and y >= 0.55
    if normalized in {"lower_right", "bottom_right"}:
        return x >= 0.55 and y >= 0.55
    if normalized in {"center", "middle"}:
        return 0.35 <= x <= 0.65 and 0.35 <= y <= 0.65
    return True


def _finding(
    code: str,
    message: str,
    **details: Any,
) -> RelationshipLayoutFinding:
    return RelationshipLayoutFinding(
        code=code,
        severity="fail",
        message=message,
        details=details,
    )


def _warn(
    code: str,
    message: str,
    **details: Any,
) -> RelationshipLayoutFinding:
    return RelationshipLayoutFinding(
        code=code,
        severity="warn",
        message=message,
        details=details,
    )


__all__ = [
    "RelationshipLayoutFinding",
    "RelationshipLayoutReport",
    "RelationshipSeverity",
    "enforce_relationship_layout",
    "object_bounds",
]
