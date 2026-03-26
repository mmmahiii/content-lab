"""QA gate models and protocol for content validation checks."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import Field

from content_lab_core.models import DomainModel
from content_lab_core.types import QAVerdict


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
        }


@runtime_checkable
class QAGate(Protocol):
    """Interface for a single QA gate that can evaluate content."""

    @property
    def name(self) -> str: ...

    def evaluate(self, run_id: str) -> QAResult: ...
