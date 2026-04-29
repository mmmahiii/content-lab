"""Filter invalid caption text before packaging; shared with script generation."""

from __future__ import annotations

import re
from typing import Any

from content_lab_creative.copy_lint import CopyLintMatch, evaluate_user_facing_text
from content_lab_creative.types import CaptionVariant, CaptionVariantName, GeneratedScriptOutput

CaptionPackagingResult = dict[str, Any]


def caption_copy_has_severity_fail(text: str) -> bool:
    return any(m.severity == "fail" for m in evaluate_user_facing_text(text, caption_scoped=True))


def lint_caption_for_packaging(
    text: str,
) -> list[CopyLintMatch]:
    """All copy-lint matches for a caption (caption-scoped and global copy rules)."""

    return evaluate_user_facing_text(text, caption_scoped=True)


def prefilter_caption_lint_table(
    variants: list[CaptionVariant],
) -> list[dict[str, Any]]:
    """Per-variant lint (used for trace) before any filtering or fallback."""

    rows: list[dict[str, Any]] = []
    for cv in variants:
        matches = lint_caption_for_packaging(cv.text)
        rows.append(
            {
                "variant": cv.variant.value,
                "match_count": len(matches),
                "has_fail": any(m.severity == "fail" for m in matches),
                "has_warn": any(m.severity == "warn" for m in matches),
                "matches": [_copy_match_to_json(m) for m in matches],
            }
        )
    return rows


def _copy_match_to_json(m: CopyLintMatch) -> dict[str, str]:
    return {
        "code": m.code,
        "category": m.category,
        "severity": m.severity,
        "message": m.message,
        "matched_text": m.matched_text,
    }


def apply_caption_packaging(
    output: GeneratedScriptOutput,
) -> tuple[GeneratedScriptOutput, CaptionPackagingResult]:
    """Drop copy-invalid captions; if none remain, insert a safe fallback. Always leaves ≥1 variant."""

    original = list(output.caption_variants)
    prefilter = prefilter_caption_lint_table(original)
    kept: list[CaptionVariant] = []
    dropped: list[dict[str, Any]] = []
    for cv in original:
        if caption_copy_has_severity_fail(cv.text):
            dropped.append(
                {
                    "variant": cv.variant.value,
                    "text_preview": _clip(cv.text, 200),
                }
            )
        else:
            kept.append(cv)
    used_fallback = False
    if not kept:
        fallback_text = _safe_fallback_caption_text(output)
        if caption_copy_has_severity_fail(fallback_text):
            fallback_text = "Save this move for the next time you need it."
        kept = [CaptionVariant(variant=CaptionVariantName.SHORT, text=fallback_text)]
        used_fallback = True
    return output.model_copy(update={"caption_variants": kept}), {
        "action": "caption_packaging",
        "prefilter_caption_lint": prefilter,
        "dropped": dropped,
        "kept_variants": [c.variant.value for c in kept],
        "dropped_count": len(dropped),
        "used_fallback_caption": used_fallback,
    }


def _clip(text: str, max_len: int) -> str:
    t = " ".join(text.split())
    return t if len(t) <= max_len else t[: max_len - 1] + "…"


def _safe_fallback_caption_text(output: GeneratedScriptOutput) -> str:
    """Template-only copy without planner/test tokens (verified against copy-lint in caller)."""
    base = re.sub(r"[\r\n\t]+", " ", output.brief_title or "this reel", flags=re.IGNORECASE).strip()
    return f"{base} — a simple reset you can use today. Save for next time you need it."


__all__ = [
    "apply_caption_packaging",
    "caption_copy_has_severity_fail",
    "lint_caption_for_packaging",
    "prefilter_caption_lint_table",
]
