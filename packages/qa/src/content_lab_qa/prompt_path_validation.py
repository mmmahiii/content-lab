"""Prompt-path motion/sensory claim validation against asset capabilities."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from content_lab_creative.planning_schema import CinematicReelPlan

_PHYSICAL_PROCESS_CLAIM_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bchopp(?:ing|ed|s)?\b"), "chopping"),
    (re.compile(r"\bpour(?:ing|s|ed)?\b"), "pouring liquid"),
    (re.compile(r"\bdrip(?:ping|s|ped)?\b"), "dripping liquid"),
    (re.compile(r"\bdrizzl(?:ing|e|ed)?\b"), "drizzling liquid"),
    (re.compile(r"\bbubbl(?:ing|es|ed)?\b"), "bubbling liquid"),
)

_SENSORY_HEAT_OR_SOUND_CLAIM_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsizzl(?:ing|e|ed|es)?\b"), "sizzling"),
    (re.compile(r"\bsteam(?:ing|y)?\b"), "steam"),
)


def collect_cinematic_plan_language(plan: CinematicReelPlan) -> str:
    """Flatten planner-visible prose for conservative vocabulary scans."""

    chunks: list[str] = []
    chunks.append(plan.page_context_summary.lower())
    if plan.content_goal:
        chunks.append(plan.content_goal.lower())

    arc = plan.narrative_arc
    chunks.extend(
        [
            arc.hook.lower(),
            arc.development.lower(),
            arc.reveal_payoff.lower(),
            arc.closing_retention_loop.lower(),
        ]
    )

    for scene in plan.scenes:
        chunks.append(scene.purpose.lower())
        chunks.append(scene.emotional_intent.lower())
        if scene.transition_in:
            chunks.append(scene.transition_in.lower())
        if scene.transition_out:
            chunks.append(scene.transition_out.lower())
        for caption in scene.captions:
            chunks.append(caption.text.lower())
        for obj in scene.objects:
            chunks.append(obj.realism_reason.lower())
            chunks.append(obj.asset_label.lower())
            chunks.append(obj.relationship_reason.lower())
        for audio in scene.audio_layers:
            chunks.append(audio.audio_id.lower())

    chunks.extend(note.lower() for note in plan.render_notes)
    chunks.append(plan.global_camera_style.lower())
    chunks.append(plan.global_lighting_style.lower())
    chunks.append(plan.caption_strategy.lower())
    chunks.append(plan.audio_strategy.lower())

    for layer in plan.audio_plan.layers:
        chunks.append(layer.audio_id.lower())

    for moment in plan.audio_plan.sensory_moments:
        chunks.append(moment.lower())

    return " ".join(chunks)


def validate_prompt_path_motion_claims(
    plan: CinematicReelPlan,
    *,
    aggregate: Mapping[str, Any],
) -> list[Any]:
    """Return realism findings when prose implies motion or sensory evidence the bank cannot support."""

    from content_lab_qa.plan_realism import PlanRealismFinding

    physical_ok = bool(aggregate.get("physical_motion_claim_evidence"))
    sensory_ok = bool(aggregate.get("sensory_hook_evidence"))

    text = collect_cinematic_plan_language(plan)
    findings: list[Any] = []

    matched_physical_labels: list[str] = []
    if not physical_ok:
        for pattern, label in _PHYSICAL_PROCESS_CLAIM_PATTERNS:
            if pattern.search(text):
                matched_physical_labels.append(label)
        if matched_physical_labels:
            findings.append(
                PlanRealismFinding(
                    code="prompt_path_impossible_physical_motion_claim",
                    severity="fail",
                    message=(
                        "Plan language implies physical process motion, but selected assets cannot "
                        "render physical cooking, cutting, or liquid motion."
                    ),
                    scene_id=None,
                    details={"matched_terms": sorted(set(matched_physical_labels))},
                    suggested_fix=(
                        "Rewrite scene intent using camera moves, opacity, and scale only, "
                        "or select video / motion-flagged assets."
                    ),
                )
            )

    matched_sensory_labels: list[str] = []
    if not sensory_ok:
        for pattern, label in _SENSORY_HEAT_OR_SOUND_CLAIM_PATTERNS:
            if pattern.search(text):
                matched_sensory_labels.append(label)
        if matched_sensory_labels:
            findings.append(
                PlanRealismFinding(
                    code="prompt_path_impossible_sensory_claim",
                    severity="fail",
                    message=(
                        "Plan language implies heat/sound/atmosphere, but selected assets lack "
                        "sensory evidence (video, audio, atmospheric overlay, motion, explicit "
                        "sensory metadata, or an allowed sensory placeholder override)."
                    ),
                    scene_id=None,
                    details={"matched_terms": sorted(set(matched_sensory_labels))},
                    suggested_fix=(
                        "Remove heat/sizzle/steam claims or add sensory-capable assets / metadata "
                        "overrides that justify them."
                    ),
                )
            )

    return findings


__all__ = [
    "collect_cinematic_plan_language",
    "validate_prompt_path_motion_claims",
]
