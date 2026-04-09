from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from content_lab_assets.asset_key import Phase1ProviderLockError
from content_lab_assets.providers.runway import RUNWAY_GEN45_MAX_DURATION_SECONDS
from content_lab_assets.providers.base import (
    ProviderRetryPolicy,
    ProviderTaskFailedError,
    ProviderVideoSubmitRequest,
    VideoProviderAdapter,
    get_phase1_video_provider,
)
from content_lab_assets.providers.runway.client import (
    RUNWAY_IMAGE_TO_VIDEO_PATH,
    RUNWAY_TASK_PATH_TEMPLATE,
    RUNWAY_TEXT_TO_VIDEO_PATH,
    RunwayGen45Client,
    RunwayHttpResponse,
)


class RecordingTransport:
    def __init__(self, responses: list[RunwayHttpResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        json_body: Mapping[str, Any] | None = None,
        timeout_seconds: float = 30.0,
    ) -> RunwayHttpResponse:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "json_body": None if json_body is None else dict(json_body),
                "timeout_seconds": timeout_seconds,
            }
        )
        if not self._responses:
            raise AssertionError("no queued transport responses")
        return self._responses.pop(0)


class RecordingLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    def info(self, event: str, /, **kwargs: Any) -> None:
        self.events.append(("info", event, kwargs))

    def warning(self, event: str, /, **kwargs: Any) -> None:
        self.events.append(("warning", event, kwargs))

    def error(self, event: str, /, **kwargs: Any) -> None:
        self.events.append(("error", event, kwargs))


def _submit_request(*, init_image_uri: str | None = None) -> ProviderVideoSubmitRequest:
    return ProviderVideoSubmitRequest(
        asset_class="clip",
        provider="runway",
        model="gen4.5",
        prompt="A cinematic launch shot",
        ratio="720:1280",
        duration_seconds=6,
        seed=7,
        idempotency_key="asset.generate:abc123",
        init_image_uri=init_image_uri,
        reference_image_uris=["https://example.com/reference.png"],
        metadata={"shot_id": "hero-1"},
    )


def test_phase1_video_provider_factory_returns_locked_adapter_protocol() -> None:
    provider = get_phase1_video_provider(provider="Runway", model="GEN4.5", api_key="top-secret")

    assert isinstance(provider, VideoProviderAdapter)
    assert isinstance(provider, RunwayGen45Client)
    assert provider.provider_name == "runway"
    assert provider.model_name == "gen4.5"


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        ("pika", "gen4.5"),
        ("runway", "gen4"),
    ],
)
def test_phase1_video_provider_factory_rejects_non_locked_path(
    provider: str,
    model: str,
) -> None:
    with pytest.raises(Phase1ProviderLockError):
        get_phase1_video_provider(provider=provider, model=model, api_key="top-secret")


def test_submit_clamps_duration_to_runway_api_max() -> None:
    transport = RecordingTransport(
        responses=[RunwayHttpResponse(status_code=200, json_body={"id": "task-123"})]
    )
    provider = RunwayGen45Client(api_key="super-secret", transport=transport)
    request = _submit_request().model_copy(update={"duration_seconds": 15})
    provider.submit(request)
    assert transport.calls[0]["json_body"]["duration"] == RUNWAY_GEN45_MAX_DURATION_SECONDS


def test_submit_uses_text_to_video_path_and_redacts_provider_secret_logs() -> None:
    transport = RecordingTransport(
        responses=[RunwayHttpResponse(status_code=200, json_body={"id": "task-123"})]
    )
    logger = RecordingLogger()
    provider = RunwayGen45Client(api_key="super-secret", transport=transport, logger=logger)

    result = provider.submit(_submit_request())

    assert result.task_id == "task-123"
    assert transport.calls[0]["url"].endswith(RUNWAY_TEXT_TO_VIDEO_PATH)
    assert transport.calls[0]["headers"]["Authorization"] == "Bearer super-secret"
    assert transport.calls[0]["headers"]["Idempotency-Key"] == "asset.generate:abc123"
    assert transport.calls[0]["json_body"] == {
        "model": "gen4.5",
        "promptText": "A cinematic launch shot",
        "ratio": "720:1280",
        "duration": 6,
        "seed": 7,
        "referenceImages": [{"uri": "https://example.com/reference.png"}],
    }

    request_logs = [entry for entry in logger.events if entry[1] == "provider_request"]
    assert request_logs
    logged_request = request_logs[0][2]["request"]
    assert logged_request["headers"]["Authorization"] == "***REDACTED***"
    assert "super-secret" not in repr(request_logs)


def test_submit_uses_image_to_video_when_init_image_is_present() -> None:
    transport = RecordingTransport(
        responses=[RunwayHttpResponse(status_code=200, json_body={"id": "task-456"})]
    )
    provider = RunwayGen45Client(api_key="super-secret", transport=transport)

    provider.submit(_submit_request(init_image_uri="https://example.com/init.png"))

    assert transport.calls[0]["url"].endswith(RUNWAY_IMAGE_TO_VIDEO_PATH)
    assert transport.calls[0]["json_body"]["promptImage"] == "https://example.com/init.png"


def test_submit_retries_transient_provider_errors_with_backoff() -> None:
    transport = RecordingTransport(
        responses=[
            RunwayHttpResponse(status_code=429, json_body={"message": "rate limited"}),
            RunwayHttpResponse(status_code=200, json_body={"id": "task-789"}),
        ]
    )
    logger = RecordingLogger()
    sleep_calls: list[float] = []
    provider = RunwayGen45Client(
        api_key="super-secret",
        transport=transport,
        logger=logger,
        sleep_fn=sleep_calls.append,
        retry_policy=ProviderRetryPolicy(max_attempts=3, initial_backoff_seconds=0.25),
    )

    result = provider.submit(_submit_request())

    assert result.task_id == "task-789"
    assert len(transport.calls) == 2
    assert sleep_calls == [0.25]
    retry_logs = [entry for entry in logger.events if entry[1] == "provider_retry"]
    assert retry_logs[0][2]["delay_seconds"] == 0.25


def test_poll_returns_succeeded_task_outputs() -> None:
    transport = RecordingTransport(
        responses=[
            RunwayHttpResponse(
                status_code=200,
                json_body={
                    "id": "task-123",
                    "status": "SUCCEEDED",
                    "output": [{"url": "https://cdn.runwayml.com/task-123/video.mp4"}],
                },
            )
        ]
    )
    provider = RunwayGen45Client(api_key="super-secret", transport=transport)

    result = provider.poll("task-123")

    assert result.status == "SUCCEEDED"
    assert result.output_urls == ["https://cdn.runwayml.com/task-123/video.mp4"]
    assert transport.calls[0]["url"].endswith(RUNWAY_TASK_PATH_TEMPLATE.format(task_id="task-123"))


def test_poll_raises_non_retryable_error_for_failed_task() -> None:
    transport = RecordingTransport(
        responses=[
            RunwayHttpResponse(
                status_code=200,
                json_body={"id": "task-123", "status": "FAILED", "failure": "provider refused"},
            )
        ]
    )
    provider = RunwayGen45Client(api_key="super-secret", transport=transport)

    with pytest.raises(ProviderTaskFailedError, match="provider refused"):
        provider.poll("task-123")


def test_download_retries_transient_errors_and_returns_bytes() -> None:
    transport = RecordingTransport(
        responses=[
            RunwayHttpResponse(status_code=503, body=b"busy"),
            RunwayHttpResponse(
                status_code=200,
                headers={"Content-Type": "video/mp4", "Content-Length": "5"},
                body=b"video",
            ),
        ]
    )
    sleep_calls: list[float] = []
    provider = RunwayGen45Client(
        api_key="super-secret",
        transport=transport,
        sleep_fn=sleep_calls.append,
        retry_policy=ProviderRetryPolicy(max_attempts=3, initial_backoff_seconds=0.1),
    )

    result = provider.download("https://cdn.runwayml.com/task-123/video.mp4")

    assert result.content == b"video"
    assert result.content_type == "video/mp4"
    assert result.content_length == 5
    assert sleep_calls == [0.1]


def test_submit_surfaces_auth_errors_without_retry() -> None:
    transport = RecordingTransport(
        responses=[RunwayHttpResponse(status_code=401, json_body={"message": "bad key"})]
    )
    provider = RunwayGen45Client(api_key="super-secret", transport=transport)

    with pytest.raises(Exception, match="bad key"):
        provider.submit(_submit_request())
    assert len(transport.calls) == 1
