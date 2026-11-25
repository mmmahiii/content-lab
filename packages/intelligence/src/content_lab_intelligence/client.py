"""LLM clients: a shared validate-and-repair loop, the Anthropic implementation, a factory."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from pydantic import ValidationError

from content_lab_intelligence.config import LLMSettings, estimate_cost_usd
from content_lab_intelligence.errors import (
    LLMError,
    LLMNotConfiguredError,
    LLMOutputError,
    LLMRefusalError,
    LLMRequestError,
    LLMUnavailableError,
)
from content_lab_intelligence.schema import strict_json_schema
from content_lab_intelligence.types import (
    LLMUsage,
    RawCompletion,
    StructuredRequest,
    StructuredResult,
    T,
)

logger = logging.getLogger("content_lab_intelligence")

REFUSAL_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_MAX_ERROR_CHARS = 1_500

CallObserver = Callable[[str, LLMUsage, int], None]


class LLMClient(Protocol):
    """Anything that can return a validated structured object for a request."""

    def generate_structured(self, request: StructuredRequest[T]) -> StructuredResult[T]: ...


class StructuredLLMClient(ABC):
    """Validate provider output with Pydantic; on failure, ask once more with the errors."""

    def __init__(self, *, max_output_attempts: int = 2, on_call: CallObserver | None = None):
        if max_output_attempts < 1:
            raise ValueError("max_output_attempts must be >= 1")
        self.max_output_attempts = max_output_attempts
        self._on_call = on_call

    @abstractmethod
    def _complete(
        self,
        request: StructuredRequest[Any],
        *,
        schema: Mapping[str, Any],
        messages: list[dict[str, Any]],
    ) -> RawCompletion: ...

    def generate_structured(self, request: StructuredRequest[T]) -> StructuredResult[T]:
        schema = strict_json_schema(request.output_model)
        messages: list[dict[str, Any]] = [{"role": "user", "content": request.prompt}]
        total: LLMUsage | None = None
        errors: list[str] = []

        for attempt in range(1, self.max_output_attempts + 1):
            completion = self._complete(request, schema=schema, messages=messages)
            total = completion.usage if total is None else total.combine(completion.usage)
            self._record(request.purpose, completion.usage, attempt)

            if completion.stop_reason == "refusal":
                raise LLMRefusalError(
                    f"{request.purpose}: model declined the request",
                    category=completion.refusal_category,
                    explanation=completion.refusal_explanation,
                    usage=total,
                )
            if completion.stop_reason == "max_tokens":
                error = "Output was cut off at max_tokens; return a shorter, complete JSON object."
            else:
                try:
                    output = request.output_model.model_validate_json(
                        completion.text or "",
                        context=dict(request.validation_context),
                    )
                except ValidationError as exc:
                    error = _summarize_validation_error(exc)
                else:
                    return StructuredResult(output=output, usage=total, attempts=attempt)

            errors.append(error)
            logger.warning(
                "llm_output_invalid purpose=%s attempt=%d error=%s",
                request.purpose,
                attempt,
                error[:300],
            )
            messages = [
                {"role": "user", "content": request.prompt},
                {
                    "role": "assistant",
                    "content": completion.assistant_content or completion.text or "{}",
                },
                {
                    "role": "user",
                    "content": (
                        "That JSON failed validation:\n"
                        f"{error}\n"
                        "Return the complete corrected JSON object, following every rule."
                    ),
                },
            ]

        raise LLMOutputError(
            f"{request.purpose}: output failed validation after "
            f"{self.max_output_attempts} attempt(s)",
            validation_errors=errors,
            usage=total,
        )

    def _record(self, purpose: str, usage: LLMUsage, attempt: int) -> None:
        logger.info(
            "llm_call purpose=%s model=%s attempt=%d input_tokens=%d output_tokens=%d "
            "cache_read=%d cache_write=%d cost_usd=%s fallback=%s",
            purpose,
            usage.model,
            attempt,
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_read_input_tokens,
            usage.cache_creation_input_tokens,
            "unknown" if usage.cost_usd is None else f"{usage.cost_usd:.6f}",
            usage.served_by_fallback,
        )
        if self._on_call is not None:
            self._on_call(purpose, usage, attempt)


class AnthropicLLMClient(StructuredLLMClient):
    """Claude via the official SDK, with JSON-schema structured outputs."""

    def __init__(
        self,
        settings: LLMSettings | None = None,
        *,
        sdk_client: Any | None = None,
        on_call: CallObserver | None = None,
    ) -> None:
        self.settings = settings or LLMSettings.from_env()
        super().__init__(max_output_attempts=self.settings.max_output_attempts, on_call=on_call)
        self._sdk_client = sdk_client

    @property
    def sdk(self) -> Any:
        if self._sdk_client is None:
            import anthropic

            self._sdk_client = anthropic.Anthropic(
                timeout=self.settings.request_timeout_seconds,
                max_retries=self.settings.max_retries,
            )
        return self._sdk_client

    def _complete(
        self,
        request: StructuredRequest[Any],
        *,
        schema: Mapping[str, Any],
        messages: list[dict[str, Any]],
    ) -> RawCompletion:
        import anthropic

        params: dict[str, Any] = {
            "model": self.settings.model,
            "max_tokens": request.max_tokens or self.settings.max_tokens,
            "system": request.system,
            "messages": messages,
            "cache_control": {"type": "ephemeral"},
            "output_config": {
                "effort": request.effort or self.settings.effort,
                "format": {"type": "json_schema", "schema": dict(schema)},
            },
        }
        if self.settings.refusal_fallbacks:
            params["betas"] = [REFUSAL_FALLBACK_BETA]
            params["fallbacks"] = "default"

        try:
            response = self.sdk.beta.messages.create(**params)
        except (
            anthropic.AuthenticationError,
            anthropic.PermissionDeniedError,
            anthropic.NotFoundError,
            anthropic.BadRequestError,
        ) as exc:
            raise LLMRequestError(f"{request.purpose}: request rejected ({exc})") from exc
        except (
            anthropic.RateLimitError,
            anthropic.APITimeoutError,
            anthropic.APIConnectionError,
        ) as exc:
            raise LLMUnavailableError(f"{request.purpose}: provider unavailable ({exc})") from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise LLMUnavailableError(f"{request.purpose}: provider error ({exc})") from exc
            raise LLMRequestError(f"{request.purpose}: request rejected ({exc})") from exc
        except anthropic.AnthropicError as exc:
            # e.g. no credentials could be resolved when the client was built.
            raise LLMNotConfiguredError(f"{request.purpose}: {exc}") from exc

        return completion_from_response(response, requested_model=self.settings.model)


def completion_from_response(response: Any, *, requested_model: str) -> RawCompletion:
    """Map an SDK ``BetaMessage`` to a ``RawCompletion``."""

    text = "".join(
        getattr(block, "text", "")
        for block in getattr(response, "content", None) or []
        if getattr(block, "type", None) == "text"
    )
    raw_usage = getattr(response, "usage", None)
    model = str(getattr(response, "model", None) or requested_model)
    input_tokens = int(getattr(raw_usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(raw_usage, "output_tokens", 0) or 0)
    cache_read = int(getattr(raw_usage, "cache_read_input_tokens", 0) or 0)
    cache_write = int(getattr(raw_usage, "cache_creation_input_tokens", 0) or 0)
    iterations = getattr(raw_usage, "iterations", None) or []
    usage = LLMUsage(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_write,
        cost_usd=estimate_cost_usd(
            model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_write,
        ),
        served_by_fallback=any(
            getattr(entry, "type", None) == "fallback_message" for entry in iterations
        ),
    )
    stop_details = getattr(response, "stop_details", None)
    return RawCompletion(
        text=text,
        stop_reason=getattr(response, "stop_reason", None),
        usage=usage,
        assistant_content=getattr(response, "content", None),
        refusal_category=getattr(stop_details, "category", None),
        refusal_explanation=getattr(stop_details, "explanation", None),
    )


def build_llm_client(
    settings: LLMSettings | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> LLMClient | None:
    """Return a configured client, or ``None`` when LLM calls are disabled or unconfigured."""

    resolved = settings or LLMSettings.from_env(env)
    if not resolved.is_enabled(env):
        return None
    return AnthropicLLMClient(resolved)


def require_llm_client(client: LLMClient | None) -> LLMClient:
    if client is None:
        raise LLMNotConfiguredError(
            "No LLM configured: set ANTHROPIC_API_KEY (and optionally CONTENT_LAB_LLM_MODEL)."
        )
    return client


def _summarize_validation_error(exc: ValidationError) -> str:
    lines = []
    for item in exc.errors(include_url=False):
        location = ".".join(str(part) for part in item.get("loc", ())) or "(root)"
        lines.append(f"- {location}: {item.get('msg', 'invalid')}")
    return "\n".join(lines)[:_MAX_ERROR_CHARS]


__all__ = [
    "REFUSAL_FALLBACK_BETA",
    "AnthropicLLMClient",
    "CallObserver",
    "LLMClient",
    "LLMError",
    "StructuredLLMClient",
    "build_llm_client",
    "completion_from_response",
    "require_llm_client",
]
