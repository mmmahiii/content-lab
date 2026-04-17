from __future__ import annotations

import logging
import re
import sys
from collections.abc import Mapping, MutableMapping, Sequence
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
    re.compile(
        r"(key|secret|token|password|salt|credential|authorization|cookie|session)", re.IGNORECASE
    ),
)

_KEY_VALUE_SECRET_PATTERN = re.compile(
    r"""(?ix)
    \b
    (api[_-]?key|access[_-]?key|client[_-]?secret|password|secret|token|authorization|cookie|session(?:id)?|jwt)
    \b
    (\s*[:=]\s*)
    (?:
        "[^"]*"
        |
        '[^']*'
        |
        [^\s,;]+
    )
    """
)

_VALUE_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    _KEY_VALUE_SECRET_PATTERN,
    re.compile(r"(?i)\b(bearer|basic)\s+[^\s]+"),
    re.compile(r"(?i)sk-[a-zA-Z0-9]{8,}"),
)


def _is_sensitive_key(key: str) -> bool:
    return any(pattern.search(key) for pattern in _SECRET_KEY_PATTERNS)


def redact_event_dict(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Structlog processor that replaces values of secret-bearing keys."""
    for key in list(event_dict):
        if _is_sensitive_key(key):
            event_dict[key] = _REDACTED
            continue
        event_dict[key] = redact_sensitive_data(event_dict[key])
    return event_dict


def redact_sensitive_data(value: Any) -> Any:
    """Recursively redact secret-bearing values inside nested payloads."""
    if isinstance(value, Mapping):
        return {
            str(key): (_REDACTED if _is_sensitive_key(str(key)) else redact_sensitive_data(raw))
            for key, raw in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item) for item in value)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive_string(value)
    return value


def redact_sensitive_string(text: str, *, max_len: int = 2_000) -> str:
    """Redact common secret patterns embedded in free-form strings (e.g. exception messages)."""
    s = text if len(text) <= max_len else f"{text[:max_len]}..."
    s = _KEY_VALUE_SECRET_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{_REDACTED}",
        s,
    )
    for pattern in _VALUE_SECRET_PATTERNS:
        if pattern is _KEY_VALUE_SECRET_PATTERN:
            continue
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
