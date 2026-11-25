"""Request, result and usage types shared by every LLM client."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class LLMUsage:
    """Token usage and estimated cost, summed across attempts of one request."""

    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cost_usd: float | None = None
    served_by_fallback: bool = False

    def combine(self, other: LLMUsage) -> LLMUsage:
        cost: float | None
        if self.cost_usd is None or other.cost_usd is None:
            cost = self.cost_usd if other.cost_usd is None else other.cost_usd
        else:
            cost = round(self.cost_usd + other.cost_usd, 6)
        return LLMUsage(
            model=other.model or self.model,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_input_tokens=self.cache_read_input_tokens + other.cache_read_input_tokens,
            cache_creation_input_tokens=(
                self.cache_creation_input_tokens + other.cache_creation_input_tokens
            ),
            cost_usd=cost,
            served_by_fallback=self.served_by_fallback or other.served_by_fallback,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cost_usd": self.cost_usd,
            "served_by_fallback": self.served_by_fallback,
        }


@dataclass(frozen=True)
class StructuredRequest(Generic[T]):
    """Ask for one JSON object that validates against ``output_model``.

    ``validation_context`` is passed to Pydantic validators (``info.context``), so
    output models can enforce request-specific rules such as a page's blocked phrases.
    """

    purpose: str
    system: str
    prompt: str
    output_model: type[T]
    max_tokens: int | None = None
    effort: str | None = None
    validation_context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StructuredResult(Generic[T]):
    output: T
    usage: LLMUsage
    attempts: int


@dataclass(frozen=True)
class RawCompletion:
    """One provider response, before validation."""

    text: str
    stop_reason: str | None
    usage: LLMUsage
    # Exactly what the provider returned for the assistant turn; replayed unchanged on repair.
    assistant_content: Any = None
    refusal_category: str | None = None
    refusal_explanation: str | None = None
