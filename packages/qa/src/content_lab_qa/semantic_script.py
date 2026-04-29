"""Semantic script QA that evaluates content quality beyond format checks.

Format QA ensures the final media has the right resolution, duration, and audio.
Semantic QA evaluates whether the underlying *creative* — hook, scene coherence,
overlays, CTA proportion, and absence of meta filler — is actually worth posting.
It is intentionally independent of :mod:`content_lab_qa.format` and the creative
package; inputs are accepted as plain mappings so the gate can be invoked from
orchestration, API tooling, or tests without pulling in heavy dependencies.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from content_lab_core.types import QAVerdict
from content_lab_qa.gate import QAResult

SemanticFindingOutcome = Literal["warn", "fail"]

SEMANTIC_SCRIPT_GATE_NAME = "semantic_script"

_MIN_HOOK_WORD_COUNT = 4
_THIN_HOOK_WORD_COUNT = 3
_DANGLING_HOOK_ENDINGS = frozenset(
    {
        "a",
        "an",
        "and",
        "because",
        "but",
        "for",
        "from",
        "if",
        "in",
        "of",
        "or",
        "so",
        "that",
        "the",
        "to",
        "when",
        "with",
    }
)
_META_FAIL_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "meta_placeholder",
        re.compile(
            r"\b(insert (the )?hook|write (the )?hook|todo|placeholder|"
            r"hook text(?! ?:)|overlay text(?! ?:)|caption text|lorem ipsum)\b",
            re.IGNORECASE,
        ),
        "Copy contains placeholder or meta instructions instead of viewer-facing content.",
    ),
    (
        "meta_generation_language",
        re.compile(
            r"\b(plain[- ]language step|planner language|generation process|"
            r"script package|short[- ]form reel|packaged as|caption plan|"
            r"hashtags ready|overlay plan|fresh angle)\b",
            re.IGNORECASE,
        ),
        "Copy references script-generation artifacts rather than the reel subject.",
    ),
    (
        "internal_qa_copy",
        re.compile(
            r"\b(smoke test page|create a explore)\b",
            re.IGNORECASE,
        ),
        "Copy reads like internal QA scaffolding or broken template grammar rather than viewer-ready packaging.",
    ),
)
_META_WARN_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "abstract_script_language",
        re.compile(
            r"\b(proof beat|ending beat|workflow step|viewer-facing|content pillar)\b",
            re.IGNORECASE,
        ),
        "Copy uses abstract planning vocabulary rather than concrete viewer language.",
    ),
)
_CTA_PATTERN = re.compile(
    r"\b(follow|follow us|subscribe|comment below|comment if|share this|share if|"
    r"save this|save for later|shop now|link in bio|bio link|learn more|"
    r"sign up|download|tap (the )?follow|what should we cover next|hit (the )?like)\b",
    re.IGNORECASE,
)
_DISCLOSURE_PATTERN = re.compile(
    r"\b(results vary|sponsored|paid partnership|ad )\b",
    re.IGNORECASE,
)
_GENERIC_OVERLAY_PHRASES = frozenset(
    {
        "wow",
        "ok",
        "okay",
        "cool",
        "nice",
        "yes",
        "yay",
        "amazing",
        "incredible",
        "mind blown",
        "watch this",
        "look",
        "facts",
        "so true",
        "trust me",
        "listen up",
    }
)
_MIN_OVERLAY_WORD_COUNT_WARN = 3
_LOW_INFO_OVERLAY_RATIO = 0.6
_DUPLICATE_OVERLAY_RATIO = 0.5
_CTA_HEAVY_RATIO = 0.5
_MIN_CONTENT_BEATS_FOR_CTA_HEAVY = 2
_MIN_WORD_RE = re.compile(r"[A-Za-z0-9']+")


class SemanticScriptQARequest(BaseModel):
    """Input envelope for the semantic script QA gate.

    All fields are accepted as loose mappings so callers can pass
    ``GeneratedScriptOutput.model_dump()`` style payloads directly alongside
    the compiled ``ScenePlanOutput`` and ``PlannedCreativeBrief`` payloads.
    ``overlays`` overrides the overlay list extracted from ``script`` when
    callers want to validate a stand-alone overlay timeline.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    script: Mapping[str, Any] = Field(default_factory=dict)
    scene_plan: Mapping[str, Any] | None = None
    overlays: Sequence[Mapping[str, Any]] | None = None
    brief: Mapping[str, Any] | None = None


class SemanticScriptFinding(BaseModel):
    """A single semantic finding with a stable machine code and operator message."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=80)
    outcome: SemanticFindingOutcome
    field_path: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=280)
    snippet: str = Field(default="", max_length=280)
    details: dict[str, Any] = Field(default_factory=dict)


class SemanticScriptQAReport(BaseModel):
    """Structured semantic QA output suitable for run summaries and operator UI."""

    model_config = ConfigDict(extra="forbid")

    gate_name: Literal["semantic_script"] = "semantic_script"
    verdict: QAVerdict
    message: str = ""
    findings: list[SemanticScriptFinding] = Field(default_factory=list)
    failure_reasons: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.verdict in (QAVerdict.PASS, QAVerdict.SKIP)

    def as_qa_result(self) -> QAResult:
        return QAResult(
            gate_name=self.gate_name,
            verdict=self.verdict,
            message=self.message,
            details={
                "findings": [finding.model_dump(mode="json") for finding in self.findings],
                "failure_reasons": list(self.failure_reasons),
            },
        )


def evaluate_semantic_script(
    request: SemanticScriptQARequest | Mapping[str, Any],
) -> SemanticScriptQAReport:
    """Evaluate semantic quality of a script/overlay/scene plan bundle.

    The returned report never raises on malformed input — it produces a
    ``FAIL`` finding describing what was missing or unusable so the gate can
    be used in robust production pipelines without heavy pre-validation.
    """

    if isinstance(request, SemanticScriptQARequest):
        payload = request
    else:
        payload = SemanticScriptQARequest.model_validate(dict(request))

    findings: list[SemanticScriptFinding] = []

    script = dict(payload.script)
    scene_plan = dict(payload.scene_plan) if payload.scene_plan is not None else None
    brief = dict(payload.brief) if payload.brief is not None else None
    overlays = (
        list(payload.overlays)
        if payload.overlays is not None
        else _mapping_list(script.get("overlay_timeline"))
    )
    spoken_script = _mapping_list(script.get("spoken_script"))

    findings.extend(_evaluate_hook(script))
    findings.extend(_evaluate_meta_language(script, overlays=overlays))
    findings.extend(_evaluate_overlay_usefulness(overlays))
    findings.extend(_evaluate_cta_balance(spoken_script=spoken_script, overlays=overlays))
    findings.extend(
        _evaluate_scene_coherence(
            scene_plan=scene_plan,
            overlays=overlays,
            brief=brief,
            script_duration=_optional_int(script.get("duration_seconds")),
        )
    )

    verdict = _aggregate_verdict(findings)
    failure_reasons = [
        finding.message for finding in findings if finding.outcome == "fail" and finding.message
    ]
    if verdict == QAVerdict.FAIL:
        message = "; ".join(failure_reasons)
    elif verdict == QAVerdict.WARN:
        message = "; ".join(
            finding.message for finding in findings if finding.outcome == "warn" and finding.message
        )
    else:
        message = "Semantic QA passed: script, overlays, and scene plan look viewer-ready."

    return SemanticScriptQAReport(
        verdict=verdict,
        message=message,
        findings=findings,
        failure_reasons=failure_reasons,
    )


def _evaluate_hook(script: Mapping[str, Any]) -> list[SemanticScriptFinding]:
    hook_text = _optional_text(script.get("hook_text"))
    findings: list[SemanticScriptFinding] = []
    if not hook_text:
        findings.append(
            SemanticScriptFinding(
                code="missing_hook",
                outcome="fail",
                field_path="hook_text",
                message="Hook text is empty; the reel has no opening hook.",
                snippet="",
                details={"hook_text": ""},
            )
        )
        return findings

    lowered_words = _MIN_WORD_RE.findall(hook_text.lower())
    if not lowered_words:
        findings.append(
            SemanticScriptFinding(
                code="missing_hook",
                outcome="fail",
                field_path="hook_text",
                message="Hook text contains no words; the reel has no opening hook.",
                snippet=_snippet(hook_text),
                details={"hook_text": hook_text},
            )
        )
        return findings

    stripped = hook_text.rstrip()
    ends_on_colon = stripped.endswith(":")
    ends_on_connector = lowered_words[-1] in _DANGLING_HOOK_ENDINGS
    ends_on_mid_thought = bool(re.search(r"\bwho want(s)?$", stripped, re.IGNORECASE))
    if ends_on_colon or ends_on_connector or ends_on_mid_thought:
        findings.append(
            SemanticScriptFinding(
                code="incomplete_hook",
                outcome="fail",
                field_path="hook_text",
                message="Hook stops on a connector or colon rather than delivering a complete idea.",
                snippet=_snippet(hook_text),
                details={
                    "hook_text": hook_text,
                    "ends_on_colon": ends_on_colon,
                    "ends_on_connector": ends_on_connector,
                    "word_count": len(lowered_words),
                },
            )
        )
    elif len(lowered_words) < _MIN_HOOK_WORD_COUNT:
        findings.append(
            SemanticScriptFinding(
                code="incomplete_hook",
                outcome="fail",
                field_path="hook_text",
                message="Hook is too short to communicate a complete idea.",
                snippet=_snippet(hook_text),
                details={"hook_text": hook_text, "word_count": len(lowered_words)},
            )
        )
    elif len(lowered_words) < _THIN_HOOK_WORD_COUNT + 1:
        findings.append(
            SemanticScriptFinding(
                code="thin_hook",
                outcome="warn",
                field_path="hook_text",
                message="Hook is very short and may read as under-developed.",
                snippet=_snippet(hook_text),
                details={"hook_text": hook_text, "word_count": len(lowered_words)},
            )
        )

    return findings


def _evaluate_meta_language(
    script: Mapping[str, Any],
    *,
    overlays: Sequence[Mapping[str, Any]],
) -> list[SemanticScriptFinding]:
    findings: list[SemanticScriptFinding] = []
    for field_path, text in _iter_script_text_fields(script, overlays=overlays):
        for code, pattern, message in _META_FAIL_PATTERNS:
            if pattern.search(text):
                findings.append(
                    SemanticScriptFinding(
                        code=code,
                        outcome="fail",
                        field_path=field_path,
                        message=message,
                        snippet=_snippet(text),
                        details={"text": text},
                    )
                )
        for code, pattern, message in _META_WARN_PATTERNS:
            if pattern.search(text):
                findings.append(
                    SemanticScriptFinding(
                        code=code,
                        outcome="warn",
                        field_path=field_path,
                        message=message,
                        snippet=_snippet(text),
                        details={"text": text},
                    )
                )
    return findings


def _evaluate_overlay_usefulness(
    overlays: Sequence[Mapping[str, Any]],
) -> list[SemanticScriptFinding]:
    texts = [
        _optional_text(overlay.get("text"))
        for overlay in overlays
        if _optional_text(overlay.get("text")) is not None
    ]
    clean_texts = [text for text in texts if text]
    if len(clean_texts) < 2:
        return []

    findings: list[SemanticScriptFinding] = []
    generic_count = sum(1 for text in clean_texts if _is_generic_overlay(text))
    if generic_count >= 2 and generic_count / len(clean_texts) >= _LOW_INFO_OVERLAY_RATIO:
        findings.append(
            SemanticScriptFinding(
                code="low_information_overlays",
                outcome="fail",
                field_path="overlay_timeline",
                message=(
                    f"{generic_count} of {len(clean_texts)} overlays are generic filler "
                    "(e.g., 'Wow', 'Watch this') and carry no viewer value."
                ),
                snippet=_snippet(" | ".join(clean_texts)),
                details={
                    "overlay_count": len(clean_texts),
                    "generic_overlay_count": generic_count,
                    "overlays": list(clean_texts),
                },
            )
        )

    short_overlays = [
        text for text in clean_texts if _word_count(text) < _MIN_OVERLAY_WORD_COUNT_WARN
    ]
    if (
        len(short_overlays) / len(clean_texts) > _LOW_INFO_OVERLAY_RATIO
        and generic_count / len(clean_texts) < _LOW_INFO_OVERLAY_RATIO
    ):
        findings.append(
            SemanticScriptFinding(
                code="low_information_overlays",
                outcome="warn",
                field_path="overlay_timeline",
                message=(
                    f"{len(short_overlays)} of {len(clean_texts)} overlays are shorter than "
                    f"{_MIN_OVERLAY_WORD_COUNT_WARN} words; overlays may not add information."
                ),
                snippet=_snippet(" | ".join(clean_texts)),
                details={
                    "overlay_count": len(clean_texts),
                    "short_overlay_count": len(short_overlays),
                    "overlays": list(clean_texts),
                },
            )
        )

    lowered_clean = [text.lower().strip() for text in clean_texts]
    duplicates = sum(
        1 for index, lowered in enumerate(lowered_clean) if lowered in lowered_clean[:index]
    )
    if duplicates / len(clean_texts) >= _DUPLICATE_OVERLAY_RATIO:
        findings.append(
            SemanticScriptFinding(
                code="duplicate_overlays",
                outcome="warn",
                field_path="overlay_timeline",
                message=(
                    f"{duplicates} of {len(clean_texts)} overlays repeat earlier overlays; "
                    "consider varying the on-screen text."
                ),
                snippet=_snippet(" | ".join(clean_texts)),
                details={
                    "overlay_count": len(clean_texts),
                    "duplicate_overlay_count": duplicates,
                },
            )
        )

    return findings


def _evaluate_cta_balance(
    *,
    spoken_script: Sequence[Mapping[str, Any]],
    overlays: Sequence[Mapping[str, Any]],
) -> list[SemanticScriptFinding]:
    spoken_lines = [
        text for text in (_optional_text(beat.get("narration")) for beat in spoken_script) if text
    ]
    if not spoken_lines:
        return [
            SemanticScriptFinding(
                code="empty_spoken_script",
                outcome="fail",
                field_path="spoken_script",
                message="Spoken script is empty; the reel has no narration beats.",
                snippet="",
                details={},
            )
        ]

    cta_lines = [line for line in spoken_lines if _is_cta(line)]
    disclosure_lines = [line for line in spoken_lines if _is_disclosure(line)]
    content_lines = [
        line for line in spoken_lines if line not in cta_lines and line not in disclosure_lines
    ]
    content_word_count = sum(_word_count(line) for line in content_lines)

    findings: list[SemanticScriptFinding] = []
    if (
        len(cta_lines) / len(spoken_lines) >= _CTA_HEAVY_RATIO
        and len(content_lines) < _MIN_CONTENT_BEATS_FOR_CTA_HEAVY
    ):
        findings.append(
            SemanticScriptFinding(
                code="cta_heavy_script",
                outcome="fail",
                field_path="spoken_script",
                message=(
                    f"{len(cta_lines)} of {len(spoken_lines)} spoken beats are CTAs with only "
                    f"{len(content_lines)} content beats; the script is CTA-heavy and under-delivers."
                ),
                snippet=_snippet(" / ".join(spoken_lines)),
                details={
                    "spoken_beat_count": len(spoken_lines),
                    "cta_beat_count": len(cta_lines),
                    "content_beat_count": len(content_lines),
                    "content_word_count": content_word_count,
                },
            )
        )
    elif content_word_count < 8:
        findings.append(
            SemanticScriptFinding(
                code="thin_content_script",
                outcome="fail",
                field_path="spoken_script",
                message=(
                    "Spoken content beats carry fewer than 8 words combined; the reel delivers "
                    "no real value."
                ),
                snippet=_snippet(" / ".join(spoken_lines)),
                details={
                    "spoken_beat_count": len(spoken_lines),
                    "cta_beat_count": len(cta_lines),
                    "content_beat_count": len(content_lines),
                    "content_word_count": content_word_count,
                },
            )
        )

    overlay_texts = [
        text for text in (_optional_text(overlay.get("text")) for overlay in overlays) if text
    ]
    if overlay_texts:
        cta_overlays = sum(1 for text in overlay_texts if _is_cta(text))
        if cta_overlays / len(overlay_texts) > _CTA_HEAVY_RATIO and cta_overlays >= 2:
            findings.append(
                SemanticScriptFinding(
                    code="cta_heavy_overlays",
                    outcome="warn",
                    field_path="overlay_timeline",
                    message=(
                        f"{cta_overlays} of {len(overlay_texts)} overlays are CTAs; on-screen "
                        "text should deliver value, not only prompts to act."
                    ),
                    snippet=_snippet(" | ".join(overlay_texts)),
                    details={
                        "overlay_count": len(overlay_texts),
                        "cta_overlay_count": cta_overlays,
                    },
                )
            )
    return findings


def _evaluate_scene_coherence(
    *,
    scene_plan: Mapping[str, Any] | None,
    overlays: Sequence[Mapping[str, Any]],
    brief: Mapping[str, Any] | None,
    script_duration: int | None,
) -> list[SemanticScriptFinding]:
    if scene_plan is None:
        return []
    scenes = _mapping_list(scene_plan.get("scenes"))
    findings: list[SemanticScriptFinding] = []
    if not scenes:
        findings.append(
            SemanticScriptFinding(
                code="empty_scene_plan",
                outcome="fail",
                field_path="scene_plan.scenes",
                message="Scene plan has no scenes; the reel has no visual structure.",
                snippet="",
                details={},
            )
        )
        return findings

    duration = _optional_int(scene_plan.get("duration_seconds")) or script_duration
    if duration is not None and duration >= 10 and len(scenes) < 3:
        findings.append(
            SemanticScriptFinding(
                code="sparse_scene_plan",
                outcome="warn",
                field_path="scene_plan.scenes",
                message=(
                    f"Scene plan covers {duration}s with only {len(scenes)} scene(s); "
                    "viewers may perceive a flat edit."
                ),
                snippet="",
                details={"duration_seconds": duration, "scene_count": len(scenes)},
            )
        )

    purposes = [_optional_text(scene.get("purpose")) or "" for scene in scenes]
    hook_scene = next(
        (scene for scene in scenes if _optional_text(scene.get("purpose")) == "hook"),
        None,
    )
    close_scene = next(
        (scene for scene in scenes if _optional_text(scene.get("purpose")) == "close"),
        None,
    )

    if hook_scene is not None:
        overlay_text = _optional_text(hook_scene.get("overlay_text"))
        overlay_role = _optional_text(hook_scene.get("overlay_role"))
        if overlay_text is None and overlay_role != "hook":
            findings.append(
                SemanticScriptFinding(
                    code="scene_missing_hook_overlay",
                    outcome="warn",
                    field_path="scene_plan.scenes[0]",
                    message=(
                        "Hook scene has no hook-oriented overlay; the opening may land with "
                        "no legible on-screen cue."
                    ),
                    snippet=_snippet(_optional_text(hook_scene.get("visual_intent")) or ""),
                    details={
                        "scene_id": _optional_text(hook_scene.get("scene_id")),
                        "overlay_role": overlay_role,
                    },
                )
            )

    brief_cta = _optional_text(brief.get("primary_call_to_action")) if brief else None
    has_cta_overlay = any(
        _is_cta(_optional_text(overlay.get("text")) or "") for overlay in overlays
    )
    if close_scene is not None and brief_cta and not has_cta_overlay:
        close_role = _optional_text(close_scene.get("overlay_role"))
        close_text = _optional_text(close_scene.get("overlay_text"))
        if close_role != "cta" and close_text is None:
            findings.append(
                SemanticScriptFinding(
                    code="scene_missing_cta_close",
                    outcome="warn",
                    field_path="scene_plan.scenes[-1]",
                    message=(
                        "Close scene has no CTA overlay even though the brief defines a primary "
                        "call to action."
                    ),
                    snippet=_snippet(brief_cta),
                    details={
                        "brief_cta": brief_cta,
                        "close_scene_role": close_role,
                    },
                )
            )

    expected_opening = purposes[0] if purposes else ""
    if expected_opening and expected_opening != "hook":
        findings.append(
            SemanticScriptFinding(
                code="scene_plan_starts_without_hook",
                outcome="fail",
                field_path="scene_plan.scenes[0]",
                message=(
                    f"Scene plan opens with '{expected_opening}' instead of a hook; the reel "
                    "lacks a dedicated opening beat."
                ),
                snippet=_snippet(expected_opening),
                details={"opening_purpose": expected_opening, "purposes": purposes},
            )
        )

    return findings


def _iter_script_text_fields(
    script: Mapping[str, Any],
    *,
    overlays: Sequence[Mapping[str, Any]],
) -> Iterable[tuple[str, str]]:
    hook = _optional_text(script.get("hook_text"))
    if hook:
        yield "hook_text", hook
    for index, beat in enumerate(_mapping_list(script.get("spoken_script"))):
        narration = _optional_text(beat.get("narration"))
        if narration:
            yield f"spoken_script[{index}].narration", narration
    for index, overlay in enumerate(overlays):
        text = _optional_text(overlay.get("text"))
        if text:
            yield f"overlay_timeline[{index}].text", text
    for index, caption in enumerate(_mapping_list(script.get("caption_variants"))):
        text = _optional_text(caption.get("text"))
        if text:
            yield f"caption_variants[{index}].text", text


def _is_generic_overlay(text: str) -> bool:
    normalized = re.sub(r"[^a-z0-9 ]+", "", text.lower()).strip()
    if not normalized:
        return True
    if normalized in _GENERIC_OVERLAY_PHRASES:
        return True
    words = normalized.split()
    return len(words) <= 1


def _is_cta(text: str) -> bool:
    return bool(_CTA_PATTERN.search(text))


def _is_disclosure(text: str) -> bool:
    return bool(_DISCLOSURE_PATTERN.search(text))


def _word_count(text: str) -> int:
    return len(_MIN_WORD_RE.findall(text))


def _aggregate_verdict(findings: Iterable[SemanticScriptFinding]) -> QAVerdict:
    has_fail = False
    has_warn = False
    for finding in findings:
        if finding.outcome == "fail":
            has_fail = True
        elif finding.outcome == "warn":
            has_warn = True
    if has_fail:
        return QAVerdict.FAIL
    if has_warn:
        return QAVerdict.WARN
    return QAVerdict.PASS


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            try:
                return int(float(value))
            except ValueError:
                return None
    return None


def _snippet(text: str) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= 280:
        return normalized
    return normalized[:277] + "..."


__all__ = [
    "SEMANTIC_SCRIPT_GATE_NAME",
    "SemanticFindingOutcome",
    "SemanticScriptFinding",
    "SemanticScriptQARequest",
    "SemanticScriptQAReport",
    "evaluate_semantic_script",
]
