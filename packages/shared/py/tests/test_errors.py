from __future__ import annotations

from content_lab_shared.errors import (
    BudgetExceededError,
    ConfigurationError,
    ContentLabError,
    ErrorDetail,
    ErrorResponse,
    ExternalServiceError,
)


class TestErrorModels:
    """Existing Pydantic error-response models still work."""

    def test_error_detail_defaults(self) -> None:
        d = ErrorDetail(code="bad_request", message="oops")
        assert d.code == "bad_request"
        assert d.message == "oops"
        assert d.details == {}

    def test_error_response_roundtrip(self) -> None:
        resp = ErrorResponse(
            error=ErrorDetail(code="not_found", message="gone", details={"id": 42})
        )
        data = resp.model_dump()
        assert data["error"]["code"] == "not_found"
        assert data["error"]["details"]["id"] == 42


class TestContentLabError:
    def test_base_error(self) -> None:
        err = ContentLabError("something broke")
        assert str(err) == "something broke"
        assert err.code == "content_lab_error"

    def test_custom_code(self) -> None:
        err = ContentLabError("bad", code="custom_code")
        assert err.code == "custom_code"

    def test_to_error_detail(self) -> None:
        err = ContentLabError("fail", code="test_code")
        detail = err.to_error_detail()
        assert isinstance(detail, ErrorDetail)
        assert detail.code == "test_code"
        assert detail.message == "fail"

    def test_is_exception(self) -> None:
        assert issubclass(ContentLabError, Exception)


class TestConfigurationError:
    def test_code(self) -> None:
        err = ConfigurationError("DATABASE_URL is missing")
        assert err.code == "configuration_error"
        assert "DATABASE_URL" in str(err)

    def test_is_content_lab_error(self) -> None:
        assert issubclass(ConfigurationError, ContentLabError)


class TestBudgetExceededError:
    def test_default_message(self) -> None:
        err = BudgetExceededError()
        assert err.code == "budget_exceeded"
        assert "budget" in str(err).lower()

    def test_custom_message(self) -> None:
        err = BudgetExceededError("Only $2 left")
        assert str(err) == "Only $2 left"

    def test_is_content_lab_error(self) -> None:
        assert issubclass(BudgetExceededError, ContentLabError)


class TestExternalServiceError:
    def test_attributes(self) -> None:
        err = ExternalServiceError("Runway", "rate limited")
        assert err.service == "Runway"
        assert err.detail == "rate limited"
        assert err.code == "external_service_error"
        assert "Runway" in str(err)
        assert "rate limited" in str(err)

    def test_to_error_detail(self) -> None:
        err = ExternalServiceError("MinIO", "connection refused")
        detail = err.to_error_detail()
        assert detail.code == "external_service_error"
        assert "MinIO" in detail.message

    def test_is_content_lab_error(self) -> None:
        assert issubclass(ExternalServiceError, ContentLabError)
