from __future__ import annotations

import base64
import json
import os
import uuid
from pathlib import Path
from unittest.mock import Mock
from urllib.error import URLError
from urllib.request import urlopen

import pytest

from content_lab_editing.package_builder import build_package_directory, build_ready_to_post_package
from content_lab_storage import (
    CanonicalStorageLayout,
    S3StorageClient,
    S3StorageConfig,
    StorageRef,
    StoredObject,
)
from content_lab_storage.reel_packages import assert_reel_package_complete

_ONE_BY_ONE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO9nWZkAAAAASUVORK5CYII="
)

_TIMELINE = {
    "version": "med-001.v1",
    "timeline_id": "timeline-test",
    "duration_seconds": 12.0,
    "cover_frame_timestamp_seconds": 0.0,
    "source_clips": [{"clip_id": "source-001", "duration_seconds": 12.0}],
    "scenes": [{"scene_id": "scene-001", "start_seconds": 0.0, "end_seconds": 12.0}],
    "edit_segments": [
        {
            "segment_id": "segment-001",
            "timeline_start_seconds": 0.0,
            "timeline_end_seconds": 12.0,
            "source_clip_id": "source-001",
            "source_start_seconds": 0.0,
            "source_end_seconds": 12.0,
        }
    ],
    "overlays": [],
    "audio_tracks": [
        {"track_id": "audio-master", "role": "master", "start_seconds": 0.0, "end_seconds": 12.0}
    ],
}
_TIMELINE_RENDER_TRACE = {
    "schema_version": "timeline_render_trace.v1",
    "scene_timings": [{"scene_id": "scene-001", "start_seconds": 0.0, "end_seconds": 12.0}],
    "overlay_timings": [],
    "audio_timings": [{"track_id": "audio-master", "start_seconds": 0.0, "end_seconds": 12.0}],
    "fade_durations": [
        {"track_id": "audio-master", "fade_in_seconds": 0.12, "fade_out_seconds": 0.18}
    ],
    "final_render_duration_seconds": 12.0,
    "source_asset_duration_seconds": 12.0,
    "duration_mismatch_checks": {"status": "pass", "mismatches": []},
    "cover_timestamp_seconds": 0.0,
}
_OVERLAY_RENDER_TRACE = {
    "artifact_type": "overlay_render_trace",
    "schema_version": "rendered_overlay_manifest_v1",
    "frame_width_px": 1080,
    "frame_height_px": 1920,
    "clip_duration_seconds": 12.0,
    "overlay_count": 0,
    "overlays": [],
}


def test_build_package_directory_writes_required_artifacts_and_manifest(tmp_path: Path) -> None:
    final_video = tmp_path / "input-video.mp4"
    cover = tmp_path / "input-cover.png"
    final_video.write_bytes(b"video-bytes")
    cover.write_bytes(_ONE_BY_ONE_PNG)

    built = build_package_directory(
        reel_id="reel-local-123",
        final_video_path=final_video,
        cover_path=cover,
        caption_variants=[
            {"variant": "short", "text": "Short caption"},
            {"variant": "standard", "text": "Standard caption"},
        ],
        posting_plan={"platform": "instagram", "scheduled_for": "2026-03-26T10:00:00Z"},
        provenance={"source_run_id": "run-123", "asset_ids": ["asset-1", "asset-2"]},
        timeline=_TIMELINE,
        timeline_render_trace=_TIMELINE_RENDER_TRACE,
        overlay_render_trace=_OVERLAY_RENDER_TRACE,
        temp_root=tmp_path / "scratch",
    )

    artifact_names = {path.name for path in built.directory.iterdir()}
    assert artifact_names == {
        "caption_variants.txt",
        "cover.png",
        "final_video.mp4",
        "package_manifest.json",
        "posting_plan.json",
        "provenance.json",
        "timeline.json",
        "timeline_render_trace.json",
        "overlay_render_trace.json",
    }
    manifest = json.loads((built.directory / "package_manifest.json").read_text(encoding="utf-8"))
    assert manifest["complete"] is True
    assert manifest["artifact_count"] == 8
    assert {artifact["name"] for artifact in manifest["artifacts"]} == {
        "caption_variants",
        "cover",
        "final_video",
        "posting_plan",
        "provenance",
        "timeline",
        "timeline_render_trace",
        "overlay_render_trace",
    }


def test_build_package_directory_merges_editing_metadata_into_manifest(tmp_path: Path) -> None:
    final_video = tmp_path / "input-video.mp4"
    cover = tmp_path / "input-cover.png"
    final_video.write_bytes(b"video-bytes")
    cover.write_bytes(_ONE_BY_ONE_PNG)

    safe_report = {
        "schema_version": 1,
        "status": "pass",
        "frame": {"width": 1080, "height": 1920},
        "safe_insets_px": {"left": 64, "right": 64, "top": 100, "bottom": 100},
        "overlays": [],
    }
    local_pkg = build_package_directory(
        reel_id="reel-local-456",
        final_video_path=final_video,
        cover_path=cover,
        caption_variants="Caption",
        posting_plan={},
        provenance={},
        timeline=_TIMELINE,
        timeline_render_trace=_TIMELINE_RENDER_TRACE,
        overlay_render_trace=_OVERLAY_RENDER_TRACE,
        temp_root=tmp_path / "scratch-ed",
        editing_metadata={"safe_area_9_16": safe_report},
    )

    manifest = json.loads(
        (local_pkg.directory / "package_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["editing"]["safe_area_9_16"]["status"] == "pass"
    assert manifest["editing"]["safe_area_9_16"]["frame"]["width"] == 1080
    client = Mock()
    layout = CanonicalStorageLayout(bucket="content-lab")
    final_video = tmp_path / "input-video.mp4"
    cover = tmp_path / "input-cover.png"
    final_video.write_bytes(b"video-bytes")
    cover.write_bytes(_ONE_BY_ONE_PNG)

    def _stored(
        ref: StorageRef, *, content_type: str | None, metadata: dict[str, str]
    ) -> StoredObject:
        return StoredObject(
            ref=ref,
            size_bytes=123,
            content_type=content_type,
            metadata=metadata,
            checksum_sha256="sha256:" + ("a" * 64),
        )

    client.put_object.side_effect = lambda **kwargs: _stored(
        kwargs["ref"],
        content_type=kwargs.get("content_type"),
        metadata=dict(kwargs.get("metadata", {})),
    )

    built = build_ready_to_post_package(
        client=client,
        layout=layout,
        reel_id="reel-local-123",
        final_video_path=final_video,
        cover_path=cover,
        caption_variants=[{"variant": "short", "text": "Short caption"}],
        posting_plan={"platform": "instagram"},
        provenance={"source_run_id": "run-123"},
        timeline=_TIMELINE,
        timeline_render_trace=_TIMELINE_RENDER_TRACE,
        overlay_render_trace=_OVERLAY_RENDER_TRACE,
        creative_trace={
            "schema_version": "phase_1",
            "artifact_type": "creative_trace",
            "brief": {"title": "Desk reset"},
        },
        temp_root=tmp_path / "scratch",
    )

    trace_path = built.local_package.directory / "creative_trace.json"
    assert trace_path.exists()
    assert built.local_package.manifest is not None
    assert built.local_package.manifest["artifact_count"] == 9
    assert {artifact["name"] for artifact in built.local_package.manifest["artifacts"]} == {
        "caption_variants",
        "cover",
        "creative_trace",
        "final_video",
        "overlay_render_trace",
        "posting_plan",
        "provenance",
        "timeline",
        "timeline_render_trace",
    }
    assert built.package_payload["creative_trace_uri"] == (
        "s3://content-lab/reels/packages/reel-local-123/creative_trace.json"
    )
    assert built.package_payload["creative_trace"]["brief"]["title"] == "Desk reset"
    assert built.package_payload["caption_variants"] == [
        {"variant": "short", "text": "Short caption"}
    ]
    assert built.stored_package.artifact_by_name("creative_trace") is not None
    assert client.put_object.call_count == 10


def test_build_ready_to_post_package_attaches_overlay_render_trace(tmp_path: Path) -> None:
    client = Mock()
    layout = CanonicalStorageLayout(bucket="content-lab")
    final_video = tmp_path / "input-video.mp4"
    cover = tmp_path / "input-cover.png"
    final_video.write_bytes(b"video-bytes")
    cover.write_bytes(_ONE_BY_ONE_PNG)

    def _stored(
        ref: StorageRef, *, content_type: str | None, metadata: dict[str, str]
    ) -> StoredObject:
        return StoredObject(
            ref=ref,
            size_bytes=123,
            content_type=content_type,
            metadata=metadata,
            checksum_sha256="sha256:" + ("a" * 64),
        )

    client.put_object.side_effect = lambda **kwargs: _stored(
        kwargs["ref"],
        content_type=kwargs.get("content_type"),
        metadata=dict(kwargs.get("metadata", {})),
    )

    built = build_ready_to_post_package(
        client=client,
        layout=layout,
        reel_id="reel-local-456",
        final_video_path=final_video,
        cover_path=cover,
        caption_variants=[{"variant": "short", "text": "Short caption"}],
        posting_plan={"platform": "instagram"},
        provenance={"source_run_id": "run-456"},
        timeline=_TIMELINE,
        timeline_render_trace=_TIMELINE_RENDER_TRACE,
        creative_trace={
            "schema_version": "phase_1",
            "artifact_type": "creative_trace",
            "brief": {"title": "Desk reset"},
        },
        overlay_render_trace={
            "artifact_type": "overlay_render_trace",
            "schema_version": 1,
            "overlay_count": 0,
            "combined_video_filter": "scale=1080:1920",
        },
        temp_root=tmp_path / "scratch-overlay",
    )

    overlay_path = built.local_package.directory / "overlay_render_trace.json"
    assert overlay_path.exists()
    assert built.local_package.manifest is not None
    assert built.local_package.manifest["artifact_count"] == 9
    artifact_names = {a["name"] for a in built.local_package.manifest["artifacts"]}
    assert artifact_names == {
        "caption_variants",
        "cover",
        "creative_trace",
        "final_video",
        "overlay_render_trace",
        "posting_plan",
        "provenance",
        "timeline",
        "timeline_render_trace",
    }
    assert built.package_payload["overlay_render_trace_uri"] == (
        "s3://content-lab/reels/packages/reel-local-456/overlay_render_trace.json"
    )
    assert built.package_payload["overlay_render_trace"]["overlay_count"] == 0
    assert built.stored_package.artifact_by_name("overlay_render_trace") is not None
    assert client.put_object.call_count == 10


def _integration_client() -> tuple[S3StorageClient, str]:
    bucket = os.getenv("MINIO_BUCKET", "content-lab")
    client = S3StorageClient(
        S3StorageConfig(
            endpoint=os.getenv("MINIO_ENDPOINT", "http://localhost:9000"),
            access_key_id=os.getenv("MINIO_ROOT_USER", "minioadmin"),
            secret_access_key=os.getenv("MINIO_ROOT_PASSWORD", "minioadmin"),
            default_bucket=bucket,
        )
    )
    return client, bucket


def _require_minio() -> None:
    endpoint = os.getenv("MINIO_ENDPOINT", "http://localhost:9000").rstrip("/")
    try:
        with urlopen(f"{endpoint}/minio/health/live", timeout=2) as response:
            if response.status != 200:
                pytest.skip("MinIO endpoint is not healthy")
    except (TimeoutError, URLError, OSError):
        pytest.skip("MinIO endpoint is not available for the integration smoke test")


@pytest.mark.integration
def test_build_ready_to_post_package_uploads_complete_package_to_minio(tmp_path: Path) -> None:
    _require_minio()
    client, bucket = _integration_client()
    layout = CanonicalStorageLayout(bucket=bucket)
    reel_id = uuid.uuid4()
    final_video = tmp_path / "fixture-video.mp4"
    cover = tmp_path / "fixture-cover.png"
    final_video.write_bytes(b"phase-1-video-payload")
    cover.write_bytes(_ONE_BY_ONE_PNG)

    built = build_ready_to_post_package(
        client=client,
        layout=layout,
        reel_id=reel_id,
        final_video_path=final_video,
        cover_path=cover,
        caption_variants=[
            {"variant": "short", "text": "Short caption"},
            {"variant": "engagement", "text": "Ask a question"},
        ],
        posting_plan={"platform": "instagram", "publish_window": "morning"},
        provenance={"source_run_id": "run-abc", "asset_ids": ["asset-1"]},
        timeline=_TIMELINE,
        timeline_render_trace=_TIMELINE_RENDER_TRACE,
        overlay_render_trace=_OVERLAY_RENDER_TRACE,
        temp_root=tmp_path / "builder",
        upload_metadata={"source": "pytest"},
    )

    assert_reel_package_complete(built.stored_package.artifacts)
    assert built.package_payload["package_root_uri"] == f"s3://{bucket}/reels/packages/{reel_id}"
    assert built.package_payload["manifest_uri"] == (
        f"s3://{bucket}/reels/packages/{reel_id}/package_manifest.json"
    )
    assert built.package_payload["provenance_uri"] == (
        f"s3://{bucket}/reels/packages/{reel_id}/provenance.json"
    )

    uploaded_names = {artifact["name"] for artifact in built.package_payload["artifacts"]}
    assert uploaded_names == {
        "caption_variants",
        "cover",
        "final_video",
        "overlay_render_trace",
        "package_manifest",
        "posting_plan",
        "provenance",
        "timeline",
        "timeline_render_trace",
    }

    manifest_object = client.get_object(
        storage_uri=f"s3://{bucket}/reels/packages/{reel_id}/package_manifest.json"
    )
    manifest = json.loads(manifest_object.body.decode("utf-8"))
    assert manifest["complete"] is True
    assert manifest["artifact_count"] == 8
    assert {artifact["name"] for artifact in manifest["artifacts"]} == {
        "caption_variants",
        "cover",
        "final_video",
        "posting_plan",
        "provenance",
        "timeline",
        "timeline_render_trace",
        "overlay_render_trace",
    }
