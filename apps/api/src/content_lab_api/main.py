from fastapi import FastAPI
from fastapi.responses import JSONResponse

from content_lab_shared.errors import ErrorDetail, ErrorResponse
from content_lab_shared.logging import configure_logging

app = FastAPI(title="Content Lab API", version="0.1.0")


@app.on_event("startup")
async def _startup() -> None:
    configure_logging()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request, exc: Exception):
    # Avoid leaking sensitive details; store full exception in logs only.
    payload = ErrorResponse(error=ErrorDetail(code="internal_error", message="Internal server error"))
    return JSONResponse(status_code=500, content=payload.model_dump())
