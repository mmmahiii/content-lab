"""Typed failures for LLM calls. Callers catch ``LLMError`` and fall back."""

from __future__ import annotations

from collections.abc import Sequence

from content_lab_intelligence.types import LLMUsage


class LLMError(Exception):
    """Base class for every LLM failure the creative layer may fall back from."""

    retryable: bool = False

    def __init__(self, message: str, *, usage: LLMUsage | None = None) -> None:
        super().__init__(message)
        self.usage = usage


class LLMNotConfiguredError(LLMError):
    """No provider or credentials are configured."""


class LLMUnavailableError(LLMError):
    """Network failure, timeout, rate limit or provider 5xx after SDK retries."""

    retryable = True


class LLMRequestError(LLMError):
    """The provider rejected the request (auth, permissions, bad request, unknown model)."""


class LLMRefusalError(LLMError):
    """The model (and any configured fallback) declined the request."""

    def __init__(
        self,
        message: str,
        *,
        category: str | None = None,
        explanation: str | None = None,
        usage: LLMUsage | None = None,
    ) -> None:
        super().__init__(message, usage=usage)
        self.category = category
        self.explanation = explanation


class LLMOutputError(LLMError):
    """The model kept returning output that failed validation."""

    def __init__(
        self,
        message: str,
        *,
        validation_errors: Sequence[str] = (),
        usage: LLMUsage | None = None,
    ) -> None:
        super().__init__(message, usage=usage)
        self.validation_errors = list(validation_errors)
