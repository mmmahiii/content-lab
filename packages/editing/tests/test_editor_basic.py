from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from content_lab_editing.editor_basic import (
    FINAL_VIDEO_FILENAME,
    PHASE1_TEMPLATE_VERSION,
    RetrievedStorageObject,
    render_basic_vertical_edit,
)


@dataclass(slots=True)
class _FakeRetrievedObject:
    body: bytes
    content_type: str | None = None


class _RecordingStorageClient:
    def __init__(self, payload: _FakeRetrievedObject) -> None:
        self._payload = payload
        self.calls: list[str] = []

    def get_object(self, *, storage_uri: str) -> RetrievedStorageObject:
        self.calls.append(storage_uri)
        return self._payload


def test_render_basic_vertical_edit_adds_silence_for_local_clip_without_audio(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "fixture-no-audio.mp4"
    _build_fixture_clip(
        output_path=source_path,
        width=1280,
        height=720,
        include_audio=False,
    )

    artifact = render_basic_vertical_edit(source_uri=source_path, workdir=tmp_path / "job")

    output_probe = _probe_media(artifact.final_video_path)
    assert artifact.template_version == PHASE1_TEMPLATE_VERSION
    assert artifact.staged_source_path.exists()
    assert artifact.final_video_path.name == FINAL_VIDEO_FILENAME
    assert artifact.source_had_audio_track is False
    assert artifact.has_audio_track is True
    assert output_probe["width"] == 1080
    assert output_probe["height"] == 1920
    assert output_probe["has_audio_track"] is True


def test_render_basic_vertical_edit_stages_s3_source_and_preserves_audio(tmp_path: Path) -> None:
    source_path = tmp_path / "fixture-with-audio.mp4"
    _build_fixture_clip(
        output_path=source_path,
        width=720,
        height=720,
        include_audio=True,
    )
    storage_uri = "s3://content-lab/assets/raw/test/source.mp4"
    storage_client = _RecordingStorageClient(
        _FakeRetrievedObject(
            body=source_path.read_bytes(),
            content_type="video/mp4",
        )
    )

    artifact = render_basic_vertical_edit(
        source_uri=storage_uri,
        workdir=tmp_path / "job-s3",
        storage_client=storage_client,
    )

    output_probe = _probe_media(artifact.final_video_path)
    assert storage_client.calls == [storage_uri]
    assert artifact.source_uri == storage_uri
    assert artifact.source_had_audio_track is True
    assert artifact.has_audio_track is True
    assert output_probe["width"] == 1080
    assert output_probe["height"] == 1920
    assert output_probe["has_audio_track"] is True


def test_render_basic_vertical_edit_requires_storage_client_for_s3_sources(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="storage_client is required"):
        render_basic_vertical_edit(
            source_uri="s3://content-lab/assets/raw/test/source.mp4",
            workdir=tmp_path / "job-missing-storage",
        )


def _build_fixture_clip(
    *,
    output_path: Path,
    width: int,
    height: int,
    include_audio: bool,
) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size={width}x{height}:rate=24",
    ]
    if include_audio:
        command.extend(
            [
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=880:sample_rate=48000",
            ]
        )

    command.extend(["-t", "1.2"])
    if include_audio:
        command.extend(["-map", "0:v:0", "-map", "1:a:0"])

    command.extend(
        [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
        ]
    )
    if include_audio:
        command.extend(["-c:a", "aac", "-ac", "2", "-ar", "48000"])

    command.append(str(output_path))
    _run_command(command)


def _probe_media(path: Path) -> dict[str, object]:
    completed = _run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    )
    payload = json.loads(completed.stdout)
    streams = payload["streams"]
    video_stream = next(stream for stream in streams if stream["codec_type"] == "video")
    return {
        "width": int(video_stream["width"]),
        "height": int(video_stream["height"]),
        "has_audio_track": any(stream["codec_type"] == "audio" for stream in streams),
    }


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip() or "no output captured"
        raise RuntimeError(details)
    return completed
