"""Runway phase-1 `gen4.5` provider adapter."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import structlog

from content_lab_assets.providers.base import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderRetryPolicy,
    ProviderTaskFailedError,
    ProviderTransientError,
    ProviderVideoDownloadResult,
    ProviderVideoPollResult,
    ProviderVideoSubmitRequest,
    ProviderVideoSubmitResult,
    ensure_phase1_provider_model,
    redact_provider_data,
)
from content_lab_assets.providers.runway import RUNWAY_GEN45_MAX_DURATION_SECONDS

RUNWAY_API_BASE_URL = "https://api.dev.runwayml.com"
RUNWAY_API_VERSION = "2024-11-06"
RUNWAY_IMAGE_TO_VIDEO_PATH = "/v1/image_to_video"
RUNWAY_TEXT_TO_VIDEO_PATH = "/v1/text_to_video"
RUNWAY_TASK_PATH_TEMPLATE = "/v1/tasks/{task_id}"
RUNWAY_FAILURE_STATUSES = frozenset({"FAILED", "CANCELLED", "ABORTED"})


@dataclass(frozen=True)
class RunwayHttpResponse:
    """Provider HTTP response wrapper used for transport injection."""

    status_code: int
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    json_body: dict[str, Any] | list[Any] | None = None

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class RunwayTransport(Protocol):
    """Minimal transport protocol for provider HTTP calls."""

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        json_body: Mapping[str, Any] | None = None,
        timeout_seconds: float = 30.0,
    ) -> RunwayHttpResponse: ...


class RunwayGen45Client:
    """Phase-1 production adapter for Runway `gen4.5` video generation."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        transport: RunwayTransport | None = None,
        retry_policy: ProviderRetryPolicy | None = None,
        logger: Any | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        provider_name: str = "runway",
        model_name: str = "gen4.5",
    ) -> None:
        normalized_provider, normalized_model = ensure_phase1_provider_model(
            provider=provider_name,
            model=model_name,
        )
        self.provider_name = normalized_provider
        self.model_name = normalized_model
        self._api_key = api_key
        self._base_url = (base_url or RUNWAY_API_BASE_URL).rstrip("/")
        self._transport = transport or UrlLibRunwayTransport()
        self._retry_policy = retry_policy or ProviderRetryPolicy()
        self._logger = logger or structlog.get_logger(__name__)
        self._sleep_fn = sleep_fn or time.sleep

    def submit(self, request: ProviderVideoSubmitRequest) -> ProviderVideoSubmitResult:
        normalized_provider, normalized_model = ensure_phase1_provider_model(
            provider=request.provider,
            model=request.model,
        )
        if normalized_provider != self.provider_name or normalized_model != self.model_name:
            raise ProviderError(
                "provider adapter does not support the requested provider/model",
                provider=self.provider_name,
            )

        duration = max(1, min(int(request.duration_seconds), RUNWAY_GEN45_MAX_DURATION_SECONDS))
        body: dict[str, Any] = {
            "model": self.model_name,
            "promptText": request.prompt,
            "ratio": request.ratio,
            "duration": duration,
        }
        if request.seed is not None:
            body["seed"] = request.seed
        if request.reference_image_uris:
            body["referenceImages"] = [{"uri": uri} for uri in request.reference_image_uris]

        path = RUNWAY_TEXT_TO_VIDEO_PATH
        if request.init_image_uri:
            path = RUNWAY_IMAGE_TO_VIDEO_PATH
            body["promptImage"] = request.init_image_uri

        response = self._request_json(
            operation="submit",
            method="POST",
            path=path,
            json_body=body,
            extra_headers={"Idempotency-Key": request.idempotency_key},
        )

        task_id = _require_text_field(response, field_name="id")
        status = _optional_text_field(response, field_name="status")
        return ProviderVideoSubmitResult(task_id=task_id, status=status, raw_response=response)

    def poll(self, task_id: str) -> ProviderVideoPollResult:
        response = self._request_json(
            operation="poll",
            method="GET",
            path=RUNWAY_TASK_PATH_TEMPLATE.format(task_id=task_id),
        )
        status = _require_text_field(response, field_name="status").upper()
        failure_reason = _extract_failure_reason(response)
        output_urls = _extract_output_urls(response)

        if status in RUNWAY_FAILURE_STATUSES:
            raise ProviderTaskFailedError(
                failure_reason or f"Runway task {task_id} ended with status {status}",
                provider=self.provider_name,
            )

        return ProviderVideoPollResult(
            task_id=_optional_text_field(response, field_name="id") or task_id,
            status=status,
            output_urls=output_urls,
            failure_reason=failure_reason,
            raw_response=response,
        )

    def download(self, url: str) -> ProviderVideoDownloadResult:
        response = self._with_retries(
            operation="download",
            execute=lambda: self._download_once(url),
        )
        return ProviderVideoDownloadResult(
            source_url=url,
            content=response.body,
            content_type=response.headers.get("Content-Type"),
            content_length=_parse_content_length(response.headers.get("Content-Length")),
        )

    def _request_json(
        self,
        *,
        operation: str,
        method: str,
        path: str,
        json_body: Mapping[str, Any] | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        response = self._with_retries(
            operation=operation,
            execute=lambda: self._request_once(
                method=method,
                url=f"{self._base_url}{path}",
                json_body=json_body,
                extra_headers=extra_headers,
            ),
        )
        if not isinstance(response.json_body, dict):
            raise ProviderError(
                f"Runway returned a non-object JSON payload during {operation}",
                provider=self.provider_name,
                status_code=response.status_code,
            )
        return response.json_body

    def _request_once(
        self,
        *,
        method: str,
        url: str,
        json_body: Mapping[str, Any] | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> RunwayHttpResponse:
        headers = self._build_api_headers(extra_headers=extra_headers)
        self._log(
            "info",
            "provider_request",
            operation=method.lower(),
            url=url,
            request={"headers": dict(headers), "json": dict(json_body or {})},
        )
        response = self._transport.request(
            method=method,
            url=url,
            headers=headers,
            json_body=json_body,
        )
        self._log(
            "info",
            "provider_response",
            operation=method.lower(),
            url=url,
            response={"status_code": response.status_code, "json": response.json_body},
        )
        self._raise_for_http_error(response=response, operation=method.lower())
        return response

    def _download_once(self, url: str) -> RunwayHttpResponse:
        self._log(
            "info",
            "provider_request",
            operation="download",
            url=url,
            request={"headers": {}},
        )
        response = self._transport.request(method="GET", url=url, headers={})
        self._log(
            "info",
            "provider_response",
            operation="download",
            url=url,
            response={
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "content_length": len(response.body),
            },
        )
        self._raise_for_http_error(response=response, operation="download")
        return response

    def _raise_for_http_error(
        self,
        *,
        response: RunwayHttpResponse,
        operation: str,
    ) -> None:
        if 200 <= response.status_code < 300:
            return

        detail = _response_detail(response)
        message = f"Runway {operation} request failed with status {response.status_code}: {detail}"
        if response.status_code in {401, 403}:
            raise ProviderAuthenticationError(
                message,
                provider=self.provider_name,
                status_code=response.status_code,
            )
        if response.status_code in self._retry_policy.retryable_status_codes:
            raise ProviderTransientError(
                message,
                provider=self.provider_name,
                status_code=response.status_code,
            )
        raise ProviderError(
            message,
            provider=self.provider_name,
            status_code=response.status_code,
        )

    def _with_retries(
        self,
        *,
        operation: str,
        execute: Callable[[], RunwayHttpResponse],
    ) -> RunwayHttpResponse:
        for attempt_number in range(1, self._retry_policy.max_attempts + 1):
            try:
                return execute()
            except ProviderTransientError as exc:
                if attempt_number >= self._retry_policy.max_attempts:
                    raise
                delay_seconds = self._retry_policy.delay_seconds_for_attempt(attempt_number)
                self._log(
                    "warning",
                    "provider_retry",
                    operation=operation,
                    attempt_number=attempt_number,
                    delay_seconds=delay_seconds,
                    error=str(exc),
                )
                self._sleep_fn(delay_seconds)

        raise AssertionError("retry loop exited unexpectedly")

    def _build_api_headers(
        self,
        *,
        extra_headers: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Runway-Version": RUNWAY_API_VERSION,
        }
        if extra_headers is not None:
            headers.update(dict(extra_headers))
        return headers

    def _log(self, level: str, event: str, **kwargs: Any) -> None:
        log_method = cast(Callable[..., Any], getattr(self._logger, level))
        log_method(event, **redact_provider_data(kwargs))


class UrlLibRunwayTransport:
    """`urllib` transport used by the production Runway adapter."""

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        json_body: Mapping[str, Any] | None = None,
        timeout_seconds: float = 30.0,
    ) -> RunwayHttpResponse:
        body_bytes = None if json_body is None else json.dumps(dict(json_body)).encode("utf-8")
        request = Request(
            url=url,
            data=body_bytes,
            headers=dict(headers),
            method=method,
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                payload = response.read()
                return RunwayHttpResponse(
                    status_code=response.status,
                    headers=dict(response.headers.items()),
                    body=payload,
                    json_body=_decode_json_payload(payload, response.headers.get("Content-Type")),
                )
        except HTTPError as exc:
            payload = exc.read()
            return RunwayHttpResponse(
                status_code=exc.code,
                headers=dict(exc.headers.items()),
                body=payload,
                json_body=_decode_json_payload(payload, exc.headers.get("Content-Type")),
            )
        except URLError as exc:
            raise ProviderTransientError(
                f"Runway transport error: {exc.reason}",
                provider="runway",
            ) from exc


def _decode_json_payload(
    payload: bytes,
    content_type: str | None,
) -> dict[str, Any] | list[Any] | None:
    if not payload:
        return None
    if content_type is not None and "json" not in content_type.lower():
        return None
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if isinstance(decoded, dict | list):
        return decoded
    return None


def _require_text_field(payload: Mapping[str, Any], *, field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ProviderError(
            f"Runway response is missing `{field_name}`",
            provider="runway",
        )
    return value


def _optional_text_field(payload: Mapping[str, Any], *, field_name: str) -> str | None:
    value = payload.get(field_name)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _extract_failure_reason(payload: Mapping[str, Any]) -> str | None:
    for key in ("failure", "error", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, Mapping):
            nested_message = _optional_text_field(value, field_name="message")
            if nested_message is not None:
                return nested_message
    return None


def _extract_output_urls(payload: Mapping[str, Any]) -> list[str]:
    urls: list[str] = []
    for key in ("output", "outputs", "artifacts", "assets"):
        urls.extend(_urls_from_value(payload.get(key)))
    deduped_urls: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if url not in seen:
            deduped_urls.append(url)
            seen.add(url)
    return deduped_urls


def _urls_from_value(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.startswith("http") else []
    if isinstance(value, Mapping):
        collected_urls: list[str] = []
        for key in ("url", "uri"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.startswith("http"):
                collected_urls.append(candidate)
        for nested_key in ("output", "outputs", "artifacts", "assets"):
            collected_urls.extend(_urls_from_value(value.get(nested_key)))
        return collected_urls
    if isinstance(value, list):
        list_urls: list[str] = []
        for item in value:
            list_urls.extend(_urls_from_value(item))
        return list_urls
    return []


def _response_detail(response: RunwayHttpResponse) -> str:
    if isinstance(response.json_body, Mapping):
        failure_reason = _extract_failure_reason(response.json_body)
        if failure_reason is not None:
            return failure_reason
    text = response.text.strip()
    return text or "no response body"


def _parse_content_length(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


__all__ = [
    "RUNWAY_API_BASE_URL",
    "RUNWAY_API_VERSION",
    "RUNWAY_FAILURE_STATUSES",
    "RUNWAY_IMAGE_TO_VIDEO_PATH",
    "RUNWAY_TASK_PATH_TEMPLATE",
    "RUNWAY_TEXT_TO_VIDEO_PATH",
    "RunwayGen45Client",
    "RunwayHttpResponse",
    "RunwayTransport",
    "UrlLibRunwayTransport",
]
