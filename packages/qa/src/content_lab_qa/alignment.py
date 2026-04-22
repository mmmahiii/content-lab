"""Heuristic alignment QA: compare creative intent to script, prompts, captions, and cover timing."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from content_lab_core.types import QAVerdict
from content_lab_qa.gate import QAResult

_WORD_RE = re.compile(r"[a-z0-9']+", re.IGNORECASE)

_STOP_WORDS: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "from",
        "your",
        "you",
        "our",
        "are",
        "was",
        "has",
        "have",
        "not",
        "but",
        "its",
        "all",
        "any",
        "can",
        "get",
        "out",
        "one",
        "use",
    }
)

Severity = Literal["warn", "fail"]


class AlignmentFinding(BaseModel):
    """A single deterministic alignment issue."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=80)
    severity: Severity
    message: str = Field(min_length=1, max_length=1_200)
    details: dict[str, object] = Field(default_factory=dict)


class AlignmentQAConstraints(BaseModel):
    """Tunable thresholds for first-pass heuristics."""

    model_config = ConfigDict(extra="forbid")

    min_intent_tokens: int = Field(default=2, ge=1, le=20)
    fail_messaging_coverage: float = Field(default=0.14, ge=0.0, le=1.0)
    fail_prompt_coverage: float = Field(default=0.10, ge=0.0, le=1.0)
    warn_caption_messaging_gap: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
    )  # warn when captions trail combined hook+script by this much (ratio points)
    warn_hook_scene_prompt_gap: float = Field(default=0.12, ge=0.0, le=1.0)
    hook_cover_slack_seconds: float = Field(default=0.75, ge=0.0, le=5.0)


class AlignmentQAReport(BaseModel):
    """Structured alignment QA for flows, APIs, and package traces."""

    model_config = ConfigDict(extra="forbid")

    gate_name: str = "alignment"
    verdict: QAVerdict
    message: str = ""
    findings: tuple[AlignmentFinding, ...] = Field(default_factory=tuple)
    metrics: dict[str, object] = Field(default_factory=dict)
    lead_text: str = ""
    skipped: bool = False
    skip_reason: str = ""

    @property
    def blocks_readiness(self) -> bool:
        return self.verdict == QAVerdict.FAIL

    def as_qa_result(self) -> QAResult:
        """Serialize into the shared QA result envelope."""

        return QAResult(
            gate_name=self.gate_name,
            verdict=self.verdict,
            message=self.message,
            details={
                "gate_name": self.gate_name,
                "verdict": self.verdict.value,
                "message": self.message,
                "findings": [finding.model_dump(mode="json") for finding in self.findings],
                "warn_findings": [
                    f.model_dump(mode="json") for f in self.findings if f.severity == "warn"
                ],
                "fail_findings": [
                    f.model_dump(mode="json") for f in self.findings if f.severity == "fail"
                ],
                "metrics": dict(self.metrics),
                "lead_text": self.lead_text,
                "skipped": self.skipped,
                "skip_reason": self.skip_reason,
            },
        )


def evaluate_alignment_qa(
    *,
    brief: Mapping[str, Any],
    script: Mapping[str, Any],
    scene_plan: Mapping[str, Any],
    compiled_prompt: Mapping[str, Any],
    editing: Mapping[str, Any] | None = None,
    constraints: AlignmentQAConstraints | None = None,
) -> AlignmentQAReport:
    """Compare brief intent to script, provider prompt, captions, scene plan, and cover timing.

    This is a deterministic, token-overlap first pass. It is expected to be augmented later
    with richer, model-based checks without changing the payload shape.
    """

    effective = constraints or AlignmentQAConstraints()
    editing_payload = dict(editing or {})

    lead_text = _lead_message(brief)
    intent_tokens = _content_tokens(lead_text)
    if len(intent_tokens) < effective.min_intent_tokens:
        return AlignmentQAReport(
            verdict=QAVerdict.SKIP,
            message="Alignment QA skipped: lead message is too thin for deterministic checks.",
            findings=(),
            metrics={"intent_token_count": len(intent_tokens)},
            lead_text=lead_text,
            skipped=True,
            skip_reason="insufficient_intent",
        )

    provider_prompt = str(compiled_prompt.get("prompt", "") or "")

    hook_text = str(script.get("hook_text", "") or "")
    spoken = _sequence(script.get("spoken_script"))
    narration_blob = " ".join(
        str(beat.get("narration", "")) for beat in spoken if isinstance(beat, Mapping)
    )
    messaging_core = f"{hook_text} {narration_blob}".strip()
    caption_blob = " ".join(
        str(c.get("text", ""))
        for c in _sequence(script.get("caption_variants"))
        if isinstance(c, Mapping)
    )
    combined_messaging = f"{messaging_core} {caption_blob}".strip()

    overlay_hooks = _hook_overlay_texts(script.get("overlay_timeline"))
    messaging_with_overlays = f"{combined_messaging} {' '.join(overlay_hooks)}".strip()

    hook_scene = _first_hook_scene(scene_plan)
    hook_scene_blob = ""
    if hook_scene is not None:
        hook_scene_blob = (
            f"{hook_scene.get('visual_intent', '')} {hook_scene.get('shot_guidance', '')}"
        )

    intent_for_metrics = set(intent_tokens)
    cover_ts = _optional_float(editing_payload.get("cover_frame_timestamp_seconds"))
    duration = _optional_float(editing_payload.get("duration_seconds"))
    hook_end = _hook_window_end_seconds(hook_scene, scene_plan, duration)

    metrics: dict[str, object] = {
        "intent_token_count": len(intent_for_metrics),
        "messaging_coverage": _coverage(intent_for_metrics, combined_messaging),
        "messaging_with_overlays_coverage": _coverage(intent_for_metrics, messaging_with_overlays),
        "prompt_coverage": _coverage(intent_for_metrics, provider_prompt),
        "hook_scene_coverage": _coverage(intent_for_metrics, hook_scene_blob),
        "caption_only_coverage": _coverage(intent_for_metrics, caption_blob),
    }

    findings: list[AlignmentFinding] = []

    messaging_cov = float(metrics["messaging_with_overlays_coverage"])
    if messaging_cov < effective.fail_messaging_coverage:
        findings.append(
            AlignmentFinding(
                code="messaging_drift",
                severity="fail",
                message="On-screen and spoken messaging diverge strongly from the lead message.",
                details={
                    "messaging_coverage": messaging_cov,
                    "threshold": effective.fail_messaging_coverage,
                },
            )
        )

    prompt_cov = float(metrics["prompt_coverage"])
    if prompt_cov < effective.fail_prompt_coverage:
        findings.append(
            AlignmentFinding(
                code="asset_prompt_drift",
                severity="fail",
                message="Compiled provider prompt is misaligned with the creative lead message.",
                details={
                    "prompt_coverage": prompt_cov,
                    "threshold": effective.fail_prompt_coverage,
                },
            )
        )

    script_without_captions = f"{hook_text} {narration_blob} {' '.join(overlay_hooks)}".strip()
    script_cov = _coverage(intent_for_metrics, script_without_captions)
    caption_cov = float(metrics["caption_only_coverage"])
    if (
        script_cov - caption_cov > effective.warn_caption_messaging_gap
        and script_cov > effective.warn_caption_messaging_gap
    ):
        findings.append(
            AlignmentFinding(
                code="caption_intent_gap",
                severity="warn",
                message="Post copy looks materially weaker than the in-reel script relative to the lead message.",
                details={
                    "script_coverage": script_cov,
                    "caption_coverage": caption_cov,
                },
            )
        )

    hook_scene_cov = float(metrics["hook_scene_coverage"])
    if (
        hook_scene_blob
        and prompt_cov < effective.warn_hook_scene_prompt_gap
        and hook_scene_cov > prompt_cov + 0.05
    ):
        findings.append(
            AlignmentFinding(
                code="hook_scene_prompt_mismatch",
                severity="warn",
                message="Hook scene plan is richer than the provider prompt; verify the source clip still matches the hook plan.",
                details={
                    "hook_scene_coverage": hook_scene_cov,
                    "prompt_coverage": prompt_cov,
                },
            )
        )

    if (
        cover_ts is not None
        and hook_end is not None
        and cover_ts > hook_end + effective.hook_cover_slack_seconds
    ):
        findings.append(
            AlignmentFinding(
                code="cover_framing_outside_hook",
                severity="warn",
                message="Cover frame timestamp sits beyond the hook window; the thumbnail may not reflect the lead hook.",
                details={
                    "cover_frame_timestamp_seconds": cover_ts,
                    "hook_window_end_seconds": hook_end,
                    "slack_seconds": effective.hook_cover_slack_seconds,
                },
            )
        )
    if (
        cover_ts is not None
        and duration is not None
        and duration > 0.0
        and cover_ts > (duration * 0.6)
    ):
        findings.append(
            AlignmentFinding(
                code="cover_frame_late",
                severity="warn",
                message="Cover frame is taken late in the timeline; it may not reflect the primary hook.",
                details={
                    "cover_frame_timestamp_seconds": cover_ts,
                    "duration_seconds": duration,
                },
            )
        )

    if any(finding.severity == "fail" for finding in findings):
        verdict = QAVerdict.FAIL
    elif any(finding.severity == "warn" for finding in findings):
        verdict = QAVerdict.WARN
    else:
        verdict = QAVerdict.PASS

    message = "Creative intent, prompts, and packaging copy look aligned for phase-1 heuristics."
    if verdict == QAVerdict.FAIL:
        message = "; ".join(f.message for f in findings if f.severity == "fail")
    elif verdict == QAVerdict.WARN:
        message = "; ".join(f.message for f in findings if f.severity == "warn")

    return AlignmentQAReport(
        verdict=verdict,
        message=message,
        findings=tuple(findings),
        metrics=metrics,
        lead_text=lead_text,
    )


def _lead_message(brief: Mapping[str, Any]) -> str:
    narrative = str(brief.get("narrative_goal", "") or "").strip()
    pillar = str(brief.get("content_pillar", "") or "").strip()
    title = str(brief.get("title", "") or "").strip()
    tags = brief.get("tags", [])
    tag_blob = ""
    if isinstance(tags, Sequence) and not isinstance(tags, str | bytes):
        tag_texts = [str(t).strip() for t in tags if str(t).strip()]
        tag_blob = " ".join(tag_texts)
    return " ".join(part for part in (narrative, pillar, title, tag_blob) if part).strip()


def _content_tokens(text: str) -> set[str]:
    return {
        match.group(0).lower()
        for match in _WORD_RE.finditer(text)
        if len(match.group(0)) > 2 and match.group(0).lower() not in _STOP_WORDS
    }


def _coverage(intent: set[str], text: str) -> float:
    if not intent:
        return 0.0
    if not text.strip():
        return 0.0
    other = _content_tokens(text)
    if not other:
        return 0.0
    return len(intent & other) / float(len(intent))


def _sequence(value: object) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    return []


def _first_hook_scene(scene_plan: Mapping[str, Any]) -> dict[str, Any] | None:
    scenes = scene_plan.get("scenes")
    if not isinstance(scenes, list):
        return None
    for raw in scenes:
        if not isinstance(raw, Mapping):
            continue
        if str(raw.get("purpose", "")).lower() == "hook":
            return dict(raw)
    if scenes:
        first = scenes[0]
        if isinstance(first, Mapping):
            return dict(first)
    return None


def _hook_window_end_seconds(
    hook_scene: Mapping[str, Any] | None,
    scene_plan: Mapping[str, Any],
    duration: float | None,
) -> float | None:
    if hook_scene is not None:
        end = _optional_int(hook_scene.get("end_seconds"))
        if end is not None:
            return float(end)
    plan_duration = _optional_int(scene_plan.get("duration_seconds"))
    if plan_duration is not None:
        return min(3.0, float(plan_duration))
    if duration is not None:
        return min(3.0, max(duration, 0.0))
    return None


def _hook_overlay_texts(overlay_timeline: object) -> list[str]:
    if not isinstance(overlay_timeline, list):
        return []
    texts: list[str] = []
    for raw in overlay_timeline:
        if not isinstance(raw, Mapping):
            continue
        if str(raw.get("emphasis", "")).lower() == "hook":
            text = str(raw.get("text", "") or "").strip()
            if text:
                texts.append(text)
    return texts


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


__all__ = [
    "AlignmentFinding",
    "AlignmentQAConstraints",
    "AlignmentQAReport",
    "evaluate_alignment_qa",
]
