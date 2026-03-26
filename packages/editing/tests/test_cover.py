from __future__ import annotations

from pathlib import Path

from content_lab_editing.cover import (
    DEFAULT_COVER_TIMESTAMP_SECONDS,
    extract_cover_frame,
    resolve_cover_frame_timestamp,
)

from ._media_helpers import build_fixture_clip, extract_png_bytes


def test_resolve_cover_frame_timestamp_stays_inside_short_clips() -> None:
    assert resolve_cover_frame_timestamp(duration_seconds=3.0) == DEFAULT_COVER_TIMESTAMP_SECONDS
    assert resolve_cover_frame_timestamp(duration_seconds=0.4) == 0.2
    assert resolve_cover_frame_timestamp(duration_seconds=0.0) == 0.0


def test_extract_cover_frame_creates_png_at_default_timestamp(tmp_path: Path) -> None:
    source_path = tmp_path / "fixture-cover.mp4"
    build_fixture_clip(
        output_path=source_path,
        width=640,
        height=360,
        include_audio=False,
        duration_seconds=1.4,
    )

    artifact = extract_cover_frame(
        video_path=source_path,
        output_path=tmp_path / "cover.png",
    )

    assert artifact.image_path.exists()
    assert artifact.timestamp_seconds == DEFAULT_COVER_TIMESTAMP_SECONDS
    assert artifact.image_path.read_bytes() == extract_png_bytes(
        source_path,
        timestamp_seconds=DEFAULT_COVER_TIMESTAMP_SECONDS,
    )
