"""Phase-1 repetition gate driven by exact reuse history and family policy."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from content_lab_core.types import QAVerdict
from content_lab_qa.gate import QAResult


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RepetitionPolicy(BaseModel):
    """Thresholds and hard limits used by the phase-1 repetition gate."""

    model_config = ConfigDict(extra="forbid")

    cooldown_seconds: int | None = Field(default=None, ge=1)
    family_reuse_cap: int | None = Field(default=None, ge=1)
    exact_reuse_warn_at: int | None = Field(default=None, ge=1)
    exact_reuse_fail_at: int | None = Field(default=None, ge=1)
    family_reuse_warn_at: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _validate_threshold_ordering(self) -> RepetitionPolicy:
        if (
            self.exact_reuse_warn_at is not None
            and self.exact_reuse_fail_at is not None
            and self.exact_reuse_warn_at >= self.exact_reuse_fail_at
        ):
            raise ValueError("exact_reuse_warn_at must be lower than exact_reuse_fail_at")
        return self


class RepetitionHistory(BaseModel):
    """Reuse counts and timestamps gathered before evaluating repetition risk."""

    model_config = ConfigDict(extra="forbid")

    exact_reuse_count: int = Field(default=0, ge=0)
    family_reuse_count: int = Field(default=0, ge=0)
    last_exact_reused_at: datetime | None = None
    last_family_reused_at: datetime | None = None


class RepetitionSignal(BaseModel):
    """A single repetition signal that contributes to the final verdict."""

    model_config = ConfigDict(extra="forbid")

    signal_name: str = Field(min_length=1)
    verdict: QAVerdict
    message: str = ""
    details: dict[str, object] = Field(default_factory=dict)


class RepetitionGateRequest(BaseModel):
    """Input envelope for the phase-1 repetition gate."""

    model_config = ConfigDict(extra="forbid")

    candidate_key: str = Field(min_length=1)
    family_id: str | None = None
    evaluated_at: datetime = Field(default_factory=_utcnow)
    history: RepetitionHistory | None = None
    policy: RepetitionPolicy = Field(default_factory=RepetitionPolicy)
    additional_signals: list[RepetitionSignal] = Field(default_factory=list)


@runtime_checkable
class RepetitionHistoryStore(Protocol):
    """Store boundary for exact and family reuse history lookups."""

    def get_repetition_history(
        self,
        *,
        candidate_key: str,
        family_id: str | None,
        evaluated_at: datetime,
    ) -> RepetitionHistory: ...


class RepetitionGate:
    """Evaluate phase-1 anti-repetition rules using exact and family history."""

    name = "repetition"

    def __init__(self, history_store: RepetitionHistoryStore | None = None) -> None:
        self._history_store = history_store

    def evaluate(self, request: RepetitionGateRequest) -> QAResult:
        history = request.history or self._lookup_history(request)
        signals = _phase1_signals(
            history=history, policy=request.policy, evaluated_at=request.evaluated_at
        )
        signals.extend(request.additional_signals)
        verdict = _aggregate_verdict(signals)
        triggered_messages = [
            signal.message
            for signal in signals
            if signal.verdict in (QAVerdict.WARN, QAVerdict.FAIL) and signal.message
        ]

        return QAResult(
            gate_name=self.name,
            verdict=verdict,
            message="; ".join(triggered_messages),
            details={
                "phase": "phase_1",
                "candidate_key": request.candidate_key,
                "family_id": request.family_id,
                "evaluated_at": request.evaluated_at.isoformat(),
                "history": history.model_dump(mode="json", exclude_none=True),
                "policy": request.policy.model_dump(mode="json", exclude_none=True),
                "signals": [
                    signal.model_dump(mode="json", exclude_none=True) for signal in signals
                ],
            },
        )

    def _lookup_history(self, request: RepetitionGateRequest) -> RepetitionHistory:
        if self._history_store is None:
            return RepetitionHistory()
        return self._history_store.get_repetition_history(
            candidate_key=request.candidate_key,
            family_id=request.family_id,
            evaluated_at=request.evaluated_at,
        )


def evaluate_repetition(
    request: RepetitionGateRequest,
    *,
    history_store: RepetitionHistoryStore | None = None,
) -> QAResult:
    """Convenience wrapper for evaluating a repetition request without manual gate wiring."""

    return RepetitionGate(history_store).evaluate(request)


def _phase1_signals(
    *,
    history: RepetitionHistory,
    policy: RepetitionPolicy,
    evaluated_at: datetime,
) -> list[RepetitionSignal]:
    signals = [
        _build_exact_reuse_signal(history=history, policy=policy),
        _build_family_reuse_signal(history=history, policy=policy),
        _build_cooldown_signal(history=history, policy=policy, evaluated_at=evaluated_at),
    ]
    return [signal for signal in signals if signal is not None]


def _build_exact_reuse_signal(
    *,
    history: RepetitionHistory,
    policy: RepetitionPolicy,
) -> RepetitionSignal | None:
    if policy.exact_reuse_warn_at is None and policy.exact_reuse_fail_at is None:
        return None

    count = history.exact_reuse_count
    verdict = QAVerdict.PASS
    message = ""
    if policy.exact_reuse_fail_at is not None and count >= policy.exact_reuse_fail_at:
        verdict = QAVerdict.FAIL
        message = f"Exact asset has already been reused {count} times"
    elif policy.exact_reuse_warn_at is not None and count >= policy.exact_reuse_warn_at:
        verdict = QAVerdict.WARN
        message = f"Exact asset reuse count is {count}"

    return RepetitionSignal(
        signal_name="exact_reuse_history",
        verdict=verdict,
        message=message,
        details={
            "exact_reuse_count": count,
            "last_exact_reused_at": history.last_exact_reused_at,
            "warn_at": policy.exact_reuse_warn_at,
            "fail_at": policy.exact_reuse_fail_at,
        },
    )


def _build_family_reuse_signal(
    *,
    history: RepetitionHistory,
    policy: RepetitionPolicy,
) -> RepetitionSignal | None:
    if policy.family_reuse_warn_at is None and policy.family_reuse_cap is None:
        return None

    count = history.family_reuse_count
    verdict = QAVerdict.PASS
    message = ""
    if policy.family_reuse_cap is not None and count >= policy.family_reuse_cap:
        verdict = QAVerdict.FAIL
        message = f"Family reuse cap reached at {count} uses"
    elif policy.family_reuse_warn_at is not None and count >= policy.family_reuse_warn_at:
        verdict = QAVerdict.WARN
        message = f"Family reuse count is {count}"

    return RepetitionSignal(
        signal_name="family_reuse_history",
        verdict=verdict,
        message=message,
        details={
            "family_reuse_count": count,
            "last_family_reused_at": history.last_family_reused_at,
            "warn_at": policy.family_reuse_warn_at,
            "family_reuse_cap": policy.family_reuse_cap,
        },
    )


def _build_cooldown_signal(
    *,
    history: RepetitionHistory,
    policy: RepetitionPolicy,
    evaluated_at: datetime,
) -> RepetitionSignal | None:
    if policy.cooldown_seconds is None:
        return None

    last_used_at = history.last_family_reused_at or history.last_exact_reused_at
    remaining_seconds = None
    verdict = QAVerdict.PASS
    message = ""
    if last_used_at is not None:
        elapsed_seconds = int((evaluated_at - last_used_at).total_seconds())
        remaining_seconds = policy.cooldown_seconds - max(elapsed_seconds, 0)
        if remaining_seconds > 0:
            verdict = QAVerdict.FAIL
            message = f"Family cooldown active for another {remaining_seconds} seconds"

    return RepetitionSignal(
        signal_name="family_cooldown",
        verdict=verdict,
        message=message,
        details={
            "cooldown_seconds": policy.cooldown_seconds,
            "last_used_at": last_used_at,
            "remaining_seconds": remaining_seconds
            if remaining_seconds and remaining_seconds > 0
            else 0,
        },
    )


def _aggregate_verdict(signals: list[RepetitionSignal]) -> QAVerdict:
    if any(signal.verdict == QAVerdict.FAIL for signal in signals):
        return QAVerdict.FAIL
    if any(signal.verdict == QAVerdict.WARN for signal in signals):
        return QAVerdict.WARN
    if any(signal.verdict == QAVerdict.SKIP for signal in signals):
        return QAVerdict.SKIP
    return QAVerdict.PASS


__all__ = [
    "RepetitionGate",
    "RepetitionGateRequest",
    "RepetitionHistory",
    "RepetitionHistoryStore",
    "RepetitionPolicy",
    "RepetitionSignal",
    "evaluate_repetition",
]
