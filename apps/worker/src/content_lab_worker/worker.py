import os

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from content_lab_shared.logging import configure_logging
from content_lab_worker.correlation import worker_service_context

configure_logging()

broker = RedisBroker(url=os.getenv("REDIS_URL", "redis://localhost:6379/0"))  # type: ignore[no-untyped-call]
dramatiq.set_broker(broker)


@dramatiq.actor
def ping() -> str:
    _ = worker_service_context()
    return "pong"
