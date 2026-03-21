from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

import pytest
import structlog.contextvars
from fastapi.testclient import TestClient

from content_lab_api.main import X_REQUEST_ID_HEADER, app
from content_lab_shared.logging import configure_logging


def _ensure_pytest_unhandled_route() -> str:
    path = "/__pytest/unhandled"
    paths = {getattr(r, "path", None) for r in app.routes}
    if path not in paths:

        @app.get(path, include_in_schema=False)
        def _pytest_unhandled() -> None:
            raise RuntimeError("deliberate failure token=supersecretvalue")

    return path


_UNHANDLED_PATH = _ensure_pytest_unhandled_route()


@pytest.fixture(autouse=True)
def _reset_logging_context() -> Any:
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()


def test_propagates_x_request_id() -> None:
    client = TestClient(app)
    rid = "client-req-abc-01"
    resp = client.get("/health", headers={"X-Request-Id": rid})
    assert resp.status_code == 200
    assert resp.headers.get(X_REQUEST_ID_HEADER.lower()) == rid


def test_generates_x_request_id_when_missing() -> None:
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    raw = resp.headers.get(X_REQUEST_ID_HEADER.lower())
    assert raw is not None
    uuid.UUID(raw)


def test_replaces_invalid_incoming_request_id() -> None:
    client = TestClient(app)
    resp = client.get("/health", headers={"X-Request-Id": "not valid!!!"})
    assert resp.status_code == 200
    out = resp.headers.get(X_REQUEST_ID_HEADER.lower())
    assert out is not None
    assert out != "not valid!!!"
    uuid.UUID(out)


def test_logs_include_request_correlation_fields(capsys: Any) -> None:
    configure_logging(level=logging.DEBUG)
    client = TestClient(app)
    rid = "log-test-req-99"
    client.get("/health", headers={"X-Request-Id": rid})

    captured = capsys.readouterr().out
    lines = [ln for ln in captured.strip().splitlines() if ln.strip()]
    http_events = []
    for ln in lines:
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if row.get("event") == "http_request":
            http_events.append(row)
    assert http_events, "expected http_request JSON log line"
    payload = http_events[-1]
    assert payload.get("request_id") == rid
    assert payload.get("correlation_id") == rid
    assert payload.get("http_method") == "GET"
    assert payload.get("http_path") == "/health"
    assert payload.get("actor") == "anonymous"


def test_unhandled_error_response_and_logs_redact_secrets(capsys: Any) -> None:
    configure_logging(level=logging.DEBUG)
    client = TestClient(app, raise_server_exceptions=False)
    rid = "err-req-001"
    resp = client.get(_UNHANDLED_PATH, headers={"X-Request-Id": rid})
    assert resp.status_code == 500
    assert resp.headers.get(X_REQUEST_ID_HEADER.lower()) == rid
    body = resp.json()
    assert body["error"]["code"] == "internal_error"
    assert body["error"]["details"]["request_id"] == rid

    captured = capsys.readouterr().out
    lines = [ln for ln in captured.strip().splitlines() if ln.strip()]
    unhandled_lines = [ln for ln in lines if "unhandled_exception" in ln]
    assert unhandled_lines
    payload = json.loads(unhandled_lines[-1])
    assert payload.get("request_id") == rid
    detail = payload.get("detail", "")
    assert "supersecretvalue" not in detail
    assert re.search(r"REDACTED|redacted", detail, re.IGNORECASE)
