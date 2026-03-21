"""Defaults for shared run/task correlation in orchestration flows."""

from __future__ import annotations

from content_lab_runs import RunContext

ORCHESTRATOR_ACTOR_NAME = "content-lab-orchestrator"


def orchestrator_service_context() -> RunContext:
    return RunContext(actor=ORCHESTRATOR_ACTOR_NAME)
