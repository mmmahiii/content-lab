"""Provider adapter boundary for phase-1 video generation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from content_lab_assets.asset_key import Phase1ProviderLockError, validate_phase1_provider_model
from content_lab_shared.logging import redact_sensitive_string

REDACTED_VALUE = "***REDACTED***"
DEFAULT_RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
_SENSITIVE_KEY_PARTS = frozenset({"authorization", "api_key", "token", "secret", "password"})


class ProviderRetryPolicy(BaseModel):
    """Retry settings for transient provider failures."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_attempts: int = Field(default=3, ge=1, le=10)
    initial_backoff_seconds: float = Field(default=0.5, ge=0.0, le=60.0)
    backoff_multiplier: float = Field(default=2.0, ge=1.0, le=10.0)
    max_backoff_seconds: float = Field(default=4.0, ge=0.0, le=300.0)
    retryable_status_codes: frozenset[int] = Field(
        default_factory=lambda: DEFAULT_RETRYABLE_STATUS_CODES
    )

    def delay_seconds_for_attempt(self, attempt_number: int) -> float:
        """Return the bounded exponential-backoff delay for a retry attempt."""

        if attempt_number < 1:
            raise ValueError("attempt_number must be at least 1")
        delay = self.initial_backoff_seconds * (self.backoff_multiplier ** (attempt_number - 1))
        return min(delay, self.max_backoff_seconds)


class ProviderVideoSubmitRequest(BaseModel):
    """Canonical provider submission inputs for phase-1 video generation."""

    model_config = ConfigDict(extra="forbid")

    asset_class: str
    provider: str
    model: str
    prompt: str = Field(min_length=1, max_length=1_000)
    ratio: str = Field(min_length=1, max_length=32)
    duration_seconds: int = Field(ge=1, le=60)
    idempotency_key: str = Field(min_length=1, max_length=256)
    seed: int | None = Field(default=None, ge=0)
    init_image_uri: str | None = None
    reference_image_uris: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderVideoSubmitResult(BaseModel):
    """Initial provider submission result."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    status: str | None = None
    raw_response: dict[str, Any] = Field(default_factory=dict)


class ProviderVideoPollResult(BaseModel):
    """Provider task status and output metadata."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    status: str
    output_urls: list[str] = Field(default_factory=list)
    failure_reason: str | None = None
    raw_response: dict[str, Any] = Field(default_factory=dict)


class ProviderVideoDownloadResult(BaseModel):
    """Downloaded provider output bytes and metadata."""

    model_config = ConfigDict(extra="forbid")

    source_url: str
    content: bytes
    content_type: str | None = None
    content_length: int | None = None


class ProviderError(RuntimeError):
    """Base provider adapter error."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        retryable: bool = False,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable
        self.status_code = status_code


class ProviderAuthenticationError(ProviderError):
    """Provider rejected or was missing credentials."""

    def __init__(self, message: str, *, provider: str, status_code: int | None = None) -> None:
        super().__init__(message, provider=provider, retryable=False, status_code=status_code)


class ProviderTransientError(ProviderError):
    """Provider failure that is safe to retry."""

    def __init__(self, message: str, *, provider: str, status_code: int | None = None) -> None:
        super().__init__(message, provider=provider, retryable=True, status_code=status_code)


class ProviderTaskFailedError(ProviderError):
    """Provider task reached a terminal failed state."""

    def __init__(self, message: str, *, provider: str) -> None:
        super().__init__(message, provider=provider, retryable=False)


@runtime_checkable
class VideoProviderAdapter(Protocol):
    """Boundary that higher layers depend on instead of raw provider SDK calls."""

    provider_name: str
    model_name: str

    def submit(self, request: ProviderVideoSubmitRequest) -> ProviderVideoSubmitResult: ...

    def poll(self, task_id: str) -> ProviderVideoPollResult: ...

    def download(self, url: str) -> ProviderVideoDownloadResult: ...


def get_phase1_video_provider(
    *,
    provider: str,
    model: str,
    api_key: str,
    base_url: str | None = None,
    transport: Any | None = None,
    retry_policy: ProviderRetryPolicy | None = None,
    logger: Any | None = None,
    sleep_fn: Any | None = None,
) -> VideoProviderAdapter:
    """Return the single supported phase-1 production video provider adapter."""

    normalized_provider, normalized_model = validate_phase1_provider_model(
        provider=provider,
        model=model,
    )

    from content_lab_assets.providers.runway.client import RunwayGen45Client

    return RunwayGen45Client(
        api_key=api_key,
        base_url=base_url,
        transport=transport,
        retry_policy=retry_policy,
        logger=logger,
        sleep_fn=sleep_fn,
        provider_name=normalized_provider,
        model_name=normalized_model,
    )


def ensure_phase1_provider_model(*, provider: str, model: str) -> tuple[str, str]:
    """Validate and normalize the locked phase-1 provider/model pair."""

    return validate_phase1_provider_model(provider=provider, model=model)


def redact_provider_data(value: Any) -> Any:
    """Recursively redact provider secrets from logs and error details."""

    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if _is_sensitive_key(key):
                redacted[key] = REDACTED_VALUE
            else:
                redacted[key] = redact_provider_data(raw_value)
        return redacted
    if isinstance(value, list):
        return [redact_provider_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_provider_data(item) for item in value)
    if isinstance(value, str):
        return redact_sensitive_string(value)
    return value


def _is_sensitive_key(key: str) -> bool:
    lowered_key = key.strip().lower().replace("-", "_")
    return any(part in lowered_key for part in _SENSITIVE_KEY_PARTS)


__all__ = [
    "DEFAULT_RETRYABLE_STATUS_CODES",
    "Phase1ProviderLockError",
    "ProviderAuthenticationError",
    "ProviderError",
    "ProviderRetryPolicy",
    "ProviderTaskFailedError",
    "ProviderTransientError",
    "ProviderVideoDownloadResult",
    "ProviderVideoPollResult",
    "ProviderVideoSubmitRequest",
    "ProviderVideoSubmitResult",
    "REDACTED_VALUE",
    "VideoProviderAdapter",
    "ensure_phase1_provider_model",
    "get_phase1_video_provider",
    "redact_provider_data",
]
