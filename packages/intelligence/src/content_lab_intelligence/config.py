"""Runtime configuration and pricing for LLM calls."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

Provider = Literal["anthropic", "none"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_EFFORT: Effort = "medium"

ENV_PROVIDER = "CONTENT_LAB_LLM_PROVIDER"
ENV_MODEL = "CONTENT_LAB_LLM_MODEL"
ENV_EFFORT = "CONTENT_LAB_LLM_EFFORT"
ENV_MAX_TOKENS = "CONTENT_LAB_LLM_MAX_TOKENS"
ENV_TIMEOUT = "CONTENT_LAB_LLM_TIMEOUT_SECONDS"
ENV_MAX_RETRIES = "CONTENT_LAB_LLM_MAX_RETRIES"
ENV_REFUSAL_FALLBACKS = "CONTENT_LAB_LLM_REFUSAL_FALLBACKS"

# Any of these means the Anthropic SDK can resolve credentials on its own.
CREDENTIAL_ENV_VARS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_PROFILE",
    "ANTHROPIC_FEDERATION_RULE_ID",
)

_EFFORTS: frozenset[str] = frozenset({"low", "medium", "high", "xhigh", "max"})


@dataclass(frozen=True)
class ModelPricing:
    """USD per million tokens (first-party Claude API list prices)."""

    input: float
    output: float
    cache_read: float
    cache_write: float


# Estimates for cost logging only; billing is the source of truth.
PRICING_PER_MTOK: dict[str, ModelPricing] = {
    "claude-sonnet-5-5": ModelPricing(input=2.00, output=10.00, cache_read=0.10, cache_write=2.50),
    "claude-opus-5-5": ModelPricing(input=4.00, output=20.00, cache_read=0.20, cache_write=5.00),
    "claude-haiku-5-5": ModelPricing(input=0.10, output=0.50, cache_read=0.01, cache_write=0.125),
}


@dataclass(frozen=True)
class LLMSettings:
    """How the creative layer talks to the LLM provider."""

    provider: Provider = "anthropic"
    model: str = DEFAULT_MODEL
    effort: Effort = DEFAULT_EFFORT
    max_tokens: int = 8_000
    request_timeout_seconds: float = 90.0
    max_retries: int = 2
    max_output_attempts: int = 2
    refusal_fallbacks: bool = True

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> LLMSettings:
        source = os.environ if env is None else env
        provider_raw = source.get(ENV_PROVIDER, "anthropic").strip().lower() or "anthropic"
        if provider_raw not in ("anthropic", "none"):
            raise ValueError(f"{ENV_PROVIDER} must be 'anthropic' or 'none', got {provider_raw!r}")
        effort_raw = source.get(ENV_EFFORT, DEFAULT_EFFORT).strip().lower() or DEFAULT_EFFORT
        if effort_raw not in _EFFORTS:
            raise ValueError(f"{ENV_EFFORT} must be one of {sorted(_EFFORTS)}, got {effort_raw!r}")
        return cls(
            provider=provider_raw,  # type: ignore[arg-type]
            model=source.get(ENV_MODEL, DEFAULT_MODEL).strip() or DEFAULT_MODEL,
            effort=effort_raw,  # type: ignore[arg-type]
            max_tokens=_int(source, ENV_MAX_TOKENS, 8_000, minimum=256),
            request_timeout_seconds=float(_int(source, ENV_TIMEOUT, 90, minimum=5)),
            max_retries=_int(source, ENV_MAX_RETRIES, 2, minimum=0),
            refusal_fallbacks=source.get(ENV_REFUSAL_FALLBACKS, "1").strip().lower()
            not in ("0", "false", "no", "off"),
        )

    def has_credentials(self, env: Mapping[str, str] | None = None) -> bool:
        source = os.environ if env is None else env
        return any(source.get(name, "").strip() for name in CREDENTIAL_ENV_VARS)

    def is_enabled(self, env: Mapping[str, str] | None = None) -> bool:
        """True when LLM calls should be attempted at all."""

        return self.provider != "none" and self.has_credentials(env)


def estimate_cost_usd(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
) -> float | None:
    pricing = PRICING_PER_MTOK.get(model)
    if pricing is None:
        return None
    total = (
        input_tokens * pricing.input
        + output_tokens * pricing.output
        + cache_read_input_tokens * pricing.cache_read
        + cache_creation_input_tokens * pricing.cache_write
    )
    return round(total / 1_000_000, 6)


def _int(source: Mapping[str, str], name: str, default: int, *, minimum: int) -> int:
    raw = source.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")
    return value
