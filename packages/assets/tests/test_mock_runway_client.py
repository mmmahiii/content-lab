from __future__ import annotations

import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from content_lab_assets.providers.runway import (
    HTTPRunwayClient,
    MockRunwayClient,
    RunwayJobStatus,
)
from content_lab_shared.settings import Settings


def test_from_settings_uses_mock_runway_client_when_mock_mode_enabled() -> None:
    with patch.dict(os.environ, {"RUNWAY_API_MODE": "mock"}, clear=False):
        client = HTTPRunwayClient.from_settings(Settings())

    assert isinstance(client, MockRunwayClient)


def _probe(body: bytes) -> str:
    with TemporaryDirectory() as tmpdir:
        fixture_path = Path(tmpdir) / "final_video.mp4"
        fixture_path.write_bytes(body)
        return subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=width,height:format=duration",
                "-of",
                "default=noprint_wrappers=1",
                str(fixture_path),
            ],
            capture_output=True,
            check=True,
            text=True,
        ).stdout


def _run_mock(client: MockRunwayClient, *, params: dict[str, object], key: str) -> bytes:
    submitted = client.submit_generation(
        task_payload={"request": {"prompt": "Mock intro"}},
        canonical_params=params,
        idempotency_key=key,
    )
    client.get_task(submitted.id)
    return client.download_output(client.get_task(submitted.id)).body


def test_mock_runway_client_reaches_success_with_a_clip_of_the_requested_length() -> None:
    client = MockRunwayClient()

    submitted = client.submit_generation(
        task_payload={"request": {"prompt": "Mock intro card"}},
        canonical_params={"model": "gen4.5", "duration_seconds": 7, "seed": 3},
        idempotency_key="asset.generate:test",
    )
    first_poll = client.get_task(submitted.id)
    second_poll = client.get_task(submitted.id)
    downloaded = client.download_output(second_poll)

    assert first_poll.normalized_status == RunwayJobStatus.RUNNING.value.upper()
    assert second_poll.normalized_status == RunwayJobStatus.SUCCEEDED.value.upper()
    assert second_poll.primary_output_url().endswith("/final_video.mp4")
    assert downloaded.content_type == "video/mp4"
    assert downloaded.filename == "final_video.mp4"
    probe = _probe(downloaded.body)
    assert "width=720" in probe
    assert "height=1280" in probe
    assert "duration=7.000000" in probe


def test_mock_runway_clips_are_deterministic_and_capped_at_ten_seconds() -> None:
    client = MockRunwayClient()

    first = _run_mock(client, params={"duration_seconds": 30, "seed": 1}, key="a")
    again = _run_mock(client, params={"duration_seconds": 30, "seed": 1}, key="b")
    other_seed = _run_mock(client, params={"duration_seconds": 30, "seed": 2}, key="c")

    assert first == again
    assert first != other_seed
    assert "duration=10.000000" in _probe(first)


def test_mock_runway_client_falls_back_to_the_static_fixture_without_ffmpeg() -> None:
    client = MockRunwayClient(ffmpeg_bin="definitely-not-ffmpeg")

    probe = _probe(_run_mock(client, params={"duration_seconds": 6}, key="d"))

    assert "width=90" in probe
    assert "height=160" in probe
    assert "duration=10.000000" in probe
