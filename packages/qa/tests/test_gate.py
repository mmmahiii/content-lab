from __future__ import annotations

from content_lab_core.types import QAVerdict
from content_lab_qa.gate import QAResult


class TestQAResult:
    def test_pass(self) -> None:
        result = QAResult(gate_name="resolution", verdict=QAVerdict.PASS)
        assert result.passed

    def test_fail(self) -> None:
        result = QAResult(
            gate_name="duration",
            verdict=QAVerdict.FAIL,
            message="Video exceeds 60s limit",
        )
        assert not result.passed
        assert result.message == "Video exceeds 60s limit"

    def test_warn(self) -> None:
        result = QAResult(gate_name="aspect_ratio", verdict=QAVerdict.WARN)
        assert not result.passed

    def test_skip_is_passing(self) -> None:
        result = QAResult(gate_name="optional_check", verdict=QAVerdict.SKIP)
        assert result.passed

    def test_details(self) -> None:
        result = QAResult(
            gate_name="file_size",
            verdict=QAVerdict.FAIL,
            details={"max_mb": 50, "actual_mb": 120},
        )
        assert result.details["actual_mb"] == 120
