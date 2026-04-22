import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from content_lab_api.constants import X_REQUEST_ID_HEADER
from content_lab_api.middleware import RequestContextMiddleware
from content_lab_api.routes import api_router
from content_lab_shared.errors import ErrorDetail, ErrorResponse
from content_lab_shared.logging import ANONYMOUS_ACTOR, configure_logging, redact_sensitive_string

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    yield


def _parse_cors_origins() -> list[str]:
    # Comma-separated list. Default to the local operator console's dev origins so
    # the web workspace can call the API directly from the browser out of the box.
    raw = os.getenv(
        "CONTENT_LAB_API_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    return [item.strip() for item in raw.split(",") if item.strip()]


app = FastAPI(title="Content Lab API", version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[X_REQUEST_ID_HEADER],
)
app.include_router(api_router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    safe_detail = redact_sensitive_string(str(exc))
    logger.error(
        "unhandled_exception",
        exc_type=type(exc).__name__,
        detail=safe_detail,
        request_id=request_id,
        http_path=request.url.path,
        http_method=request.method,
        actor=getattr(request.state, "actor", ANONYMOUS_ACTOR),
        exc_info=exc,
    )
    payload = ErrorResponse(
        error=ErrorDetail(
            code="internal_error",
            message="Internal server error",
            details={"request_id": request_id},
        )
    )
    return JSONResponse(
        status_code=500,
        content=payload.model_dump(),
        headers={X_REQUEST_ID_HEADER: request_id},
    )
