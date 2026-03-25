"""Deterministic phase-1 creative director."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from content_lab_creative.persona import PageMetadata, PersonaProfile
from content_lab_creative.types import (
    ApplicablePolicyState,
    CreativeMode,
    DirectorPlanInput,
    DirectorSelectionTrace,
    PlannedCreativeBrief,
    PolicyModeRatios,
    PolicyStateDocument,
    PolicyStatePatch,
)

_MODE_ORDER: tuple[CreativeMode, ...] = (
    CreativeMode.EXPLOIT,
    CreativeMode.EXPLORE,
    CreativeMode.MUTATION,
    CreativeMode.CHAOS,
)
_MODE_GOALS: dict[CreativeMode, str] = {
    CreativeMode.EXPLOIT: "Double down on a proven angle with crisp execution.",
    CreativeMode.EXPLORE: "Test a fresh angle that still fits the page persona.",
    CreativeMode.MUTATION: "Remix a familiar idea with a new framing or structure.",
    CreativeMode.CHAOS: "Push into a surprising but still policy-safe concept.",
}
_FALLBACK_CONTENT_PILLAR = "general"


def _deep_merge_state(
    base: dict[str, Any],
    overlay: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = deepcopy(base)
    if overlay is None:
        return merged

    for key, value in overlay.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_state(existing, value)
            continue
        merged[key] = deepcopy(value)
    return merged


def stable_bucket(seed_material: str) -> float:
    """Convert a stable seed string into a deterministic selection bucket."""

    digest = hashlib.sha256(seed_material.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big") / 2**64


def resolve_policy_state(
    *,
    global_policy: PolicyStateDocument | None = None,
    page_policy: PolicyStatePatch | PolicyStateDocument | None = None,
) -> ApplicablePolicyState:
    """Resolve the effective policy state for a page-level planning call."""

    global_document = global_policy or PolicyStateDocument()
    page_payload = None
    if page_policy is not None:
        page_payload = page_policy.model_dump(mode="json", exclude_none=True)

    effective_payload = _deep_merge_state(
        global_document.model_dump(mode="json"),
        page_payload,
    )
    return ApplicablePolicyState(
        global_policy=global_document,
        page_policy=page_policy,
        effective_policy=PolicyStateDocument.model_validate(effective_payload),
    )


def select_mode_from_bucket(
    mode_ratios: PolicyModeRatios,
    *,
    bucket: float,
) -> CreativeMode:
    """Select a mode by walking the weighted ratio buckets."""

    if bucket < 0.0 or bucket > 1.0:
        raise ValueError("bucket must be between 0.0 and 1.0")

    cumulative = 0.0
    for mode in _MODE_ORDER:
        cumulative += getattr(mode_ratios, mode.value)
        if bucket < cumulative or mode is _MODE_ORDER[-1]:
            return mode
    return _MODE_ORDER[-1]


def _content_pillars(page_metadata: PageMetadata) -> tuple[str, ...]:
    persona = page_metadata.persona
    if persona is None or not persona.content_pillars:
        return (_FALLBACK_CONTENT_PILLAR,)
    return tuple(persona.content_pillars)


def _brief_tone(persona: PersonaProfile | None) -> str:
    if persona is None or not persona.brand_tone:
        return "neutral"
    return ", ".join(persona.brand_tone[:2])


def _brief_tags(
    *,
    selected_mode: CreativeMode,
    content_pillar: str,
    persona: PersonaProfile | None,
) -> list[str]:
    tags = [selected_mode.value, _slugify(content_pillar)]
    if persona is not None:
        tags.extend(_slugify(tone) for tone in persona.brand_tone[:2])

    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if not tag or tag in seen:
            continue
        seen.add(tag)
        normalized.append(tag)
    return normalized


def _slugify(value: str) -> str:
    fragments = []
    for char in value.strip().lower():
        fragments.append(char if char.isalnum() else "-")
    return "-".join(part for part in "".join(fragments).split("-") if part)


def _seed_material(request: DirectorPlanInput, *, content_pillar: str) -> str:
    persona = request.page_metadata.persona
    payload = {
        "page_name": request.page_name,
        "persona_label": None if persona is None else persona.label,
        "audience": None if persona is None else persona.audience,
        "content_pillar": content_pillar,
        "brief_index": request.brief_index,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _title(page_name: str, *, content_pillar: str, selected_mode: CreativeMode) -> str:
    normalized_pillar = content_pillar.strip() or _FALLBACK_CONTENT_PILLAR
    return f"{page_name}: {normalized_pillar} ({selected_mode.value})"


def _description(
    *,
    page_name: str,
    content_pillar: str,
    selected_mode: CreativeMode,
    persona: PersonaProfile | None,
) -> str:
    audience = "the target audience" if persona is None else persona.audience
    return (
        f"Create a {selected_mode.value} reel for {page_name} focused on {content_pillar} "
        f"for {audience}."
    )


class PhaseOneDirector:
    """Deterministic planner for phase-1 persona- and policy-aware briefs."""

    def plan(self, request: DirectorPlanInput) -> PlannedCreativeBrief:
        """Produce a stable structured brief from page persona and policy state."""

        policy = resolve_policy_state(
            global_policy=request.global_policy,
            page_policy=request.page_policy,
        )
        page_metadata = request.page_metadata
        persona = page_metadata.persona
        content_pillars = _content_pillars(page_metadata)
        content_pillar = content_pillars[request.brief_index % len(content_pillars)]
        seed_material = _seed_material(request, content_pillar=content_pillar)
        bucket = stable_bucket(seed_material)
        selected_mode = select_mode_from_bucket(
            policy.effective_policy.mode_ratios,
            bucket=bucket,
        )
        primary_call_to_action = None
        if page_metadata.constraints.allow_direct_cta and persona is not None:
            primary_call_to_action = persona.primary_call_to_action

        return PlannedCreativeBrief(
            title=_title(
                request.page_name,
                content_pillar=content_pillar,
                selected_mode=selected_mode,
            ),
            description=_description(
                page_name=request.page_name,
                content_pillar=content_pillar,
                selected_mode=selected_mode,
                persona=persona,
            ),
            target_platforms=list(request.target_platforms),
            tone=_brief_tone(persona),
            duration_seconds=request.duration_seconds,
            tags=_brief_tags(
                selected_mode=selected_mode,
                content_pillar=content_pillar,
                persona=persona,
            ),
            page_name=request.page_name,
            page_metadata=page_metadata,
            persona_label=None if persona is None else persona.label,
            audience=None if persona is None else persona.audience,
            content_pillar=content_pillar,
            selected_mode=selected_mode,
            narrative_goal=_MODE_GOALS[selected_mode],
            primary_call_to_action=primary_call_to_action,
            constraints=page_metadata.constraints,
            policy=policy,
            selection_trace=DirectorSelectionTrace(
                brief_index=request.brief_index,
                seed_material=seed_material,
                seed_bucket=bucket,
                selected_mode=selected_mode,
                mode_weights=policy.effective_policy.mode_ratios,
            ),
        )


def plan_creative_brief(request: DirectorPlanInput) -> PlannedCreativeBrief:
    """Convenience wrapper for phase-1 brief planning."""

    return PhaseOneDirector().plan(request)


__all__ = [
    "PhaseOneDirector",
    "plan_creative_brief",
    "resolve_policy_state",
    "select_mode_from_bucket",
    "stable_bucket",
]
