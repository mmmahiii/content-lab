from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from content_lab_editing.editor_basic import (
    FINAL_COVER_FILENAME,
    FINAL_VIDEO_FILENAME,
    PHASE1_TEMPLATE_VERSION,
    RetrievedStorageObject,
    render_basic_vertical_edit,
)
from content_lab_editing.instructions import EditInstruction, EditOperation

from ._media_helpers import build_fixture_clip, extract_png_bytes, probe_media


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
    build_fixture_clip(
        output_path=source_path,
        width=1280,
        height=720,
        include_audio=False,
    )

    artifact = render_basic_vertical_edit(source_uri=source_path, workdir=tmp_path / "job")

    output_probe = probe_media(artifact.final_video_path)
    assert artifact.template_version == PHASE1_TEMPLATE_VERSION
    assert artifact.staged_source_path.exists()
    assert artifact.final_video_path.name == FINAL_VIDEO_FILENAME
    assert artifact.cover_image_path.name == FINAL_COVER_FILENAME
    assert artifact.cover_image_path.exists()
    assert artifact.cover_frame_timestamp_seconds == 0.5
    assert artifact.source_had_audio_track is False
    assert artifact.has_audio_track is True
    assert output_probe["width"] == 1080
    assert output_probe["height"] == 1920
    assert output_probe["has_audio_track"] is True


def test_render_basic_vertical_edit_stages_s3_source_and_preserves_audio(tmp_path: Path) -> None:
    source_path = tmp_path / "fixture-with-audio.mp4"
    build_fixture_clip(
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

    output_probe = probe_media(artifact.final_video_path)
    assert storage_client.calls == [storage_uri]
    assert artifact.source_uri == storage_uri
    assert artifact.cover_image_path.exists()
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


def test_render_basic_vertical_edit_applies_overlay_timeline(tmp_path: Path) -> None:
    source_path = tmp_path / "fixture-black.mp4"
    build_fixture_clip(
        output_path=source_path,
        width=720,
        height=1280,
        include_audio=False,
        duration_seconds=1.4,
        video_source="color=c=black:size=720x1280:rate=24",
    )

    artifact = render_basic_vertical_edit(
        source_uri=source_path,
        workdir=tmp_path / "job-overlay",
        overlay_timeline=[
            EditInstruction(
                operation=EditOperation.OVERLAY_TEXT,
                params={
                    "text": "Overlay active",
                    "start": 0.4,
                    "end": 1.0,
                },
            )
        ],
    )

    before_overlay = extract_png_bytes(artifact.final_video_path, timestamp_seconds=0.2)
    during_overlay = extract_png_bytes(artifact.final_video_path, timestamp_seconds=0.6)
    after_overlay = extract_png_bytes(artifact.final_video_path, timestamp_seconds=1.2)

    assert before_overlay == after_overlay
    assert during_overlay != before_overlay
