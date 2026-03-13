from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from content_lab_shared.errors import ErrorDetail, ErrorResponse
from content_lab_shared.logging import configure_logging

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    yield


app = FastAPI(title="Content Lab API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_exception",
        exc_type=type(exc).__name__,
        detail=str(exc),
        path=request.url.path,
        method=request.method,
        exc_info=exc,
    )
    payload = ErrorResponse(
        error=ErrorDetail(code="internal_error", message="Internal server error")
    )
    return JSONResponse(status_code=500, content=payload.model_dump())
