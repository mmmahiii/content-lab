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


def test_mock_runway_client_reaches_success_with_deterministic_mp4_output() -> None:
    client = MockRunwayClient()

    submitted = client.submit_generation(
        task_payload={"request": {"prompt": "Black intro card"}},
        canonical_params={"model": "gen4.5"},
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
    assert downloaded.body.startswith(b"\x00\x00\x00")

    with TemporaryDirectory() as tmpdir:
        fixture_path = Path(tmpdir) / downloaded.filename
        fixture_path.write_bytes(downloaded.body)
        probe = subprocess.run(
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
        )

    assert "width=90" in probe.stdout
    assert "height=160" in probe.stdout
    assert "duration=10.000000" in probe.stdout
