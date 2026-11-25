"""Turn a Pydantic model into a JSON schema accepted by structured outputs.

Structured outputs support a subset of JSON Schema. Numeric/length constraints are
moved into each field's description (so the model still sees them) and enforced by
Pydantic after the response arrives.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

_CONSTRAINT_HINTS: dict[str, str] = {
    "minLength": "at least {} characters",
    "maxLength": "at most {} characters",
    "minItems": "at least {} items",
    "maxItems": "at most {} items",
    "minimum": "minimum {}",
    "maximum": "maximum {}",
    "exclusiveMinimum": "greater than {}",
    "exclusiveMaximum": "less than {}",
}
_DROPPED_KEYS = frozenset({"title", "default", "examples", "pattern", "uniqueItems", "multipleOf"})


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema(mode="validation")
    transformed = _transform(schema)
    if not isinstance(transformed, dict):  # pragma: no cover - model schemas are objects
        raise TypeError("model schema must be an object")
    return transformed


def _transform(node: Any) -> Any:
    if isinstance(node, list):
        return [_transform(item) for item in node]
    if not isinstance(node, dict):
        return node

    hints: list[str] = []
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in _CONSTRAINT_HINTS:
            hints.append(_CONSTRAINT_HINTS[key].format(value))
            continue
        if key in _DROPPED_KEYS:
            continue
        if key == "const":
            out["enum"] = [value]
            continue
        if key in ("properties", "$defs"):
            out[key] = {name: _transform(sub) for name, sub in value.items()}
            continue
        out[key] = _transform(value)

    if out.get("type") == "object" or "properties" in out:
        out["type"] = "object"
        out["additionalProperties"] = False
        out["required"] = list(out.get("properties", {}).keys())

    if hints:
        description = str(out.get("description", "")).strip()
        joined = "; ".join(hints)
        out["description"] = f"{description} ({joined})" if description else f"({joined})"
    return out
