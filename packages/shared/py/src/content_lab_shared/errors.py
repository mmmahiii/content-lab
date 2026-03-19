from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# API response models (unchanged)
# ---------------------------------------------------------------------------
class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ---------------------------------------------------------------------------
# Domain exception hierarchy
# ---------------------------------------------------------------------------
class ContentLabError(Exception):
    """Base exception for all Content Lab services."""

    def __init__(self, message: str, *, code: str = "content_lab_error") -> None:
        super().__init__(message)
        self.code = code

    def to_error_detail(self) -> ErrorDetail:
        return ErrorDetail(code=self.code, message=str(self))


class ConfigurationError(ContentLabError):
    """A required configuration value is missing or invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="configuration_error")


class BudgetExceededError(ContentLabError):
    """The monthly spend budget has been exhausted."""

    def __init__(self, message: str = "Monthly budget exceeded") -> None:
        super().__init__(message, code="budget_exceeded")


class ExternalServiceError(ContentLabError):
    """A call to an external provider (Runway, S3, etc.) failed."""

    def __init__(self, service: str, detail: str) -> None:
        super().__init__(f"{service}: {detail}", code="external_service_error")
        self.service = service
        self.detail = detail
