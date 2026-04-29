"""Structured QA findings for operator-visible run and task output."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from content_lab_core.types import QAVerdict
from content_lab_qa.alignment import AlignmentFinding, AlignmentQAReport
from content_lab_qa.format import FormatQAReport
from content_lab_qa.gate import QAResult
from content_lab_qa.semantic_script import SemanticScriptFinding, SemanticScriptQAReport

StructuredSeverity = Literal["pass", "warn", "fail", "skip"]

StandardFindingType = Literal[
    "overlay_text_clipped",
    "overlay_overlap_detected",
    "overlay_text_mismatch",
    "caption_meta_language",
    "duration_mismatch",
    "generic",
]

_META_CODES_FOR_CAPTION = frozenset(
    {
        "meta_placeholder",
        "meta_generation_language",
        "abstract_script_language",
    }
)

_MAX_OVERLAY_CHARS_BEFORE_CLIP_WARN = 96


class StructuredQAFinding(BaseModel):
    """Normalized finding shape shared across gates for run/task payloads."""

    model_config = ConfigDict(extra="forbid")

    finding_type: str = Field(
        min_length=1,
        description=(
            "Stable machine code; prefer standard types: overlay_text_clipped, "
            "overlay_overlap_detected, overlay_text_mismatch, caption_meta_language, "
            "duration_mismatch, or generic."
        ),
    )
    gate_name: str = Field(min_length=1)
    severity: StructuredSeverity
    passed: bool
    field_path: str = ""
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


def collect_structured_qa_findings(
    *,
    format_report: FormatQAReport,
    repetition_result: QAResult,
    semantic_report: SemanticScriptQAReport,
    alignment_report: AlignmentQAReport,
    editing_output: Mapping[str, Any] | None = None,
    creative_script: Mapping[str, Any] | None = None,
) -> list[StructuredQAFinding]:
    """Fold phase-1 QA reports into a single structured finding list for persistence."""

    findings: list[StructuredQAFinding] = []
    findings.extend(_findings_from_format(format_report))
    findings.append(_finding_from_qa_result(repetition_result, finding_type="generic"))
    findings.extend(_findings_from_semantic(semantic_report))
    findings.extend(_findings_from_alignment(alignment_report))
    findings.extend(
        _findings_from_overlay_diagnostics(
            editing_output=dict(editing_output or {}),
            creative_script=dict(creative_script or {}),
        )
    )
    return findings


def _finding_from_qa_result(result: QAResult, *, finding_type: str) -> StructuredQAFinding:
    return StructuredQAFinding(
        finding_type=finding_type,
        gate_name=result.gate_name,
        severity=_severity_from_verdict(result.verdict),
        passed=result.passed,
        field_path=_field_path_from_qa_result(result),
        message=result.message,
        details=dict(result.details),
    )


def _field_path_from_qa_result(result: QAResult) -> str:
    gate = result.gate_name
    if gate in {"final_video_dimensions", "final_video_duration", "final_video_audio"}:
        return "editing.final_video"
    if gate.startswith("cover"):
        return "editing.cover_image"
    if gate == "repetition":
        return "asset_resolution.asset_key_hash"

    details = dict(result.details)
    explicit = details.get("field_path")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    path = details.get("path")
    if isinstance(path, str) and path.strip():
        return path.strip()
    return ""


def _findings_from_format(report: FormatQAReport) -> list[StructuredQAFinding]:
    rows: list[StructuredQAFinding] = []
    for check in report.checks:
        finding_type: StandardFindingType = "generic"
        if check.gate_name == "final_video_duration" and not check.passed:
            finding_type = "duration_mismatch"
        rows.append(_finding_from_qa_result(check, finding_type=finding_type))
    return rows


def _findings_from_semantic(report: SemanticScriptQAReport) -> list[StructuredQAFinding]:
    rows: list[StructuredQAFinding] = []
    for finding in report.findings:
        rows.append(_finding_from_semantic(finding))
    return rows


def _finding_from_semantic(finding: SemanticScriptFinding) -> StructuredQAFinding:
    if finding.outcome == "fail":
        severity: StructuredSeverity = "fail"
        passed = False
    elif finding.outcome == "warn":
        severity = "warn"
        passed = False
    else:
        severity = "pass"
        passed = True
    finding_type = _semantic_finding_type(finding)
    return StructuredQAFinding(
        finding_type=finding_type,
        gate_name="semantic_script",
        severity=severity,
        passed=passed,
        field_path=finding.field_path,
        message=finding.message,
        details={
            "code": finding.code,
            "snippet": finding.snippet,
            **dict(finding.details),
        },
    )


def _semantic_finding_type(finding: SemanticScriptFinding) -> str:
    if finding.code == "duplicate_overlays":
        return "overlay_overlap_detected"
    if finding.code in _META_CODES_FOR_CAPTION and finding.field_path.startswith(
        "caption_variants"
    ):
        return "caption_meta_language"
    if finding.code in _META_CODES_FOR_CAPTION and "caption" in finding.field_path.lower():
        return "caption_meta_language"
    return "generic"


def _findings_from_alignment(report: AlignmentQAReport) -> list[StructuredQAFinding]:
    rows: list[StructuredQAFinding] = []
    for finding in report.findings:
        rows.append(_finding_from_alignment(finding))
    if report.skipped:
        rows.append(
            StructuredQAFinding(
                finding_type="generic",
                gate_name=report.gate_name,
                severity="skip",
                passed=True,
                field_path="creative.brief",
                message=report.message or "Alignment QA skipped.",
                details={
                    "skipped": True,
                    "skip_reason": report.skip_reason,
                    "metrics": dict(report.metrics),
                },
            )
        )
    return rows


def _finding_from_alignment(finding: AlignmentFinding) -> StructuredQAFinding:
    passed = finding.severity != "fail"
    severity: StructuredSeverity = "fail" if finding.severity == "fail" else "warn"
    return StructuredQAFinding(
        finding_type="generic",
        gate_name="alignment",
        severity=severity,
        passed=passed,
        field_path=_alignment_field_path(finding.code),
        message=finding.message,
        details={"code": finding.code, **dict(finding.details)},
    )


def _alignment_field_path(code: str) -> str:
    if code == "caption_intent_gap":
        return "script.caption_variants"
    if code in {"messaging_drift", "asset_prompt_drift"}:
        return "creative.compiled_prompt"
    if code in {"cover_framing_outside_hook", "cover_frame_late"}:
        return "editing.cover_frame_timestamp_seconds"
    return ""


def _findings_from_overlay_diagnostics(
    *,
    editing_output: dict[str, Any],
    creative_script: dict[str, Any],
) -> list[StructuredQAFinding]:
    rows: list[StructuredQAFinding] = []
    trace_raw = editing_output.get("overlay_render_trace")
    trace = dict(trace_raw) if isinstance(trace_raw, Mapping) else {}
    normalized = trace.get("normalized_overlays")
    if not isinstance(normalized, list):
        normalized = []

    for index, overlay in enumerate(normalized):
        if not isinstance(overlay, Mapping):
            continue
        text = str(overlay.get("text", "") or "")
        if len(text) >= _MAX_OVERLAY_CHARS_BEFORE_CLIP_WARN:
            rows.append(
                StructuredQAFinding(
                    finding_type="overlay_text_clipped",
                    gate_name="overlay_render",
                    severity="warn",
                    passed=False,
                    field_path=f"editing.overlay_render_trace.normalized_overlays[{index}].text",
                    message=(
                        "Overlay text is long relative to the vertical safe title safe-area; "
                        "it may be clipped or shrink unpredictably in FFmpeg drawtext."
                    ),
                    details={
                        "char_length": len(text),
                        "threshold": _MAX_OVERLAY_CHARS_BEFORE_CLIP_WARN,
                        "text_excerpt": text[:120],
                    },
                )
            )

    if _normalized_overlay_intervals_overlap(normalized):
        rows.append(
            StructuredQAFinding(
                finding_type="overlay_overlap_detected",
                gate_name="overlay_render",
                severity="warn",
                passed=False,
                field_path="editing.overlay_render_trace.normalized_overlays",
                message="Two or more overlays share overlapping on-screen time windows.",
                details={"normalized_overlay_count": len(normalized)},
            )
        )

    planned = _planned_overlay_texts(creative_script.get("overlay_timeline"))
    rendered = [
        _normalize_overlay_text(str(o.get("text", "") or ""))
        for o in normalized
        if isinstance(o, Mapping) and str(o.get("text", "") or "").strip()
    ]
    if planned and rendered and planned != rendered:
        rows.append(
            StructuredQAFinding(
                finding_type="overlay_text_mismatch",
                gate_name="overlay_render",
                severity="fail",
                passed=False,
                field_path="script.overlay_timeline",
                message="Rendered overlay texts differ from the planned script overlay timeline.",
                details={"planned_texts": planned, "rendered_texts": rendered},
            )
        )

    return rows


def _normalized_overlay_intervals_overlap(raw: Sequence[Any]) -> bool:
    intervals: list[tuple[float, float]] = []
    for overlay in raw:
        if not isinstance(overlay, Mapping):
            continue
        start = float(overlay.get("start_seconds") or 0.0)
        end_val = overlay.get("end_seconds")
        if end_val is None:
            continue
        end = float(end_val)
        if end <= start:
            continue
        intervals.append((start, end))
    intervals.sort(key=lambda pair: pair[0])
    for previous, current in zip(intervals, intervals[1:]):
        if current[0] < previous[1] - 1e-3:
            return True
    return False


def _planned_overlay_texts(timeline: Any) -> list[str]:
    if not isinstance(timeline, list):
        return []
    texts: list[str] = []
    for raw in timeline:
        if not isinstance(raw, Mapping):
            continue
        text = raw.get("text")
        params = raw.get("params") if isinstance(raw.get("params"), Mapping) else None
        if text is None and params is not None:
            text = params.get("text")
        normalized = _normalize_overlay_text(str(text or ""))
        if normalized:
            texts.append(normalized)
    return texts


def _normalize_overlay_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).lower()


def _severity_from_verdict(verdict: QAVerdict) -> StructuredSeverity:
    if verdict == QAVerdict.PASS:
        return "pass"
    if verdict == QAVerdict.WARN:
        return "warn"
    if verdict == QAVerdict.FAIL:
        return "fail"
    return "skip"


def structured_findings_as_jsonable(findings: Sequence[StructuredQAFinding]) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in findings]


__all__ = [
    "StandardFindingType",
    "StructuredQAFinding",
    "StructuredSeverity",
    "collect_structured_qa_findings",
    "structured_findings_as_jsonable",
]
