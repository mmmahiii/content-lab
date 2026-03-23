"""Provider-facing worker actor definitions."""

from __future__ import annotations

from content_lab_worker.actors._shared import ActorLike, build_queue_name, get_actor_logger

logger = get_actor_logger("provider")
QUEUE_NAME = build_queue_name("provider")
ACTORS: tuple[ActorLike, ...] = ()

__all__ = ["ACTORS", "QUEUE_NAME", "logger"]
