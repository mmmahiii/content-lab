from __future__ import annotations

import json
import logging
from typing import Any

import structlog
import structlog.contextvars

from content_lab_shared.logging import (
    clear_correlation_id,
    configure_logging,
    get_correlation_id,
    redact_event_dict,
    redact_sensitive_data,
    redact_sensitive_string,
    set_correlation_id,
)


class TestCorrelationId:
    def teardown_method(self) -> None:
        clear_correlation_id()
        structlog.contextvars.clear_contextvars()

    def test_default_is_none(self) -> None:
        assert get_correlation_id() is None

    def test_set_and_get(self) -> None:
        set_correlation_id("req-abc-123")
        assert get_correlation_id() == "req-abc-123"

    def test_clear(self) -> None:
        set_correlation_id("req-xyz")
        clear_correlation_id()
        assert get_correlation_id() is None


class TestCorrelationIdInLogs:
    """Verify the structlog processor injects correlation_id into output."""

    def teardown_method(self) -> None:
        clear_correlation_id()
        structlog.contextvars.clear_contextvars()

    def test_correlation_id_appears_in_log(self, capsys: Any) -> None:
        configure_logging(level=logging.DEBUG)
        set_correlation_id("cid-42")
        log = structlog.get_logger()
        log.info("hello")

        captured = capsys.readouterr().out
        payload = json.loads(captured.strip().splitlines()[-1])
        assert payload["correlation_id"] == "cid-42"
        assert payload["event"] == "hello"

    def test_no_correlation_id_when_unset(self, capsys: Any) -> None:
        configure_logging(level=logging.DEBUG)
        log = structlog.get_logger()
        log.info("no_cid")

        captured = capsys.readouterr().out
        payload = json.loads(captured.strip().splitlines()[-1])
        assert "correlation_id" not in payload


class TestRedactEventDict:
    def _call(self, event_dict: dict[str, Any]) -> Any:
        return redact_event_dict(None, "info", event_dict)

    def test_redacts_known_secret_keys(self) -> None:
        ed = {"event": "test", "api_key": "sk-live-xxx", "token": "tok_abc"}
        result = self._call(ed)
        assert result["api_key"] == "***REDACTED***"
        assert result["token"] == "***REDACTED***"
        assert result["event"] == "test"

    def test_leaves_non_secret_keys(self) -> None:
        ed = {"event": "test", "user_id": "u-1", "path": "/health"}
        result = self._call(ed)
        assert result["user_id"] == "u-1"
        assert result["path"] == "/health"

    def test_redacts_password_fields(self) -> None:
        ed = {"event": "test", "db_password": "hunter2"}
        result = self._call(ed)
        assert result["db_password"] == "***REDACTED***"

    def test_case_insensitive(self) -> None:
        ed = {"event": "test", "API_KEY": "abc", "Secret": "xyz"}
        result = self._call(ed)
        assert result["API_KEY"] == "***REDACTED***"
        assert result["Secret"] == "***REDACTED***"

    def test_redacts_nested_payloads(self) -> None:
        ed = {
            "event": "test",
            "metadata": {
                "provider": {
                    "authorization": "Bearer top-secret",
                    "nested": [{"api_key": "abc123"}, {"note": "safe"}],
                }
            },
        }
        result = self._call(ed)
        assert result["metadata"]["provider"]["authorization"] == "***REDACTED***"
        assert result["metadata"]["provider"]["nested"][0]["api_key"] == "***REDACTED***"
        assert result["metadata"]["provider"]["nested"][1]["note"] == "safe"


class TestRedactSensitiveData:
    def test_redacts_sequence_values_recursively(self) -> None:
        redacted = redact_sensitive_data(
            {
                "items": (
                    {"session_id": "sess-123"},
                    {"message": "authorization=super-secret"},
                )
            }
        )
        assert redacted["items"][0]["session_id"] == "***REDACTED***"
        assert redacted["items"][1]["message"] == "authorization=***REDACTED***"


class TestRedactSensitiveString:
    def test_redacts_token_assignment(self) -> None:
        raw = "failed: token=supersecret and ok"
        out = redact_sensitive_string(raw)
        assert "supersecret" not in out
        assert "***REDACTED***" in out

    def test_redacts_header_style_credentials(self) -> None:
        raw = 'request failed authorization: "Bearer secret-token" cookie=session=abc'
        out = redact_sensitive_string(raw)
        assert "secret-token" not in out
        assert "session=abc" not in out
        assert out.count("***REDACTED***") >= 2


class TestConfigureLogging:
    def teardown_method(self) -> None:
        clear_correlation_id()
        structlog.contextvars.clear_contextvars()

    def test_redaction_in_full_pipeline(self, capsys: Any) -> None:
        configure_logging(level=logging.DEBUG, redact=True)
        log = structlog.get_logger()
        log.info("auth_attempt", api_key="sk-live-real-key", user="alice")

        captured = capsys.readouterr().out
        payload = json.loads(captured.strip().splitlines()[-1])
        assert payload["api_key"] == "***REDACTED***"
        assert payload["user"] == "alice"

    def test_no_redaction_when_disabled(self, capsys: Any) -> None:
        configure_logging(level=logging.DEBUG, redact=False)
        log = structlog.get_logger()
        log.info("auth_attempt", api_key="sk-live-real-key")

        captured = capsys.readouterr().out
        payload = json.loads(captured.strip().splitlines()[-1])
        assert payload["api_key"] == "sk-live-real-key"

    def test_configure_with_custom_level(self) -> None:
        configure_logging(level=logging.WARNING)
        root = logging.getLogger()
        assert root.level == logging.WARNING
