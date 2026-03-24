"""Runway provider client primitives shared by worker actors."""

from __future__ import annotations

import json
import mimetypes
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from content_lab_shared.settings import Settings

RUNWAY_API_BASE_URL = "https://api.dev.runwayml.com"
RUNWAY_API_VERSION = "2024-11-06"
_RETRYABLE_TASK_STATUSES = frozenset({"PENDING", "RUNNING", "THROTTLED"})
_SUCCESS_TASK_STATUS = "SUCCEEDED"
_FAILED_TASK_STATUSES = frozenset({"FAILED", "CANCELLED"})
_TERMINAL_FAILURE_PREFIXES = ("SAFETY.", "INPUT_PREPROCESSING.SAFETY.")
_RETRYABLE_FAILURE_PREFIXES = (
    "INTERNAL",
    "INPUT_PREPROCESSING.INTERNAL",
)


class RunwayFailureDisposition(StrEnum):
    """How the worker should treat a failed provider task."""

    TERMINAL = "terminal"
    RETRYABLE = "retryable"


@dataclass(frozen=True, slots=True)
class RunwaySubmittedTask:
    """Provider response returned after a successful submission."""

    id: str
    raw_response: dict[str, Any] = field(default_factory=dict)

    def metadata(self) -> dict[str, Any]:
        return {
            "submission": {
                "task_id": self.id,
                "response": dict(self.raw_response),
            }
        }


@dataclass(frozen=True, slots=True)
class RunwayTaskSnapshot:
    """Normalized provider task state used by the worker loop."""

    id: str
    status: str
    output: tuple[str, ...] = ()
    failure_code: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)

    @property
    def normalized_status(self) -> str:
        return self.status.strip().upper()

    @property
    def is_retryable_status(self) -> bool:
        return self.normalized_status in _RETRYABLE_TASK_STATUSES

    @property
    def is_success(self) -> bool:
        return self.normalized_status == _SUCCESS_TASK_STATUS

    @property
    def is_failure(self) -> bool:
        return self.normalized_status in _FAILED_TASK_STATUSES

    def primary_output_url(self) -> str:
        if not self.output:
            raise ValueError("Runway task did not include any output URLs")
        return self.output[0]

    def metadata(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "task": {
                "id": self.id,
                "status": self.normalized_status.lower(),
                "response": dict(self.raw_response),
            }
        }
        if self.failure_code is not None:
            payload["task"]["failure_code"] = self.failure_code
        if self.output:
            payload["task"]["output"] = list(self.output)
        return payload

    @classmethod
    def from_response(cls, response: Mapping[str, Any]) -> RunwayTaskSnapshot:
        output = response.get("output", ())
        output_urls = tuple(str(item).strip() for item in output if str(item).strip())
        failure_code_raw = response.get("failureCode")
        failure_code = None if failure_code_raw in (None, "") else str(failure_code_raw).strip()
        return cls(
            id=str(response["id"]).strip(),
            status=str(response["status"]).strip(),
            output=output_urls,
            failure_code=failure_code,
            raw_response=dict(response),
        )


@dataclass(frozen=True, slots=True)
class RunwayDownloadedAsset:
    """Downloaded media bytes for a successful Runway task."""

    url: str
    body: bytes
    content_type: str | None = None

    @property
    def filename(self) -> str:
        path = urlsplit(self.url).path
        candidate = Path(path).name.strip()
        if candidate:
            return candidate
        extension = _extension_from_content_type(self.content_type)
        return f"runway-output{extension}"


class RunwayClient(Protocol):
    """Provider client boundary used by the worker actor."""

    def submit_generation(
        self,
        *,
        task_payload: Mapping[str, Any],
        canonical_params: Mapping[str, Any],
        idempotency_key: str,
    ) -> RunwaySubmittedTask: ...

    def get_task(self, external_ref: str) -> RunwayTaskSnapshot: ...

    def download_output(self, task: RunwayTaskSnapshot) -> RunwayDownloadedAsset: ...


class HTTPRunwayClient:
    """Small stdlib HTTP client for the phase-1 Runway generation path."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = RUNWAY_API_BASE_URL,
        api_version: str = RUNWAY_API_VERSION,
    ) -> None:
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._api_version = api_version.strip()
        if not self._api_key:
            raise ValueError("Runway API key must not be blank")

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> HTTPRunwayClient:
        resolved = settings or Settings()
        return cls(api_key=resolved.runway_api_key.get_secret_value())

    def submit_generation(
        self,
        *,
        task_payload: Mapping[str, Any],
        canonical_params: Mapping[str, Any],
        idempotency_key: str,
    ) -> RunwaySubmittedTask:
        body = _build_submit_body(task_payload=task_payload, canonical_params=canonical_params)
        body["metadata"] = {"contentLabIdempotencyKey": idempotency_key}
        endpoint = "image_to_video" if "promptImage" in body else "text_to_video"
        response = self._request_json("POST", f"/v1/{endpoint}", payload=body)
        return RunwaySubmittedTask(id=str(response["id"]).strip(), raw_response=response)

    def get_task(self, external_ref: str) -> RunwayTaskSnapshot:
        response = self._request_json("GET", f"/v1/tasks/{external_ref}")
        return RunwayTaskSnapshot.from_response(response)

    def download_output(self, task: RunwayTaskSnapshot) -> RunwayDownloadedAsset:
        url = task.primary_output_url()
        request = Request(url, method="GET")
        with urlopen(request) as response:
            content_type = response.headers.get_content_type()
            return RunwayDownloadedAsset(
                url=url,
                body=response.read(),
                content_type=None if content_type == "application/octet-stream" else content_type,
            )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self._base_url}{path}",
            data=data,
            method=method,
            headers=self._headers(with_json=payload is not None),
        )
        with urlopen(request) as response:
            body = json.loads(response.read().decode("utf-8"))
        if not isinstance(body, dict):
            raise ValueError("Runway API response was not a JSON object")
        return cast(dict[str, Any], body)

    def _headers(self, *, with_json: bool) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "X-Runway-Version": self._api_version,
        }
        if with_json:
            headers["Content-Type"] = "application/json"
        return headers


def classify_failure(failure_code: str | None) -> RunwayFailureDisposition:
    """Classify a failed task using Runway's documented retry guidance."""

    if failure_code is None:
        return RunwayFailureDisposition.RETRYABLE

    normalized = failure_code.strip().upper()
    if normalized == "ASSET.INVALID":
        return RunwayFailureDisposition.TERMINAL
    if normalized.startswith(_TERMINAL_FAILURE_PREFIXES):
        return RunwayFailureDisposition.TERMINAL
    if normalized.startswith(_RETRYABLE_FAILURE_PREFIXES):
        return RunwayFailureDisposition.RETRYABLE
    return RunwayFailureDisposition.TERMINAL


def _build_submit_body(
    *,
    task_payload: Mapping[str, Any],
    canonical_params: Mapping[str, Any],
) -> dict[str, Any]:
    request_payload = _mapping(task_payload.get("request"))
    body: dict[str, Any] = {
        "model": str(canonical_params.get("model", request_payload.get("model", "gen4.5"))),
        "promptText": str(canonical_params.get("prompt", request_payload.get("prompt", ""))),
        "ratio": _runway_ratio(canonical_params.get("ratio") or request_payload.get("ratio")),
        "duration": _int_or_default(
            canonical_params.get("duration_seconds", request_payload.get("duration_seconds")),
            default=6,
        ),
    }

    seed = canonical_params.get("seed", request_payload.get("seed"))
    if seed is not None:
        body["seed"] = int(seed)

    prompt_image = request_payload.get("prompt_image") or request_payload.get("prompt_image_uri")
    if prompt_image is not None and str(prompt_image).strip():
        body["promptImage"] = str(prompt_image).strip()

    return body


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _int_or_default(value: Any, *, default: int) -> int:
    if value is None:
        return default
    return int(value)


def _runway_ratio(value: Any) -> str:
    if value is None:
        return "720:1280"
    normalized = str(value).strip().lower()
    mapping = {
        "9:16": "720:1280",
        "16:9": "1280:720",
    }
    return mapping.get(normalized, str(value).strip())


def _extension_from_content_type(content_type: str | None) -> str:
    if content_type is None:
        return ".bin"
    guessed = mimetypes.guess_extension(content_type, strict=False)
    if guessed is None:
        return ".bin"
    return guessed


__all__ = [
    "HTTPRunwayClient",
    "RUNWAY_API_BASE_URL",
    "RUNWAY_API_VERSION",
    "RunwayClient",
    "RunwayDownloadedAsset",
    "RunwayFailureDisposition",
    "RunwaySubmittedTask",
    "RunwayTaskSnapshot",
    "classify_failure",
]
