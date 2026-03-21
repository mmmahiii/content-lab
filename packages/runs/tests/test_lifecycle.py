from __future__ import annotations

import pytest

from content_lab_core.types import RunStatus
from content_lab_runs.lifecycle import InvalidTransitionError, RunRecord


class TestRunRecord:
    def test_defaults(self) -> None:
        run = RunRecord(name="test-run")
        assert run.status == RunStatus.PENDING
        assert not run.is_terminal

    def test_valid_transitions(self) -> None:
        run = RunRecord(name="run-1")
        run.transition_to(RunStatus.RUNNING)
        assert run.status == RunStatus.RUNNING
        run.transition_to(RunStatus.COMPLETED)
        assert run.status == RunStatus.COMPLETED  # type: ignore[comparison-overlap]
        assert run.is_terminal

    def test_invalid_transition(self) -> None:
        run = RunRecord(name="run-2")
        with pytest.raises(InvalidTransitionError):
            run.transition_to(RunStatus.COMPLETED)

    def test_pause_resume(self) -> None:
        run = RunRecord(name="run-3")
        run.transition_to(RunStatus.RUNNING)
        run.transition_to(RunStatus.PAUSED)
        assert run.status == RunStatus.PAUSED
        run.transition_to(RunStatus.RUNNING)
        assert run.status == RunStatus.RUNNING  # type: ignore[comparison-overlap]

    def test_failed_can_retry(self) -> None:
        run = RunRecord(name="run-4")
        run.transition_to(RunStatus.RUNNING)
        run.transition_to(RunStatus.FAILED)
        assert run.is_terminal
        run.transition_to(RunStatus.PENDING)
        assert not run.is_terminal

    def test_cancelled_is_terminal(self) -> None:
        run = RunRecord(name="run-5")
        run.transition_to(RunStatus.CANCELLED)
        assert run.is_terminal
        with pytest.raises(InvalidTransitionError):
            run.transition_to(RunStatus.RUNNING)
