from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from content_lab_core.types import QAVerdict
from content_lab_qa.repetition import (
    RepetitionGate,
    RepetitionGateRequest,
    RepetitionHistory,
    RepetitionPolicy,
    RepetitionSignal,
    evaluate_repetition,
)


class InMemoryRepetitionHistoryStore:
    def __init__(self, history: RepetitionHistory) -> None:
        self.history = history
        self.calls: list[tuple[str, str | None]] = []

    def get_repetition_history(
        self,
        *,
        candidate_key: str,
        family_id: str | None,
        evaluated_at: datetime,
    ) -> RepetitionHistory:
        del evaluated_at
        self.calls.append((candidate_key, family_id))
        return self.history


def test_repetition_gate_passes_when_history_is_below_thresholds() -> None:
    result = evaluate_repetition(
        RepetitionGateRequest(
            candidate_key="asset-key-1",
            family_id="family-a",
            history=RepetitionHistory(
                exact_reuse_count=1,
                family_reuse_count=1,
            ),
            policy=RepetitionPolicy(
                exact_reuse_warn_at=2,
                exact_reuse_fail_at=4,
                family_reuse_warn_at=3,
                family_reuse_cap=5,
            ),
        )
    )

    assert result.verdict == QAVerdict.PASS
    assert result.passed
    assert result.message == ""
    assert result.details["phase"] == "phase_1"


def test_repetition_gate_warns_when_exact_reuse_threshold_is_hit() -> None:
    result = evaluate_repetition(
        RepetitionGateRequest(
            candidate_key="asset-key-2",
            family_id="family-b",
            history=RepetitionHistory(
                exact_reuse_count=2,
                family_reuse_count=1,
                last_exact_reused_at=datetime(2026, 3, 24, 12, 0, tzinfo=UTC),
            ),
            policy=RepetitionPolicy(
                exact_reuse_warn_at=2,
                exact_reuse_fail_at=5,
                family_reuse_cap=4,
            ),
        )
    )

    assert result.verdict == QAVerdict.WARN
    assert not result.passed
    assert "Exact asset reuse count is 2" in result.message
    signals = cast(list[dict[str, Any]], result.details["signals"])
    assert signals[0]["signal_name"] == "exact_reuse_history"
    assert signals[0]["verdict"] == "warn"


def test_repetition_gate_fails_for_family_cap_and_active_cooldown() -> None:
    evaluated_at = datetime(2026, 3, 26, 12, 0, tzinfo=UTC)
    result = evaluate_repetition(
        RepetitionGateRequest(
            candidate_key="asset-key-3",
            family_id="family-c",
            evaluated_at=evaluated_at,
            history=RepetitionHistory(
                exact_reuse_count=1,
                family_reuse_count=3,
                last_family_reused_at=evaluated_at - timedelta(seconds=120),
            ),
            policy=RepetitionPolicy(
                cooldown_seconds=300,
                family_reuse_cap=3,
                exact_reuse_warn_at=2,
                exact_reuse_fail_at=5,
            ),
        )
    )

    assert result.verdict == QAVerdict.FAIL
    assert "Family reuse cap reached at 3 uses" in result.message
    assert "Family cooldown active for another 180 seconds" in result.message
    signals = cast(list[dict[str, Any]], result.details["signals"])
    cooldown_signal = next(
        signal for signal in signals if signal["signal_name"] == "family_cooldown"
    )
    cooldown_details = cast(dict[str, Any], cooldown_signal["details"])
    assert cooldown_details["remaining_seconds"] == 180


def test_repetition_gate_queries_history_store_when_request_history_is_missing() -> None:
    store = InMemoryRepetitionHistoryStore(
        RepetitionHistory(
            exact_reuse_count=4,
            family_reuse_count=2,
        )
    )
    gate = RepetitionGate(store)

    result = gate.evaluate(
        RepetitionGateRequest(
            candidate_key="asset-key-4",
            family_id="family-d",
            policy=RepetitionPolicy(
                exact_reuse_warn_at=2,
                exact_reuse_fail_at=4,
            ),
        )
    )

    assert result.verdict == QAVerdict.FAIL
    assert store.calls == [("asset-key-4", "family-d")]


def test_repetition_gate_keeps_shape_stable_when_future_signals_are_added() -> None:
    result = evaluate_repetition(
        RepetitionGateRequest(
            candidate_key="asset-key-5",
            history=RepetitionHistory(),
            policy=RepetitionPolicy(),
            additional_signals=[
                RepetitionSignal(
                    signal_name="phash_similarity",
                    verdict=QAVerdict.WARN,
                    message="Perceptual hash is close to a recent asset",
                    details={"score": 0.81},
                )
            ],
        )
    )

    assert result.verdict == QAVerdict.WARN
    assert result.gate_name == "repetition"
    assert result.details["signals"] == [
        {
            "signal_name": "phash_similarity",
            "verdict": "warn",
            "message": "Perceptual hash is close to a recent asset",
            "details": {"score": 0.81},
        }
    ]
