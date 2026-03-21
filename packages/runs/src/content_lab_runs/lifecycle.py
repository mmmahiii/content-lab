"""Pipeline run lifecycle model and state transition logic."""

from __future__ import annotations

from pydantic import Field

from content_lab_core.models import DomainModel
from content_lab_core.types import RunStatus

_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.PENDING: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.RUNNING: frozenset({RunStatus.PAUSED, RunStatus.COMPLETED, RunStatus.FAILED}),
    RunStatus.PAUSED: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset({RunStatus.PENDING}),
    RunStatus.CANCELLED: frozenset(),
}


class InvalidTransitionError(Exception):
    """Raised when a run status transition is not allowed."""

    def __init__(self, current: RunStatus, target: RunStatus) -> None:
        super().__init__(f"Cannot transition from {current.value!r} to {target.value!r}")
        self.current = current
        self.target = target


class RunRecord(DomainModel):
    """Represents a single pipeline run through its lifecycle."""

    name: str
    status: RunStatus = RunStatus.PENDING
    error_message: str = ""
    step_index: int = 0
    tags: list[str] = Field(default_factory=list)

    def transition_to(self, target: RunStatus) -> None:
        """Move the run to *target* status, raising on illegal transitions."""
        allowed = _TRANSITIONS.get(self.status, frozenset())
        if target not in allowed:
            raise InvalidTransitionError(self.status, target)
        self.status = target

    @property
    def is_terminal(self) -> bool:
        return self.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED)
