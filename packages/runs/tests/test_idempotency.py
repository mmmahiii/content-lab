from __future__ import annotations

import hashlib
import json
from decimal import Decimal

import pytest

from content_lab_runs import JSONValue, canonical_json_bytes, idempotency_key_from_payload


def test_idempotency_key_stable_across_key_order() -> None:
    a: dict[str, JSONValue] = {"b": 1, "a": {"d": 2, "c": 3}}
    b: dict[str, JSONValue] = {"a": {"c": 3, "d": 2}, "b": 1}
    k1 = idempotency_key_from_payload("scope.x", a)
    k2 = idempotency_key_from_payload("scope.x", b)
    assert k1 == k2
    assert k1.startswith("scope.x:")
    assert len(k1.split(":", 1)[1]) == 64


def test_idempotency_key_differs_for_scope() -> None:
    payload = {"x": 1}
    k1 = idempotency_key_from_payload("a", payload)
    k2 = idempotency_key_from_payload("b", payload)
    assert k1 != k2


def test_idempotency_key_differs_for_payload() -> None:
    assert idempotency_key_from_payload("s", {"x": 1}) != idempotency_key_from_payload(
        "s", {"x": 2}
    )


def test_idempotency_scope_strips_and_rejects_empty() -> None:
    k = idempotency_key_from_payload("  my.scope  ", {})
    assert k.startswith("my.scope:")
    with pytest.raises(ValueError, match="non-empty"):
        idempotency_key_from_payload("   ", {})


def test_idempotency_rejects_non_serializable() -> None:
    with pytest.raises(ValueError, match="JSON-serializable"):
        idempotency_key_from_payload("s", {"d": Decimal("1")})  # type: ignore[dict-item]


def test_canonical_json_bytes_matches_key_body_shape() -> None:
    payload = {"z": 1, "y": 2}
    direct = canonical_json_bytes(payload)
    key = idempotency_key_from_payload("unit", payload)
    digest = key.split(":", 1)[1]

    body = json.dumps(
        {"scope": "unit", "payload": dict(payload)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    assert digest == hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert direct == json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
