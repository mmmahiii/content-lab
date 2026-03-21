"""Defaults for shared run/task correlation in the worker process."""

from __future__ import annotations

from content_lab_runs import RunContext

WORKER_ACTOR_NAME = "content-lab-worker"


def worker_service_context() -> RunContext:
    return RunContext(actor=WORKER_ACTOR_NAME)
