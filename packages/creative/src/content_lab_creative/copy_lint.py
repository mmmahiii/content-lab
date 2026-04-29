"""Central user-facing copy lint registry (exact / contains / regex) with categories.

All consumer-facing string checks for meta/system leakage should be added here so
creative generation, QA, and any other packages share one engine.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

CopyLintCategory = Literal[
    "meta_generation_language",
    "internal_entities",
    "mode_labels",
    "system_descriptions",
    "test_scaffold_language",
]
CopyLintMatchScope = Literal["all", "caption_only"]
CopyLintRuleKind = Literal["regex", "contains", "exact"]
CopyLintSeverity = Literal["fail", "warn"]


@dataclass(frozen=True, slots=True)
class CopyRuleDef:
    """Static definition; compiled to ``_ResolvedCopyRule`` at import time."""

    code: str
    category: CopyLintCategory
    kind: CopyLintRuleKind
    pattern: str
    message: str
    scope: CopyLintMatchScope = "all"
    severity: CopyLintSeverity = "fail"
    # When True, ``exact``/``contains`` use casefolded text; ``regex`` uses re.IGNORECASE.
    case_insensitive: bool = True


@dataclass(frozen=True, slots=True)
class CopyLintMatch:
    """One rule hit (structured result for API consumers)."""

    code: str
    category: CopyLintCategory
    severity: CopyLintSeverity
    message: str
    matched_text: str


@dataclass(frozen=True, slots=True)
class _ResolvedCopyRule:
    rule: CopyRuleDef
    pattern: re.Pattern[str] | None


def _compile_def(defn: CopyRuleDef) -> _ResolvedCopyRule:
    if defn.kind == "regex":
        flags = re.IGNORECASE if defn.case_insensitive else 0
        return _ResolvedCopyRule(rule=defn, pattern=re.compile(defn.pattern, flags))
    return _ResolvedCopyRule(rule=defn, pattern=None)


def _try_match_resolved(
    text: str,
    res: _ResolvedCopyRule,
) -> str | None:
    r = res.rule
    if r.kind == "regex":
        assert res.pattern is not None
        m = res.pattern.search(text)
        return m.group(0) if m else None
    if r.kind == "contains":
        flags = re.IGNORECASE if r.case_insensitive else 0
        m = re.search(re.escape(r.pattern), text, flags)
        return m.group(0) if m else None
    a = text.strip()
    b = r.pattern
    if r.case_insensitive:
        return a if a.casefold() == b.casefold() else None
    return a if a == b else None


def _scope_applies(res: _ResolvedCopyRule, *, field_is_caption: bool) -> bool:
    if res.rule.scope == "all":
        return True
    return field_is_caption


def _resolve_chain(defs: Sequence[CopyRuleDef]) -> tuple[_ResolvedCopyRule, ...]:
    return tuple(_compile_def(d) for d in defs)


# --- Rule registry (define once) ---------------------------------------------

USER_FACING_COPY_RULE_DEFS: tuple[CopyRuleDef, ...] = (
    # meta_generation_language — all user text fields
    CopyRuleDef(
        code="meta_plain_language_step",
        category="meta_generation_language",
        kind="regex",
        pattern=r"\bplain[- ]language step\b",
        message="Text describes script planning instead of final viewer-facing content.",
    ),
    CopyRuleDef(
        code="meta_setup_instruction",
        category="meta_generation_language",
        kind="regex",
        pattern=r"\b(set up|setup|core setup|name the|show the payoff)\b",
        message="Text contains production instructions instead of final script copy.",
    ),
    CopyRuleDef(
        code="meta_generation_language",
        category="meta_generation_language",
        kind="regex",
        pattern=(
            r"\b(fresh angle|persona[- ]fit|planner language|generation process|"
            r"script package|short[- ]form reel|packaged as|hook text|overlay text|"
            r"caption plan|hashtags ready)\b"
        ),
        message="Text refers to generation artifacts rather than the reel subject.",
    ),
    CopyRuleDef(
        code="placeholder_hook",
        category="meta_generation_language",
        kind="regex",
        pattern=r"\b(fast hook|write (the )?hook|insert hook|todo|placeholder)\b",
        message="Text contains placeholder hook language.",
    ),
    CopyRuleDef(
        code="abstract_script_language",
        category="meta_generation_language",
        kind="regex",
        pattern=r"\b(proof beat|ending beat|workflow|viewer-facing)\b",
        message="Text uses abstract script-planning language.",
        severity="warn",
    ),
    # Caption-only: internal + planner leakage (CAP-D001) mapped to categories
    CopyRuleDef(
        code="caption_meta_create_a",
        category="system_descriptions",
        kind="contains",
        pattern="Create a",
        message="Caption uses planner-style creation language.",
        scope="caption_only",
    ),
    CopyRuleDef(
        code="caption_meta_create_an",
        category="system_descriptions",
        kind="contains",
        pattern="Create an",
        message="Caption uses planner-style creation language.",
        scope="caption_only",
    ),
    CopyRuleDef(
        code="caption_meta_reel_for",
        category="internal_entities",
        kind="contains",
        pattern="reel for",
        message="Caption refers to a reel as an internal artifact.",
        scope="caption_only",
    ),
    CopyRuleDef(
        code="caption_meta_focused_on",
        category="system_descriptions",
        kind="contains",
        pattern="focused on",
        message="Caption uses instruction-style focus phrasing.",
        scope="caption_only",
    ),
    CopyRuleDef(
        code="caption_meta_smoke_test_page",
        category="test_scaffold_language",
        kind="contains",
        pattern="Smoke Test Page",
        message="Caption contains internal test/sandbox page labels.",
        scope="caption_only",
    ),
    CopyRuleDef(
        code="caption_meta_explore",
        category="mode_labels",
        kind="regex",
        pattern=r"\bexplore\b",
        message="Caption uses internal plan/explore language.",
        scope="caption_only",
    ),
    CopyRuleDef(
        code="caption_meta_exploit",
        category="mode_labels",
        kind="regex",
        pattern=r"\bexploit\b",
        message="Caption uses internal plan/exploit language.",
        scope="caption_only",
    ),
    CopyRuleDef(
        code="caption_meta_mutation",
        category="mode_labels",
        kind="regex",
        pattern=r"\bmutation\b",
        message="Caption uses internal plan/mutation language.",
        scope="caption_only",
    ),
    CopyRuleDef(
        code="caption_meta_chaos",
        category="mode_labels",
        kind="regex",
        pattern=r"\bchaos\b",
        message="Caption uses internal test/mode language.",
        scope="caption_only",
    ),
    CopyRuleDef(
        code="caption_meta_mode",
        category="mode_labels",
        kind="regex",
        pattern=r"\bmode\b",
        message="Caption uses internal test/mode language.",
        scope="caption_only",
    ),
    CopyRuleDef(
        code="caption_meta_page_persona",
        category="internal_entities",
        kind="contains",
        pattern="page persona",
        message="Caption contains page/persona planner labels.",
        scope="caption_only",
    ),
    CopyRuleDef(
        code="caption_meta_content_pillar",
        category="internal_entities",
        kind="contains",
        pattern="content pillar",
        message="Caption uses internal content-planning language.",
        scope="caption_only",
    ),
    CopyRuleDef(
        code="caption_meta_brief",
        category="internal_entities",
        kind="regex",
        pattern=r"\bbrief\b",
        message="Caption uses internal brief/plan language.",
        scope="caption_only",
    ),
    CopyRuleDef(
        code="caption_meta_variant",
        category="internal_entities",
        kind="regex",
        pattern=r"\bvariant\b",
        message="Caption uses internal variant / packaging language.",
        scope="caption_only",
    ),
    CopyRuleDef(
        code="caption_meta_hook_scene",
        category="system_descriptions",
        kind="contains",
        pattern="hook scene",
        message="Caption uses scene template labels.",
        scope="caption_only",
    ),
    CopyRuleDef(
        code="caption_meta_setup_scene",
        category="system_descriptions",
        kind="contains",
        pattern="setup scene",
        message="Caption uses scene template labels.",
        scope="caption_only",
    ),
    CopyRuleDef(
        code="caption_meta_payoff_scene",
        category="system_descriptions",
        kind="contains",
        pattern="payoff scene",
        message="Caption uses scene template labels.",
        scope="caption_only",
    ),
    CopyRuleDef(
        code="caption_meta_visual_focus",
        category="system_descriptions",
        kind="contains",
        pattern="visual focus",
        message="Caption uses production/planning focus labels.",
        scope="caption_only",
    ),
)

_COMPILED_DEFAULT: tuple[_ResolvedCopyRule, ...] = _resolve_chain(USER_FACING_COPY_RULE_DEFS)


def evaluate_user_facing_text(
    text: str,
    *,
    caption_scoped: bool = False,
    rules: Sequence[CopyRuleDef] | None = None,
) -> list[CopyLintMatch]:
    """Run the copy lint engine on a single string (caption, hook line, overlay, CTA, etc.).

    :param text: The full field text to check.
    :param caption_scoped: When True, apply ``scope=caption_only`` rules (usually caption slots).
    :param rules: Optional override (used by tests to prove exact/contains/regex with tiny samples).
    """
    compiled: tuple[_ResolvedCopyRule, ...] = (
        _resolve_chain(rules) if rules is not None else _COMPILED_DEFAULT
    )
    matches: list[CopyLintMatch] = []
    for res in compiled:
        if not _scope_applies(res, field_is_caption=caption_scoped):
            continue
        hit = _try_match_resolved(text, res)
        if not hit:
            continue
        r = res.rule
        matches.append(
            CopyLintMatch(
                code=r.code,
                category=r.category,
                severity=r.severity,
                message=r.message,
                matched_text=hit,
            )
        )
    return matches


__all__ = [
    "CopyLintCategory",
    "CopyLintMatch",
    "CopyLintMatchScope",
    "CopyLintRuleKind",
    "CopyLintSeverity",
    "CopyRuleDef",
    "USER_FACING_COPY_RULE_DEFS",
    "evaluate_user_facing_text",
]
