"""Run/task correlation context shared across worker and orchestrator."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, fields, replace
from typing import Iterator
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RunContext:
    """Correlation identifiers for a unit of work (run, task, HTTP request, service)."""

    run_id: str | UUID | None = None
    task_id: str | None = None
    request_id: str | None = None
    actor: str | None = None

    def merged_with(self, overlay: RunContext) -> RunContext:
        """Return a new context; non-None fields from ``overlay`` override ``self``."""
        return merge_run_context(self, overlay)


_run_context_var: ContextVar[RunContext | None] = ContextVar("content_lab_run_context", default=None)


def merge_run_context(base: RunContext, overlay: RunContext) -> RunContext:
    """Merge two contexts; overlay wins for fields that are not None."""
    kwargs: dict[str, str | UUID | None] = {}
    for f in fields(RunContext):
        name = f.name
        base_v = getattr(base, name)
        over_v = getattr(overlay, name)
        kwargs[name] = over_v if over_v is not None else base_v
    return RunContext(**kwargs)


def with_run_id(ctx: RunContext, run_id: str | UUID) -> RunContext:
    return replace(ctx, run_id=run_id)


def with_task_id(ctx: RunContext, task_id: str) -> RunContext:
    return replace(ctx, task_id=task_id)


def with_request_id(ctx: RunContext, request_id: str) -> RunContext:
    return replace(ctx, request_id=request_id)


def with_actor(ctx: RunContext, actor: str) -> RunContext:
    return replace(ctx, actor=actor)


def correlation_dict(ctx: RunContext) -> dict[str, str]:
    """Flatten to string key/values for structured logs or trace headers (omit unset fields)."""
    out: dict[str, str] = {}
    if ctx.run_id is not None:
        out["run_id"] = str(ctx.run_id)
    if ctx.task_id is not None:
        out["task_id"] = ctx.task_id
    if ctx.request_id is not None:
        out["request_id"] = ctx.request_id
    if ctx.actor is not None:
        out["actor"] = ctx.actor
    return out


def current_run_context() -> RunContext | None:
    return _run_context_var.get()


@contextmanager
def run_context_scope(ctx: RunContext) -> Iterator[None]:
    """Bind ``ctx`` for the current async/task context; restored on exit."""
    token = _run_context_var.set(ctx)
    try:
        yield
    finally:
        _run_context_var.reset(token)
