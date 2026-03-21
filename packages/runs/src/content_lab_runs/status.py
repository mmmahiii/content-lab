"""Typed lifecycle statuses for pipeline runs and tasks."""

from __future__ import annotations

from enum import StrEnum


class RunStatus(StrEnum):
    """High-level state of a pipeline run (persisted run row / orchestration)."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(StrEnum):
    """Fine-grained state for an individual task/step within a run."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
