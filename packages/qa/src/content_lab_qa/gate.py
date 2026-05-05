"""QA gate models and protocol for content validation checks."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import Field

from content_lab_core.models import DomainModel
from content_lab_core.types import QAVerdict

_NONBLOCKING_FAIL_GATES = frozenset(
    {
        "alignment",
        "caption_meta_language",
        "cover_dimensions",
        "cover_exists",
        "final_video_audio",
        "final_video_audio_sync",
        "final_video_dimensions",
        "final_video_duration",
        "media_sync",
        "overlay_text_fidelity",
        "package_script_semantics",
        "repetition",
        "semantic_script",
        "timeline_timing",
    }
)
_BLOCKING_PACKAGE_GATES = frozenset(
    {
        "package_completeness",
        "package_manifest",
        "package_provenance",
    }
)
_BLOCKING_FINDING_CODES = frozenset(
    {
        "canonical_timeline_missing",
        "audio_video_duration_mismatch",
        "cover_timestamp_out_of_bounds",
        "creative_duration_mismatch",
        "editing_duration_mismatch",
        "final_duration_missing",
        "final_video_missing_audio",
        "final_video_missing_video",
        "media_timeline_missing",
        "overlay_exceeds_video_duration",
        "scene_exceeds_video_duration",
        "source_asset_too_short",
        "timeline_missing",
        "timeline_missing_final_duration",
    }
)


class QAResult(DomainModel):
    """Outcome of a single quality-assurance gate evaluation."""

    gate_name: str
    verdict: QAVerdict
    message: str = ""
    details: dict[str, object] = Field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.verdict in (QAVerdict.PASS, QAVerdict.SKIP)

    def as_payload(self) -> dict[str, Any]:
        return {
            "gate_name": self.gate_name,
            "verdict": self.verdict.value,
            "message": self.message,
            "details": dict(self.details),
            "passed": self.passed,
            "blocks_readiness": qa_result_blocks_readiness(self),
        }


@runtime_checkable
class QAGate(Protocol):
    """Interface for a single QA gate that can evaluate content."""

    @property
    def name(self) -> str: ...

    def evaluate(self, run_id: str) -> QAResult: ...


def qa_result_blocks_readiness(result: QAResult) -> bool:
    """Return whether a QA failure should stop packaging/readiness.

    QA can report quality, copy, timing, and review issues without turning a paid
    generation into a dead end. Only structural failures that prevent a usable
    package, or explicitly blocking findings, should stop readiness.
    """

    if result.verdict != QAVerdict.FAIL:
        return False
    gate_name = result.gate_name
    if gate_name in _BLOCKING_PACKAGE_GATES:
        return True
    if gate_name in _NONBLOCKING_FAIL_GATES:
        return _details_include_blocking_code(result.details)
    return True


def _details_include_blocking_code(value: object) -> bool:
    if isinstance(value, dict):
        code = value.get("code")
        if isinstance(code, str) and code in _BLOCKING_FINDING_CODES:
            return True
        return any(_details_include_blocking_code(item) for item in value.values())
    if isinstance(value, list | tuple):
        return any(_details_include_blocking_code(item) for item in value)
    return False
