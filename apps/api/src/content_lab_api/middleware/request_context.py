from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable

import structlog
import structlog.contextvars
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from content_lab_api.constants import X_REQUEST_ID_HEADER
from content_lab_shared.logging import ANONYMOUS_ACTOR, clear_correlation_id, set_correlation_id

logger = structlog.get_logger()

X_ACTOR_HEADER = "x-actor-id"

_REQUEST_ID_SAFE = re.compile(r"^[a-zA-Z0-9._-]{1,128}$")


def _normalize_request_id(raw: str | None) -> str:
    if raw is None:
        return str(uuid.uuid4())
    tid = raw.strip()
    if not tid or not _REQUEST_ID_SAFE.fullmatch(tid):
        return str(uuid.uuid4())
    return tid


def _actor_from_request(request: Request) -> str:
    raw = request.headers.get(X_ACTOR_HEADER)
    if not raw:
        return ANONYMOUS_ACTOR
    actor = raw.strip()
    if not actor or len(actor) > 256:
        return ANONYMOUS_ACTOR
    return actor


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Generate or propagate ``X-Request-Id`` and bind HTTP context for structured logs."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = _normalize_request_id(request.headers.get(X_REQUEST_ID_HEADER))
        request.state.request_id = request_id
        actor = _actor_from_request(request)
        request.state.actor = actor

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            http_method=request.method,
            http_path=request.url.path,
            actor=actor,
        )
        set_correlation_id(request_id)
        try:
            response = await call_next(request)
        except BaseException:
            structlog.contextvars.clear_contextvars()
            clear_correlation_id()
            raise

        logger.info("http_request", status_code=response.status_code)
        structlog.contextvars.clear_contextvars()
        clear_correlation_id()

        response.headers[X_REQUEST_ID_HEADER] = request_id
        return response
