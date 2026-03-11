import os

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from content_lab_shared.logging import configure_logging

configure_logging()

broker = RedisBroker(url=os.getenv("REDIS_URL", "redis://localhost:6379/0"))  # type: ignore[no-untyped-call]
dramatiq.set_broker(broker)  # type: ignore[no-untyped-call]


@dramatiq.actor
def ping() -> str:
    return "pong"
