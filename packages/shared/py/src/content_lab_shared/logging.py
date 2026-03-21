from __future__ import annotations

import logging
import re
import sys
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog

ANONYMOUS_ACTOR = "anonymous"

# ---------------------------------------------------------------------------
# Correlation-ID primitives
# ---------------------------------------------------------------------------
_correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def set_correlation_id(cid: str) -> None:
    """Store a correlation ID for the current async/thread context."""
    _correlation_id_var.set(cid)


def get_correlation_id() -> str | None:
    """Return the current correlation ID (or *None*)."""
    return _correlation_id_var.get()


def clear_correlation_id() -> None:
    """Reset the correlation ID for the current context."""
    _correlation_id_var.set(None)


def _inject_correlation_id(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Structlog processor that adds ``correlation_id`` when available."""
    cid = _correlation_id_var.get()
    if cid is not None:
        event_dict["correlation_id"] = cid
    return event_dict


# ---------------------------------------------------------------------------
# Secret-redaction processor
# ---------------------------------------------------------------------------
_REDACTED = "***REDACTED***"

_SECRET_KEY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(key|secret|token|password|salt|credential)", re.IGNORECASE),
)


def _is_sensitive_key(key: str) -> bool:
    return any(p.search(key) for p in _SECRET_KEY_PATTERNS)


def redact_event_dict(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Structlog processor that replaces values of secret-bearing keys."""
    for key in list(event_dict):
        if _is_sensitive_key(key):
            event_dict[key] = _REDACTED
    return event_dict


_VALUE_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(api[_-]?key|password|secret|token|auth)\s*[=:]\s*[^\s,;]+"),
    re.compile(r"(?i)bearer\s+[^\s]+"),
    re.compile(r"(?i)sk-[a-zA-Z0-9]{8,}"),
)


def redact_sensitive_string(text: str, *, max_len: int = 2_000) -> str:
    """Redact common secret patterns embedded in free-form strings (e.g. exception messages)."""
    s = text if len(text) <= max_len else f"{text[:max_len]}…"
    for pattern in _VALUE_SECRET_PATTERNS:
        s = pattern.sub(_REDACTED, s)
    return s


# ---------------------------------------------------------------------------
# Public configuration entry-point
# ---------------------------------------------------------------------------
def configure_logging(level: int = logging.INFO, *, redact: bool = True) -> None:
    """Configure stdlib + structlog for consistent JSON logging across services.

    Parameters
    ----------
    level:
        The minimum log level (default ``logging.INFO``).
    redact:
        When *True* (the default), automatically replace values whose keys
        match common secret-field patterns (``*key*``, ``*secret*``, etc.).
    """
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
        force=True,
    )

    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        _inject_correlation_id,
    ]
    if redact:
        processors.append(redact_event_dict)
    processors.extend(
        [
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )
