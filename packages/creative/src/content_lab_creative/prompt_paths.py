"""Stackable prompt paths for the single-prompt cinematic planner."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

PROMPT_PATHS: tuple[str, ...] = (
    "sensory_hook",
    "problem_solution",
    "luxury_reveal",
    "transformation",
    "before_after",
    "curiosity_gap",
    "product_as_background_payoff",
    "object_story",
    "micro_drama",
    "satisfying_process",
    "ambient_lifestyle",
    "speed_ramp_showcase",
    "cinematic_closeup",
    "educational_overlay",
    "social_proof",
    "contrast_hook",
    "routine_sequence",
)

PROMPT_PATH_DESCRIPTIONS: Mapping[str, str] = {
    "sensory_hook": "Lead with texture, sound, motion, or appetite-level sensory evidence.",
    "problem_solution": "Show friction, then make the selected assets resolve it visually.",
    "luxury_reveal": "Use controlled pacing and polish to reveal a premium object or result.",
    "transformation": "Move from an initial state into a clearer, improved final state.",
    "before_after": "Use contrast between two states without fake screenshots or fake UI.",
    "curiosity_gap": "Delay the full meaning of the hero subject until the payoff beat.",
    "product_as_background_payoff": "Let product or brand context emerge as the final reason.",
    "object_story": "Make one physical object carry the narrative through changing context.",
    "micro_drama": "Use small tension, interruption, or anticipation without overacting.",
    "satisfying_process": "Make process motion, sequence, and completion feel rewarding.",
    "ambient_lifestyle": "Build a coherent lived-in moment with subtle product presence.",
    "speed_ramp_showcase": "Use controlled pacing changes around key motion or reveal beats.",
    "cinematic_closeup": "Prioritize close framing, depth, shadows, and tactile detail.",
    "educational_overlay": "Use sparse editable captions to clarify an idea without crowding.",
    "social_proof": "Imply credibility through result, evidence, or contextual signals.",
    "contrast_hook": "Open with immediate visual contrast or tension.",
    "routine_sequence": "Show repeatable steps in a calm, coherent temporal sequence.",
}


def normalize_prompt_paths(values: Sequence[str] | None) -> list[str]:
    """Normalize and validate prompt path names."""

    if not values:
        return []
    result: list[str] = []
    for value in values:
        normalized = "_".join(str(value).strip().lower().replace("-", "_").split())
        if not normalized:
            continue
        if normalized not in PROMPT_PATHS:
            raise ValueError(f"unknown prompt path: {value}")
        if normalized not in result:
            result.append(normalized)
    return result


def select_prompt_paths_for_context(
    *,
    page_context: Mapping[str, Any],
    selected_assets: Sequence[Mapping[str, Any]],
    content_goal: str | None = None,
    pinned_prompt_paths: Sequence[str] | None = None,
    banned_prompt_paths: Sequence[str] | None = None,
    max_paths: int = 4,
) -> list[str]:
    """Choose deterministic default paths for prompt guidance."""

    pinned = normalize_prompt_paths(pinned_prompt_paths)
    banned = set(normalize_prompt_paths(banned_prompt_paths))
    if banned.intersection(pinned):
        raise ValueError("pinned_prompt_paths and banned_prompt_paths cannot overlap")

    text = _context_text(page_context, selected_assets, content_goal).lower()
    ranked: list[str] = []
    if any(term in text for term in ("food", "kitchen", "cook", "steak", "sizzle", "steam")):
        ranked.extend(["sensory_hook", "satisfying_process", "cinematic_closeup"])
    if any(term in text for term in ("luxury", "premium", "high end", "jewelry", "watch")):
        ranked.extend(["luxury_reveal", "cinematic_closeup", "product_as_background_payoff"])
    if any(term in text for term in ("business", "saas", "service", "founder", "operations")):
        ranked.extend(["problem_solution", "educational_overlay", "social_proof"])
    if any(term in text for term in ("before", "after", "transform", "reset")):
        ranked.extend(["transformation", "before_after", "contrast_hook"])
    if any(term in text for term in ("routine", "habit", "daily")):
        ranked.append("routine_sequence")
    if any(term in text for term in ("ambient", "lifestyle", "home", "room")):
        ranked.append("ambient_lifestyle")

    ranked.extend(["curiosity_gap", "object_story", "cinematic_closeup"])
    selected: list[str] = []
    for path in [*pinned, *ranked]:
        if path in banned or path in selected:
            continue
        selected.append(path)
        if len(selected) >= max_paths:
            break
    return selected or ["cinematic_closeup"]


def _context_text(
    page_context: Mapping[str, Any],
    selected_assets: Sequence[Mapping[str, Any]],
    content_goal: str | None,
) -> str:
    parts: list[str] = [str(content_goal or "")]
    parts.extend(str(value) for value in page_context.values() if isinstance(value, str))
    for asset in selected_assets:
        parts.extend(str(value) for value in asset.values() if isinstance(value, str))
        metadata = asset.get("metadata")
        if isinstance(metadata, Mapping):
            parts.extend(str(value) for value in metadata.values() if isinstance(value, str))
    return " ".join(parts)


__all__ = [
    "PROMPT_PATHS",
    "PROMPT_PATH_DESCRIPTIONS",
    "normalize_prompt_paths",
    "select_prompt_paths_for_context",
]
