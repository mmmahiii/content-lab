"""Lint structured creative output before it reaches paid generation."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from content_lab_creative.types import GeneratedScriptOutput

CreativeLintOutcome = Literal["pass", "warn", "fail"]
CreativeLintFindingOutcome = Literal["warn", "fail"]

_FAIL_META_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "meta_plain_language_step",
        re.compile(r"\bplain[- ]language step\b", re.IGNORECASE),
        "Text describes script planning instead of final viewer-facing content.",
    ),
    (
        "meta_setup_instruction",
        re.compile(r"\b(set up|setup|core setup|name the|show the payoff)\b", re.IGNORECASE),
        "Text contains production instructions instead of final script copy.",
    ),
    (
        "meta_generation_language",
        re.compile(
            r"\b(fresh angle|persona[- ]fit|planner language|generation process|"
            r"script package|short[- ]form reel|packaged as|hook text|overlay text|"
            r"caption plan|hashtags ready)\b",
            re.IGNORECASE,
        ),
        "Text refers to generation artifacts rather than the reel subject.",
    ),
    (
        "internal_qa_copy",
        re.compile(
            r"\b(smoke test page|create a explore)\b",
            re.IGNORECASE,
        ),
        "Caption or script line reads like internal QA scaffolding or broken template grammar.",
    ),
    (
        "placeholder_hook",
        re.compile(
            r"\b(fast hook|write (the )?hook|insert hook|todo|placeholder)\b", re.IGNORECASE
        ),
        "Text contains placeholder hook language.",
    ),
)
_WARN_META_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "abstract_script_language",
        re.compile(
            r"\b(proof beat|ending beat|workflow|viewer-facing|content pillar)\b", re.IGNORECASE
        ),
        "Text uses abstract script-planning language.",
    ),
)
_DANGLING_HOOK_ENDINGS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "in",
    "of",
    "or",
    "that",
    "the",
    "to",
    "with",
}
_CTA_PATTERNS = (
    re.compile(
        r"\b(follow|subscribe|comment|share|save|shop now|link in bio|learn more|"
        r"sign up|download|what should we cover next)\b",
        re.IGNORECASE,
    ),
)
_DISCLOSURE_PATTERNS = (
    re.compile(r"\b(results vary|ad|sponsored|paid partnership)\b", re.IGNORECASE),
)


class CreativeLintFinding(BaseModel):
    """One lint finding attached to a specific generated script field."""

    model_config = ConfigDict(extra="forbid")

    outcome: CreativeLintFindingOutcome
    code: str = Field(min_length=1, max_length=80)
    field_path: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=240)
    snippet: str = Field(min_length=1, max_length=280)


class CreativeLintResult(BaseModel):
    """Structured lint result suitable for run outputs and operator surfaces."""

    model_config = ConfigDict(extra="forbid")

    findings: list[CreativeLintFinding] = Field(default_factory=list)
    checked_fields: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def outcome(self) -> CreativeLintOutcome:
        if any(finding.outcome == "fail" for finding in self.findings):
            return "fail"
        if any(finding.outcome == "warn" for finding in self.findings):
            return "warn"
        return "pass"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def passed(self) -> bool:
        return self.outcome != "fail"


def lint_script_output(script: GeneratedScriptOutput | Mapping[str, Any]) -> CreativeLintResult:
    """Lint a generated script package for meta filler and weak script structure."""

    payload = (
        script.model_dump(mode="json")
        if isinstance(script, GeneratedScriptOutput)
        else dict(script)
    )
    findings: list[CreativeLintFinding] = []
    text_fields = list(_script_text_fields(payload))
    checked_fields = [field_path for field_path, _ in text_fields]

    for field_path, text in text_fields:
        findings.extend(_lint_text_field(field_path, text))

    hook_text = str(payload.get("hook_text", "")).strip()
    if hook_text:
        findings.extend(_lint_hook(hook_text))

    spoken_lines = [
        str(beat.get("narration", "")).strip()
        for beat in _mapping_list(payload.get("spoken_script"))
        if str(beat.get("narration", "")).strip()
    ]
    findings.extend(_lint_script_strength(spoken_lines))

    return CreativeLintResult(findings=findings, checked_fields=checked_fields)


def _script_text_fields(payload: Mapping[str, Any]) -> Iterable[tuple[str, str]]:
    hook = str(payload.get("hook_text", "")).strip()
    if hook:
        yield "hook_text", hook

    for index, beat in enumerate(_mapping_list(payload.get("spoken_script"))):
        narration = str(beat.get("narration", "")).strip()
        if narration:
            yield f"spoken_script[{index}].narration", narration

    for index, cue in enumerate(_mapping_list(payload.get("overlay_timeline"))):
        text = str(cue.get("text", "")).strip()
        if text:
            yield f"overlay_timeline[{index}].text", text

    for index, caption in enumerate(_mapping_list(payload.get("caption_variants"))):
        text = str(caption.get("text", "")).strip()
        if text:
            yield f"caption_variants[{index}].text", text

    for index, comment in enumerate(_mapping_list(payload.get("pinned_comments"))):
        text = str(comment.get("text", "")).strip()
        if text:
            yield f"pinned_comments[{index}].text", text


def _lint_text_field(field_path: str, text: str) -> list[CreativeLintFinding]:
    findings: list[CreativeLintFinding] = []
    for code, pattern, message in _FAIL_META_PATTERNS:
        if pattern.search(text):
            findings.append(
                CreativeLintFinding(
                    outcome="fail",
                    code=code,
                    field_path=field_path,
                    message=message,
                    snippet=_snippet(text),
                )
            )
    for code, pattern, message in _WARN_META_PATTERNS:
        if pattern.search(text):
            findings.append(
                CreativeLintFinding(
                    outcome="warn",
                    code=code,
                    field_path=field_path,
                    message=message,
                    snippet=_snippet(text),
                )
            )
    return findings


def _lint_hook(hook_text: str) -> list[CreativeLintFinding]:
    normalized = hook_text.strip()
    lowered_words = re.findall(r"[a-z0-9']+", normalized.lower())
    if not lowered_words:
        return []

    findings: list[CreativeLintFinding] = []
    if lowered_words[-1] in _DANGLING_HOOK_ENDINGS or normalized.endswith(":"):
        findings.append(
            CreativeLintFinding(
                outcome="fail",
                code="incomplete_hook",
                field_path="hook_text",
                message="Hook appears visibly incomplete or ends on a dangling connector.",
                snippet=_snippet(hook_text),
            )
        )
    if len(lowered_words) < 4:
        findings.append(
            CreativeLintFinding(
                outcome="warn",
                code="thin_hook",
                field_path="hook_text",
                message="Hook is very short and may not establish a complete idea.",
                snippet=_snippet(hook_text),
            )
        )
    if re.search(r"\bwho want(s)?$", normalized, re.IGNORECASE):
        findings.append(
            CreativeLintFinding(
                outcome="fail",
                code="incomplete_hook",
                field_path="hook_text",
                message="Hook appears to stop mid-thought.",
                snippet=_snippet(hook_text),
            )
        )
    return findings


def _lint_script_strength(spoken_lines: list[str]) -> list[CreativeLintFinding]:
    if not spoken_lines:
        return []

    cta_or_disclosure_count = sum(1 for line in spoken_lines if _is_cta_or_disclosure(line))
    content_lines = [line for line in spoken_lines if not _is_cta_or_disclosure(line)]
    content_word_count = sum(len(re.findall(r"[a-z0-9']+", line.lower())) for line in content_lines)
    if cta_or_disclosure_count >= max(2, len(spoken_lines) - 1) or content_word_count < 8:
        return [
            CreativeLintFinding(
                outcome="fail",
                code="cta_only_script",
                field_path="spoken_script",
                message="Script is mostly CTA/disclosure text and lacks enough content beats.",
                snippet=_snippet(" / ".join(spoken_lines)),
            )
        ]
    return []


def _is_cta_or_disclosure(text: str) -> bool:
    return any(pattern.search(text) for pattern in (*_CTA_PATTERNS, *_DISCLOSURE_PATTERNS))


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _snippet(text: str) -> str:
    normalized = " ".join(text.split())
    return normalized[:277] + "..." if len(normalized) > 280 else normalized


__all__ = [
    "CreativeLintFinding",
    "CreativeLintFindingOutcome",
    "CreativeLintOutcome",
    "CreativeLintResult",
    "lint_script_output",
]
