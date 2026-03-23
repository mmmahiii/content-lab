"""Shared queue and logging helpers for worker actor modules."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any, Final, Protocol

WORKER_QUEUE_NAMESPACE: Final = "content-lab-worker"
_INVALID_QUEUE_CHARS = re.compile(r"[^a-z0-9]+")


class ActorLike(Protocol):
    actor_name: str
    queue_name: str
    fn: Callable[..., Any]


def build_queue_name(domain: str) -> str:
    normalized = _INVALID_QUEUE_CHARS.sub("-", domain.strip().lower()).strip("-")
    if not normalized:
        raise ValueError("actor queue domain must contain at least one alphanumeric character")
    return f"{WORKER_QUEUE_NAMESPACE}.{normalized}"


def get_actor_logger(domain: str) -> logging.Logger:
    logger_name = _INVALID_QUEUE_CHARS.sub("_", domain.strip().lower()).strip("_") or "unknown"
    return logging.getLogger(f"content_lab_worker.actors.{logger_name}")
