"""Deterministic idempotency keys from canonical JSON payloads."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import TypeAlias

# JSON-like tree used for hashing; callers should pass plain data only (no Decimal/date).
JSONValue: TypeAlias = str | int | float | bool | None | dict[str, "JSONValue"] | list["JSONValue"]


def canonical_json_bytes(payload: Mapping[str, JSONValue]) -> bytes:
    """Return UTF-8 bytes of a minified JSON document with stable key ordering."""
    try:
        text = json.dumps(
            dict(payload),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        msg = "payload must be JSON-serializable (use plain dict/list/str/int/float/bool/None)"
        raise ValueError(msg) from exc
    return text.encode("utf-8")


def idempotency_key_from_payload(scope: str, payload: Mapping[str, JSONValue]) -> str:
    """Derive a stable idempotency key from scope + payload.

    Equivalent payloads (including key order in nested dicts) produce the same key.
    """
    normalized = scope.strip()
    if not normalized:
        raise ValueError("scope must be non-empty")

    try:
        body = json.dumps(
            {"scope": normalized, "payload": dict(payload)},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        msg = "payload must be JSON-serializable (use plain dict/list/str/int/float/bool/None)"
        raise ValueError(msg) from exc
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return f"{normalized}:{digest}"
