"""Lightweight deterministic visual prompt specificity linting."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

GENERIC_VISUAL_PHRASES = (
    "visual focus",
    "useful step",
    "concrete improvement",
    "everyday context",
    "operations action",
    "the payoff",
    "the problem",
    "show value",
    "fresh angle",
    "fits the persona",
)

REQUIRED_SCENE_FIELDS = (
    "subject",
    "setting",
    "action",
    "key_visual_object",
    "camera_framing",
)


@dataclass(frozen=True, slots=True)
class VisualPromptLintResult:
    passed: bool
    findings: tuple[str, ...]
    generic_filler_removed: bool = False
    no_legible_text_instruction_applied: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "findings": list(self.findings),
            "generic_filler_removed": self.generic_filler_removed,
            "no_legible_text_instruction_applied": self.no_legible_text_instruction_applied,
            "required_scene_fields": list(REQUIRED_SCENE_FIELDS),
        }


def lint_scene_visual_specificity(
    scene: Mapping[str, Any],
    *,
    prompt_text: str | None = None,
) -> VisualPromptLintResult:
    """Check that a scene/prompt has concrete visual execution fields."""

    findings: list[str] = []
    haystack = str(prompt_text or "").lower()
    if not haystack:
        haystack = " ".join(
            str(part or "")
            for part in (
                scene.get("visual_intent"),
                scene.get("shot_guidance"),
                scene.get("action"),
                scene.get("key_visual_object"),
            )
        ).lower()
    for phrase in GENERIC_VISUAL_PHRASES:
        if phrase in haystack:
            findings.append(f"generic_phrase:{phrase}")

    for field_name in REQUIRED_SCENE_FIELDS:
        value = str(scene.get(field_name) or "").strip()
        if not value:
            findings.append(f"missing_field:{field_name}")

    return VisualPromptLintResult(
        passed=not findings,
        findings=tuple(findings),
        generic_filler_removed=not any(
            phrase in (prompt_text or "").lower() for phrase in GENERIC_VISUAL_PHRASES
        ),
        no_legible_text_instruction_applied="no legible text" in (prompt_text or "").lower(),
    )


__all__ = [
    "GENERIC_VISUAL_PHRASES",
    "REQUIRED_SCENE_FIELDS",
    "VisualPromptLintResult",
    "lint_scene_visual_specificity",
]
