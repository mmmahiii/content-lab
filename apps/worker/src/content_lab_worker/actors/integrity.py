"""Integrity and smoke-test worker actors."""

from __future__ import annotations

import dramatiq

from content_lab_worker.actors._shared import ActorLike, build_queue_name, get_actor_logger
from content_lab_worker.correlation import worker_service_context

logger = get_actor_logger("integrity")
QUEUE_NAME = build_queue_name("integrity")


@dramatiq.actor(queue_name=QUEUE_NAME)
def ping() -> str:
    context = worker_service_context()
    logger.info("ping actor invoked for %s", context.actor)
    return "pong"


ACTORS: tuple[ActorLike, ...] = (ping,)

__all__ = ["ACTORS", "QUEUE_NAME", "ping"]
