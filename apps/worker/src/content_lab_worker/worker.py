"""Stable Dramatiq entrypoint for Content Lab worker actors."""

from __future__ import annotations

import os
from typing import Final

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from content_lab_shared.logging import configure_logging
from content_lab_worker.actors import ActorRegistration, register_actor_modules
from content_lab_worker.actors._shared import ActorLike

configure_logging()

broker = RedisBroker(url=os.getenv("REDIS_URL", "redis://localhost:6379/0"))  # type: ignore[no-untyped-call]
dramatiq.set_broker(broker)

ACTOR_REGISTRATION: Final[ActorRegistration] = register_actor_modules()


def _require_actor(actor_name: str) -> ActorLike:
    for actor in ACTOR_REGISTRATION.actors:
        if actor.actor_name == actor_name:
            return actor
    raise RuntimeError(f"actor '{actor_name}' was not registered")


ping: Final[ActorLike] = _require_actor("ping")

__all__ = ["ACTOR_REGISTRATION", "broker", "ping"]
