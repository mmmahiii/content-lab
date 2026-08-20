"""Deterministic scene coherence QA for cinematic reel plans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from content_lab_creative.planning_schema import CaptionPlan, CinematicReelPlan, TimelineObject
from content_lab_editing.support_surface_overlap import (
    OverlapValidationContext,
    evaluate_on_surface_support_region,
    overlap_artifacts_for_support,
    resolve_support_overlap_ratio,
)

SceneCoherenceSeverity = Literal["warn", "fail"]


@dataclass(frozen=True, slots=True)
class SceneCoherenceFinding:
    code: str
    severity: SceneCoherenceSeverity
    message: str
    scene_id: str | None
    suggested_fix: str
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "scene_id": self.scene_id,
            "suggested_fix": self.suggested_fix,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class SceneCoherenceReport:
    findings: tuple[SceneCoherenceFinding, ...]

    @property
    def passed(self) -> bool:
        return not any(finding.severity == "fail" for finding in self.findings)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "scene_coherence_qa_v1",
            "passed": self.passed,
            "findings": [finding.as_dict() for finding in self.findings],
            "failure_codes": [
                finding.code for finding in self.findings if finding.severity == "fail"
            ],
            "warning_codes": [
                finding.code for finding in self.findings if finding.severity == "warn"
            ],
        }


class SceneCoherenceValidator:
    """Validate physical and visual hierarchy rules for any cinematic niche."""

    def validate(
        self,
        plan: CinematicReelPlan,
        *,
        overlap_context: OverlapValidationContext | None = None,
    ) -> SceneCoherenceReport:
        findings: list[SceneCoherenceFinding] = []
        light_ids = {light.light_id for light in plan.lighting_shadow_plan.lights}
        self._validate_scene_timing(plan, findings)
        for scene in plan.scenes:
            objects = list(scene.objects)
            objects_by_id = {item.object_id: item for item in objects}
            heroes = [item for item in objects if item.role == "hero_subject"]
            narrative_payoffs = [item for item in objects if item.role == "narrative_payoff"]
            focal_objects = [
                item
                for item in objects
                if item.role in {"hero_subject", "narrative_payoff", scene.dominant_focal_role}
            ]
            dominant_candidates = [
                item
                for item in objects
                if item.role
                not in {"environment_base", "audio_layer", "caption_support", "transition_element"}
            ]
            dominant = max(dominant_candidates, key=_visual_priority) if dominant_candidates else None
            hero = max(heroes, key=_visual_priority) if heroes else None

            if not _is_transition_scene(
                scene.purpose,
                scene.transition_in,
                scene.transition_out,
            ) and not any(item.role == "environment_base" for item in objects):
                findings.append(
                    _finding(
                        "missing_environment_base",
                        "fail",
                        "Visual scene has no environment_base object.",
                        scene.scene_id,
                        "Add a base/environment layer before placing foreground assets.",
                    )
                )
            if len(focal_objects) != 1:
                findings.append(
                    _finding(
                        "dominant_focal_subject_count_invalid",
                        "fail",
                        "Scene must contain exactly one dominant focal object.",
                        scene.scene_id,
                        "Choose one hero_subject or narrative_payoff and demote competing objects.",
                        focal_count=len(focal_objects),
                    )
                )
            if len(heroes) > 1:
                findings.append(
                    _finding(
                        "too_many_hero_subjects",
                        "fail",
                        "Scene contains more than one hero_subject.",
                        scene.scene_id,
                        "Keep one hero_subject and mark other assets supporting_subject or reject them.",
                        hero_count=len(heroes),
                    )
                )
            if len(narrative_payoffs) > 1:
                findings.append(
                    _finding(
                        "too_many_narrative_payoffs",
                        "fail",
                        "Scene contains more than one narrative_payoff.",
                        scene.scene_id,
                        "Keep one payoff object for the scene.",
                        narrative_payoff_count=len(narrative_payoffs),
                    )
                )
            high_foreground = [item for item in objects if item.z > 0.65]
            if len(high_foreground) > 3:
                findings.append(
                    _finding(
                        "too_many_high_z_foreground_objects",
                        "fail",
                        "Too many high-depth foreground objects create collage clutter.",
                        scene.scene_id,
                        "Lower z-depth or remove extra foreground objects; keep at most three.",
                        foreground_count=len(high_foreground),
                    )
                )
            if dominant is not None and dominant.role not in {"hero_subject", "narrative_payoff"}:
                findings.append(
                    _finding(
                        "hero_not_highest_visual_priority",
                        "fail",
                        "Hero or payoff does not have the highest visual priority.",
                        scene.scene_id,
                        "Increase hero scale/z/opacity or reduce competing supporting objects.",
                        dominant_object_id=dominant.object_id,
                        dominant_role=dominant.role,
                    )
                )
            self._validate_relationships(
                scene.scene_id,
                objects,
                objects_by_id,
                hero,
                findings,
                overlap_context=overlap_context,
            )
            self._validate_caption_overlap(scene.scene_id, scene.captions, hero, findings)
            self._validate_shadows(scene.scene_id, objects, light_ids, findings)
            self._validate_static_motion(scene.scene_id, objects, findings)
        return SceneCoherenceReport(findings=tuple(findings))

    def _validate_relationships(
        self,
        scene_id: str,
        objects: list[TimelineObject],
        objects_by_id: dict[str, TimelineObject],
        hero: TimelineObject | None,
        findings: list[SceneCoherenceFinding],
        *,
        overlap_context: OverlapValidationContext | None = None,
    ) -> None:
        for item in objects:
            if (
                item.role != "atmospheric_layer"
                and item.z > 0.45
                and item.role in {"supporting_subject", "foreground_texture"}
                and not item.support_object_id
            ):
                findings.append(
                    _finding(
                        "floating_cutout_without_support",
                        "fail",
                        "Foreground cutout has no declared physical support.",
                        scene_id,
                        "Set support_object_id and spatial_relationship, or mark it atmospheric.",
                        object_id=item.object_id,
                    )
                )
            support = objects_by_id.get(item.support_object_id or "")
            if item.support_object_id and support is None:
                findings.append(
                    _finding(
                        "support_object_not_found",
                        "fail",
                        "support_object_id does not refer to an object in the same scene.",
                        scene_id,
                        "Use an object_id from the same scene as the support.",
                        object_id=item.object_id,
                        support_object_id=item.support_object_id,
                    )
                )
                continue
            if support is not None:
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
                                "fail",
                                "Support surface mask was expected but was not loaded.",
                                scene_id,
                                "Load the declared support_surface_mask_uri before render, or remove the mask requirement.",
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
                            else "Object does not meet the required overlap for its relationship."
                        )
                        suggested_fix = (
                            "Move the object onto occupied support-surface pixels, not just the bbox."
                            if failure_code == "on_surface_outside_support_region"
                            else "Move or scale the object so it visibly contacts the support."
                        )
                        findings.append(
                            _finding(
                                failure_code,
                                "fail",
                                message,
                                scene_id,
                                suggested_fix,
                                object_id=item.object_id,
                                support_object_id=support.object_id,
                                required_overlap_ratio=item.required_overlap_ratio,
                                **region.as_dict(),
                            )
                        )
                else:
                    overlap, overlap_method = resolve_support_overlap_ratio(
                        item, support, artifacts
                    )
                    if item.spatial_relationship == "inside" and overlap < item.required_overlap_ratio:
                        findings.append(
                            _finding(
                                "relationship_required_overlap_not_met",
                                "fail",
                                "Object does not meet the required overlap for its relationship.",
                                scene_id,
                                "Move or scale the object so it visibly contacts or fits the support.",
                                object_id=item.object_id,
                                support_object_id=support.object_id,
                                overlap_ratio=round(overlap, 4),
                                required_overlap_ratio=item.required_overlap_ratio,
                                overlap_method=overlap_method,
                            )
                        )
                if item.spatial_relationship == "inside" and item.z <= support.z:
                    findings.append(
                        _finding(
                            "inside_depth_invalid",
                            "fail",
                            "Object marked inside must sit above the container/support plane.",
                            scene_id,
                            "Raise object z above the support while keeping it within bounds.",
                            object_id=item.object_id,
                            support_object_id=support.object_id,
                        )
                    )
            if hero is not None and item.object_id != hero.object_id:
                if item.relative_depth_rule == "behind_hero" and item.z > hero.z:
                    findings.append(
                        _finding(
                            "behind_hero_depth_invalid",
                            "fail",
                            "Object marked behind_hero has higher z than the hero.",
                            scene_id,
                            "Lower the object's z below the hero z-depth.",
                            object_id=item.object_id,
                            hero_object_id=hero.object_id,
                        )
                    )
                if item.role == "background_reveal":
                    overlap = _overlap_ratio(item, hero)
                    max_hero_overlap = _background_reveal_max_hero_overlap(item)
                    if item.z >= hero.z:
                        findings.append(
                            _finding(
                                "background_reveal_depth_invalid",
                                "fail",
                                "Background reveal is not behind the hero in z-depth.",
                                scene_id,
                                (
                                    f"{item.object_id} has z={item.z:.2f} while hero "
                                    f"{hero.object_id} has z={hero.z:.2f}; lower z below hero, "
                                    "move it to a rear/background region, or reject it."
                                ),
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
                    if item.z > 0.45 and item.role != "narrative_payoff":
                        findings.append(
                            _finding(
                                "background_reveal_too_forward",
                                "fail",
                                "Background reveal is too far forward in z-depth.",
                                scene_id,
                                (
                                    f"{item.object_id} is at z={item.z:.2f}; lower it to rear "
                                    "depth, reduce scale/opacity, move it away from the hero, or reject it."
                                ),
                                object_id=item.object_id,
                                z=item.z,
                                problem=f"{item.object_id} is placed at foreground z-depth.",
                                failure_code="background_reveal_too_forward",
                            )
                        )
                    if overlap > max_hero_overlap:
                        findings.append(
                            _finding(
                                "background_reveal_overlaps_hero",
                                "fail",
                                "Background reveal overlaps the hero above the safe threshold.",
                                scene_id,
                                (
                                    f"{item.object_id} overlaps hero_subject by {overlap:.2f}; "
                                    "move it to upper-right/upper-left background, reduce scale/opacity, "
                                    "lower z, or reject it in provenance.rejected_assets."
                                ),
                                object_id=item.object_id,
                                hero_object_id=hero.object_id,
                                overlap_ratio=round(overlap, 4),
                                max_overlap_ratio=max_hero_overlap,
                                problem=(
                                    f"{item.object_id} overlaps hero_subject by {overlap:.2f}."
                                ),
                                failure_code="background_reveal_overlaps_hero",
                            )
                        )
                    region_problem = _background_reveal_region_problem(item)
                    if region_problem is not None:
                        findings.append(
                            _finding(
                                "background_reveal_region_invalid",
                                "fail",
                                "Background reveal is outside its declared screen-region constraints.",
                                scene_id,
                                (
                                    f"{item.object_id} violates background/rear region constraints; "
                                    "move it to an allowed background region or reject it."
                                ),
                                object_id=item.object_id,
                                x=item.x,
                                y=item.y,
                                preferred_screen_regions=item.preferred_screen_regions,
                                forbidden_screen_regions=item.forbidden_screen_regions,
                                problem=region_problem,
                                failure_code="background_reveal_region_invalid",
                            )
                        )

    def _validate_caption_overlap(
        self,
        scene_id: str,
        captions: list[CaptionPlan],
        hero: TimelineObject | None,
        findings: list[SceneCoherenceFinding],
    ) -> None:
        if hero is None:
            return
        for caption in captions:
            if not caption.safe_area_compliant:
                findings.append(
                    _finding(
                        "caption_safe_area_violation",
                        "fail",
                        "Caption is not safe-area compliant.",
                        scene_id,
                        "Move captions inside the declared safe area.",
                        caption_id=caption.caption_id,
                    )
                )
            if _caption_hero_overlap_ratio(caption, hero) > 0.02:
                findings.append(
                    _finding(
                        "caption_overlaps_hero",
                        "fail",
                        "Caption overlaps the hero bounding box.",
                        scene_id,
                        "Move caption above, below, or beside the hero subject.",
                        caption_id=caption.caption_id,
                        hero_object_id=hero.object_id,
                    )
                )

    def _validate_shadows(
        self,
        scene_id: str,
        objects: list[TimelineObject],
        light_ids: set[str],
        findings: list[SceneCoherenceFinding],
    ) -> None:
        for item in objects:
            if item.shadow_spec.enabled and item.shadow_spec.source_light_id not in light_ids:
                findings.append(
                    _finding(
                        "invalid_light_reference",
                        "fail",
                        "Object shadow references an undeclared light.",
                        scene_id,
                        "Use a source_light_id from lighting_shadow_plan.lights.",
                        object_id=item.object_id,
                        source_light_id=item.shadow_spec.source_light_id,
                    )
                )
            if item.spatial_relationship == "atmospheric" and item.shadow_spec.contact_shadow_required:
                findings.append(
                    _finding(
                        "atmospheric_contact_shadow_invalid",
                        "fail",
                        "Atmospheric objects should not require hard contact shadows.",
                        scene_id,
                        "Disable contact shadows for atmospheric or motion layers.",
                        object_id=item.object_id,
                    )
                )
            if item.support_contact_required and (
                not item.shadow_spec.enabled or not item.shadow_spec.contact_shadow_required
            ):
                findings.append(
                    _finding(
                        "missing_contact_shadow",
                        "fail",
                        "Object relationship requires a contact shadow.",
                        scene_id,
                        "Enable contact_shadow_required and target the supporting object.",
                        object_id=item.object_id,
                    )
                )
            if item.support_contact_required and not item.contact_shadow_target_object_id:
                findings.append(
                    _finding(
                        "missing_contact_shadow_target",
                        "fail",
                        "Contact-shadow-required object has no target object.",
                        scene_id,
                        "Set contact_shadow_target_object_id to the supporting surface/object.",
                        object_id=item.object_id,
                    )
                )

    def _validate_scene_timing(
        self,
        plan: CinematicReelPlan,
        findings: list[SceneCoherenceFinding],
    ) -> None:
        expected = 0.0
        for scene in sorted(plan.scenes, key=lambda candidate: candidate.start_time):
            if scene.start_time < expected - 0.001:
                findings.append(
                    _finding(
                        "scene_time_overlap",
                        "fail",
                        "Scene time ranges overlap.",
                        scene.scene_id,
                        "Adjust scene start/end times so scenes are continuous.",
                    )
                )
            if scene.start_time > expected + 0.05:
                findings.append(
                    _finding(
                        "scene_time_gap",
                        "fail",
                        "Scene time ranges leave an unintended gap.",
                        scene.scene_id,
                        "Start the scene where the previous scene ends or add a transition scene.",
                    )
                )
            expected = max(expected, scene.end_time)

    def _validate_static_motion(
        self,
        scene_id: str,
        objects: list[TimelineObject],
        findings: list[SceneCoherenceFinding],
    ) -> None:
        impossible_terms = ("deformation", "liquid", "splash", "steam", "sizzle", "chop")
        for item in objects:
            motion_type = item.motion_curve.type.lower()
            if item.role in {"atmospheric_layer", "motion_layer"}:
                continue
            if any(term in motion_type for term in impossible_terms):
                findings.append(
                    _finding(
                        "impossible_static_asset_motion",
                        "fail",
                        "Static asset motion implies unsupported physical deformation or sensory movement.",
                        scene_id,
                        "Use deterministic transforms only, or supply a true motion/atmospheric asset.",
                        object_id=item.object_id,
                        motion_type=item.motion_curve.type,
                    )
                )


def validate_scene_coherence(
    plan: CinematicReelPlan,
    *,
    overlap_context: OverlapValidationContext | None = None,
) -> SceneCoherenceReport:
    """Validate scene coherence with the default deterministic validator."""

    return SceneCoherenceValidator().validate(plan, overlap_context=overlap_context)


def _visual_priority(item: TimelineObject) -> float:
    duration = max(0.0, item.end_time - item.start_time)
    area = item.width_normalised * item.height_normalised * item.scale * item.scale
    sharpness = 1.0 - min(1.0, item.blur_spec.radius + item.blur_spec.motion_blur)
    return (
        item.z * 0.25
        + area * 0.32
        + item.opacity * 0.18
        + sharpness * 0.12
        + duration * 0.013
    )


def _bounds(item: TimelineObject) -> tuple[float, float, float, float]:
    width = item.width_normalised * item.scale
    height = item.height_normalised * item.scale
    return (
        max(0.0, item.x - width / 2),
        max(0.0, item.y - height / 2),
        min(1.0, item.x + width / 2),
        min(1.0, item.y + height / 2),
    )


def _overlap_ratio(item: TimelineObject, other: TimelineObject) -> float:
    left_a, top_a, right_a, bottom_a = _bounds(item)
    left_b, top_b, right_b, bottom_b = _bounds(other)
    overlap_width = max(0.0, min(right_a, right_b) - max(left_a, left_b))
    overlap_height = max(0.0, min(bottom_a, bottom_b) - max(top_a, top_b))
    overlap_area = overlap_width * overlap_height
    item_area = max(0.0001, (right_a - left_a) * (bottom_a - top_a))
    return overlap_area / item_area


def _background_reveal_max_hero_overlap(item: TimelineObject) -> float:
    if item.max_overlap_ratio >= 1.0:
        return 0.1
    return item.max_overlap_ratio


def _background_reveal_region_problem(item: TimelineObject) -> str | None:
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


def _background_reveal_forbidden_region_hit(item: TimelineObject, region: str) -> bool:
    normalized = region.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized == "full_frame":
        left, top, right, bottom = _bounds(item)
        return (right - left) * (bottom - top) >= 0.72
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


def _caption_hero_overlap_ratio(caption: CaptionPlan, hero: TimelineObject) -> float:
    caption_height = min(0.18, max(0.04, caption.font_size / 1080))
    caption_bounds = (
        max(0.0, caption.x - caption.max_width / 2),
        max(0.0, caption.y - caption_height / 2),
        min(1.0, caption.x + caption.max_width / 2),
        min(1.0, caption.y + caption_height / 2),
    )
    hero_bounds = _bounds(hero)
    overlap_width = max(0.0, min(caption_bounds[2], hero_bounds[2]) - max(caption_bounds[0], hero_bounds[0]))
    overlap_height = max(0.0, min(caption_bounds[3], hero_bounds[3]) - max(caption_bounds[1], hero_bounds[1]))
    overlap_area = overlap_width * overlap_height
    caption_area = max(
        0.0001,
        (caption_bounds[2] - caption_bounds[0]) * (caption_bounds[3] - caption_bounds[1]),
    )
    return overlap_area / caption_area


def _is_transition_scene(
    purpose: str,
    transition_in: str | None,
    transition_out: str | None,
) -> bool:
    text = " ".join(value or "" for value in (purpose, transition_in, transition_out)).lower()
    return "transition" in text and "environment" not in text


def _finding(
    code: str,
    severity: SceneCoherenceSeverity,
    message: str,
    scene_id: str | None,
    suggested_fix: str,
    **details: Any,
) -> SceneCoherenceFinding:
    return SceneCoherenceFinding(
        code=code,
        severity=severity,
        message=message,
        scene_id=scene_id,
        suggested_fix=suggested_fix,
        details=details,
    )


__all__ = [
    "SceneCoherenceFinding",
    "SceneCoherenceReport",
    "SceneCoherenceSeverity",
    "SceneCoherenceValidator",
    "validate_scene_coherence",
]
