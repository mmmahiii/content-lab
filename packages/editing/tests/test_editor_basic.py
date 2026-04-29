from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from content_lab_editing.edit_plan import SceneAwareEditPlan, SceneEditPlanSegment
from content_lab_editing.editor_basic import (
    FINAL_COVER_FILENAME,
    FINAL_VIDEO_FILENAME,
    OVERLAY_RENDER_TRACE_FILENAME,
    PHASE1_TEMPLATE_VERSION,
    RetrievedStorageObject,
    render_basic_vertical_edit,
)
from content_lab_editing.instructions import EditInstruction, EditOperation
from content_lab_editing.templates import (
    EDITORIAL_TEMPLATE_METADATA_KEY,
    EDITORIAL_TEMPLATE_VERSION_METADATA_KEY,
    HOOK_FIRST_V1,
)
from content_lab_storage.paths import OVERLAY_RENDER_TRACE_FILENAME

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
    assert artifact.rendered_overlay_manifest.overlays == ()
    assert artifact.overlay_render_trace_path.name == OVERLAY_RENDER_TRACE_FILENAME
    assert artifact.overlay_render_trace_path.exists()
    assert artifact.staged_segment_paths == (artifact.staged_source_path,)
    assert artifact.overlay_render_trace_path is not None
    assert artifact.overlay_render_trace is not None
    trace_path = artifact.final_video_path.parent / OVERLAY_RENDER_TRACE_FILENAME
    assert trace_path.exists()
    assert artifact.overlay_render_trace_path == trace_path
    assert artifact.overlay_render_trace["overlay_count"] == 0
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
    assert artifact.rendered_overlay_manifest.overlays == ()
    assert artifact.overlay_render_trace_path.name == OVERLAY_RENDER_TRACE_FILENAME
    assert artifact.overlay_render_trace_path.exists()

    output_probe = probe_media(artifact.final_video_path)
    assert output_probe["height"] == 1920
    assert output_probe["has_audio_track"] is True


def test_render_basic_vertical_edit_requires_storage_client_for_s3_sources(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="storage_client is required"):
        render_basic_vertical_edit(
            source_uri="s3://content-lab/assets/raw/test/source.mp4",
            workdir=tmp_path / "job-missing-storage",
        )


def test_render_basic_vertical_edit_rejects_probe_mismatch_vs_expected_timeline(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "fixture-2s.mp4"
    build_fixture_clip(
        output_path=source_path,
        width=720,
        height=1280,
        include_audio=False,
        duration_seconds=2.0,
    )
    with pytest.raises(ValueError, match="Source media duration"):
        render_basic_vertical_edit(
            source_uri=source_path,
            workdir=tmp_path / "job-mismatch",
            expected_timeline_duration_seconds=10,
        )


def test_render_basic_vertical_edit_accepts_matching_expected_timeline(tmp_path: Path) -> None:
    source_path = tmp_path / "fixture-5s.mp4"
    build_fixture_clip(
        output_path=source_path,
        width=720,
        height=1280,
        include_audio=True,
        duration_seconds=5.0,
    )
    artifact = render_basic_vertical_edit(
        source_uri=source_path,
        workdir=tmp_path / "job-match",
        expected_timeline_duration_seconds=5,
    )
    assert artifact.final_video_path.exists()


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

    report = artifact.overlay_render_report
    assert report is not None
    assert report["render_authority"] == "overlay_timeline_argument_only"
    assert len(report["overlays"]) == 1
    overlay_row = report["overlays"][0]
    assert overlay_row["source_path"] == "script.overlay_timeline[0]"
    assert overlay_row["final_render_text"] == "Overlay active"

    assert artifact.rendered_overlay_manifest.schema_version == "rendered_overlay_manifest_v1"
    assert len(artifact.rendered_overlay_manifest.overlays) == 1
    assert artifact.rendered_overlay_manifest.overlays[0].final_render_text == "Overlay active"
    assert artifact.overlay_render_trace_path.name == OVERLAY_RENDER_TRACE_FILENAME
    assert artifact.overlay_render_trace_path.exists()

    before_overlay = extract_png_bytes(artifact.final_video_path, timestamp_seconds=0.2)
    during_overlay = extract_png_bytes(artifact.final_video_path, timestamp_seconds=0.6)
    after_overlay = extract_png_bytes(artifact.final_video_path, timestamp_seconds=1.2)

    assert before_overlay == after_overlay
    assert during_overlay != before_overlay
    assert artifact.overlay_render_trace is not None
    assert artifact.overlay_render_trace["overlay_count"] == 1


def test_render_basic_vertical_edit_assembles_scene_aware_plan(tmp_path: Path) -> None:
    hook_source = tmp_path / "hook-red.mp4"
    value_source = tmp_path / "value-blue.mp4"
    build_fixture_clip(
        output_path=hook_source,
        width=640,
        height=640,
        include_audio=False,
        duration_seconds=0.9,
        video_source="color=c=red:size=640x640:rate=24",
    )
    build_fixture_clip(
        output_path=value_source,
        width=1280,
        height=720,
        include_audio=False,
        duration_seconds=0.9,
        video_source="color=c=blue:size=1280x720:rate=24",
    )
    edit_plan = SceneAwareEditPlan(
        segments=[
            SceneEditPlanSegment(
                segment_id="segment-001",
                scene_id="scene-hook",
                purpose="hook",
                source_uri=str(hook_source),
                duration_seconds=0.6,
                timeline_start_seconds=0.0,
            ),
            SceneEditPlanSegment(
                segment_id="segment-002",
                scene_id="scene-value",
                purpose="value",
                source_uri=str(value_source),
                duration_seconds=0.6,
                timeline_start_seconds=0.6,
            ),
        ]
    )

    artifact = render_basic_vertical_edit(
        source_uri=hook_source,
        workdir=tmp_path / "job-scenes",
        edit_plan=edit_plan,
    )

    output_probe = probe_media(artifact.final_video_path)
    assert artifact.final_video_path.name == FINAL_VIDEO_FILENAME
    assert len(artifact.staged_segment_paths) == 2
    assert artifact.staged_segment_paths[0].exists()
    assert artifact.staged_segment_paths[1].exists()
    assert output_probe["width"] == 1080
    assert output_probe["height"] == 1920
    assert output_probe["has_audio_track"] is True
    duration_seconds = output_probe["duration_seconds"]
    assert isinstance(duration_seconds, float)
    assert 1.0 <= duration_seconds <= 1.5

    first_frame = extract_png_bytes(artifact.final_video_path, timestamp_seconds=0.2)
    second_frame = extract_png_bytes(artifact.final_video_path, timestamp_seconds=0.9)
    assert first_frame != second_frame


def test_render_basic_vertical_edit_applies_editorial_template(tmp_path: Path) -> None:
    hook_source = tmp_path / "hook-red.mp4"
    value_source = tmp_path / "value-blue.mp4"
    close_source = tmp_path / "close-green.mp4"
    build_fixture_clip(
        output_path=hook_source,
        width=640,
        height=640,
        include_audio=False,
        duration_seconds=0.9,
        video_source="color=c=red:size=640x640:rate=24",
    )
    build_fixture_clip(
        output_path=value_source,
        width=640,
        height=640,
        include_audio=False,
        duration_seconds=0.9,
        video_source="color=c=blue:size=640x640:rate=24",
    )
    build_fixture_clip(
        output_path=close_source,
        width=640,
        height=640,
        include_audio=False,
        duration_seconds=0.9,
        video_source="color=c=green:size=640x640:rate=24",
    )
    # Deliberately supply segments out of hook-first order so the template
    # reorder is observable in the applied plan.
    edit_plan = SceneAwareEditPlan(
        segments=[
            SceneEditPlanSegment(
                segment_id="segment-001",
                scene_id="scene-value",
                purpose="value",
                source_uri=str(value_source),
                duration_seconds=0.7,
                timeline_start_seconds=0.0,
            ),
            SceneEditPlanSegment(
                segment_id="segment-002",
                scene_id="scene-hook",
                purpose="hook",
                source_uri=str(hook_source),
                duration_seconds=0.9,
                timeline_start_seconds=0.7,
            ),
            SceneEditPlanSegment(
                segment_id="segment-003",
                scene_id="scene-close",
                purpose="close",
                source_uri=str(close_source),
                duration_seconds=0.7,
                timeline_start_seconds=1.6,
            ),
        ]
    )

    artifact = render_basic_vertical_edit(
        source_uri=hook_source,
        workdir=tmp_path / "job-template",
        edit_plan=edit_plan,
        editorial_template=HOOK_FIRST_V1,
    )

    assert artifact.editorial_template_id == HOOK_FIRST_V1.template_id
    assert artifact.editorial_template_version == HOOK_FIRST_V1.template_version
    applied = artifact.applied_edit_plan
    assert applied is not None
    assert [segment.scene_id for segment in applied.segments] == [
        "scene-hook",
        "scene-value",
        "scene-close",
    ]
    # Hook is clamped into [hook_min, hook_max]; 0.9s fits inside [0.6, 1.4].
    assert applied.segments[0].duration_seconds == pytest.approx(0.9)
    # Close is clamped into [end_card_min, end_card_max]; 0.7s fits inside [0.5, 1.2].
    assert applied.segments[-1].duration_seconds == pytest.approx(0.7)
    # Contiguous timeline retimed from zero.
    assert applied.segments[0].timeline_start_seconds == pytest.approx(0.0)
    assert applied.segments[1].timeline_start_seconds == pytest.approx(0.9)
    assert applied.segments[2].timeline_start_seconds == pytest.approx(1.6)
    # Template identity is visible in plan metadata for packaging/trace.
    assert applied.metadata[EDITORIAL_TEMPLATE_METADATA_KEY] == (HOOK_FIRST_V1.template_id)
    assert applied.metadata[EDITORIAL_TEMPLATE_VERSION_METADATA_KEY] == (
        HOOK_FIRST_V1.template_version
    )

    output_probe = probe_media(artifact.final_video_path)
    assert output_probe["width"] == 1080
    assert output_probe["height"] == 1920
    # Hook should render first; sample the first 200ms and confirm it is red,
    # not blue (the original first segment in the unapplied plan).
    hook_frame = extract_png_bytes(artifact.final_video_path, timestamp_seconds=0.2)
    late_frame = extract_png_bytes(artifact.final_video_path, timestamp_seconds=1.2)
    assert hook_frame != late_frame
