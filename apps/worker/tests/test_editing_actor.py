from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from content_lab_assets.combinator import (
    CandidateComposition,
    PackAsset,
    generate_candidate_compositions,
)
from content_lab_assets.types import AssetKind
from content_lab_editing import CompositionManifest
from content_lab_editing.cover import CoverFrameArtifact
from content_lab_editing.ffmpeg import FFmpegRunResult
from content_lab_editing.layered_ffmpeg import LayeredCompositionResult
from content_lab_storage import StorageRef, StoredObject
from content_lab_worker.actors.editing import (
    AssetUsageSpec,
    LayeredCompositionRequest,
    RenderAssetRecord,
    RetryableCompositionActorError,
    TerminalCompositionActorError,
    process_layered_composition,
)


class FakeLayeredCompositionStore:
    def __init__(
        self,
        request: LayeredCompositionRequest,
        *,
        asset_sources: Mapping[str, Mapping[str, object]],
    ) -> None:
        self.state = request
        self.asset_sources = {key: dict(value) for key, value in asset_sources.items()}
        self.package_payload: dict[str, Any] | None = None
        self.render_asset: RenderAssetRecord | None = None
        self.asset_usages: list[AssetUsageSpec] = []

    def load_request(
        self,
        *,
        run_id: uuid.UUID | str,
        task_id: uuid.UUID | str | None = None,
    ) -> LayeredCompositionRequest:
        assert str(self.state.run_id) == str(run_id)
        if task_id is not None:
            assert str(self.state.task_id) == str(task_id)
        return self.state

    def load_asset_sources(
        self,
        request: LayeredCompositionRequest,
        *,
        asset_ids: Sequence[str],
    ) -> dict[str, Mapping[str, object]]:
        assert request.run_id == self.state.run_id
        return {
            asset_id: self.asset_sources[asset_id]
            for asset_id in asset_ids
            if asset_id in self.asset_sources
        }

    def mark_running(
        self,
        request: LayeredCompositionRequest,
        *,
        task_result: Mapping[str, Any],
    ) -> LayeredCompositionRequest:
        self.state = replace(
            request,
            run_status="running",
            task_status="running",
            reel_status="editing",
            task_result=dict(task_result),
        )
        return self.state

    def mark_retryable(
        self,
        request: LayeredCompositionRequest,
        *,
        reason: str,
        task_result: Mapping[str, Any],
    ) -> LayeredCompositionRequest:
        self.state = replace(
            request,
            run_status="running",
            task_status="retrying",
            reel_status="editing",
            run_output_payload={"reason": reason, "retryable": True, **dict(task_result)},
            task_result={"reason": reason, "retryable": True, **dict(task_result)},
        )
        return self.state

    def mark_failed(
        self,
        request: LayeredCompositionRequest,
        *,
        reason: str,
        task_result: Mapping[str, Any],
    ) -> LayeredCompositionRequest:
        self.state = replace(
            request,
            run_status="failed",
            task_status="failed",
            reel_status="qa_failed",
            run_output_payload={"reason": reason, "retryable": False, **dict(task_result)},
            task_result={"reason": reason, "retryable": False, **dict(task_result)},
        )
        return self.state

    def mark_ready(
        self,
        request: LayeredCompositionRequest,
        *,
        package_payload: Mapping[str, Any],
        render_asset: RenderAssetRecord,
        asset_usages: Sequence[AssetUsageSpec],
        task_result: Mapping[str, Any],
    ) -> LayeredCompositionRequest:
        self.package_payload = dict(package_payload)
        self.render_asset = render_asset
        self.asset_usages = list(asset_usages)
        ready_payload = {
            **dict(task_result),
            "package": dict(package_payload),
            "render_asset": render_asset.as_payload(),
        }
        self.state = replace(
            request,
            run_status="succeeded",
            task_status="succeeded",
            reel_status="ready",
            run_output_payload=ready_payload,
            task_result=ready_payload,
        )
        return self.state


class FakeStorageClient:
    def __init__(self) -> None:
        self.objects: list[StoredObject] = []
        self.data_by_uri: dict[str, bytes] = {}

    def head_object(self, *, storage_uri: str) -> StoredObject:
        if storage_uri not in self.data_by_uri:
            raise FileNotFoundError(storage_uri)
        ref = StorageRef.from_uri(storage_uri)
        data = self.data_by_uri[storage_uri]
        return StoredObject(ref=ref, size_bytes=len(data))

    def get_object(self, *, storage_uri: str) -> object:
        body = self.data_by_uri[storage_uri]

        class Retrieved:
            def __init__(self, payload: bytes) -> None:
                self.body = payload

        return Retrieved(body)

    def put_object(
        self,
        *,
        data: bytes,
        ref: StorageRef | None = None,
        storage_uri: str | None = None,
        key: str | None = None,
        bucket: str | None = None,
        content_type: str | None = None,
        metadata: Mapping[str, str] | None = None,
        checksum_sha256: str | None = None,
    ) -> StoredObject:
        if ref is None:
            if storage_uri is not None:
                ref = StorageRef.from_uri(storage_uri)
            else:
                assert key is not None
                ref = StorageRef(bucket=bucket or "content-lab", key=key)
        stored = StoredObject(
            ref=ref,
            size_bytes=len(data),
            content_type=content_type,
            metadata=dict(metadata or {}),
            checksum_sha256=checksum_sha256,
        )
        self.objects.append(stored)
        self.data_by_uri[stored.ref.uri] = data
        return stored


class FakeRenderer:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    def __call__(
        self,
        manifest: CompositionManifest,
        *,
        asset_sources: Mapping[str, object],
        output_path: str | Path,
        storage_client: object | None = None,
        staging_dir: str | Path | None = None,
        timeout_seconds: float | None = None,
    ) -> LayeredCompositionResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"rendered-video")
        command = ("ffmpeg", "-i", "source.mp4", str(output))
        return LayeredCompositionResult(
            output_path=output,
            command=command,
            filter_complex="[0:v]null[finalv]",
            staged_assets={},
            ffmpeg_result=FFmpegRunResult(
                command=command,
                returncode=0,
                stdout="",
                stderr="",
                duration_seconds=0.01,
            ),
        )


def fake_cover_extractor(
    *,
    video_path: str | Path,
    output_path: str | Path,
    timestamp_seconds: float | None = None,
    duration_seconds: float | None = None,
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
) -> CoverFrameArtifact:
    _ = (video_path, timestamp_seconds, ffmpeg_bin, ffprobe_bin)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"cover-png")
    return CoverFrameArtifact(image_path=output, timestamp_seconds=0.5)


def test_process_layered_composition_renders_and_marks_ready() -> None:
    request, manifest, source_asset_id = _request_with_manifest()
    store = FakeLayeredCompositionStore(
        request,
        asset_sources={
            source_asset_id: {
                "source": "https://cdn.example.com/source.mp4",
                "status": "ready",
                "content_hash": "sha256:" + ("a" * 64),
                "media_type": "video/mp4",
            }
        },
    )
    storage = FakeStorageClient()

    result = process_layered_composition(
        run_id=request.run_id,
        task_id=request.task_id,
        store=store,
        storage_client=storage,
        renderer=FakeRenderer(),
        cover_extractor=fake_cover_extractor,
    )

    assert result["status"] == "ready"
    assert result["package"]["package_root_uri"] == (
        f"s3://content-lab/reels/packages/{request.reel_id}"
    )
    assert store.state.run_status == "succeeded"
    assert store.state.task_status == "succeeded"
    assert store.state.reel_status == "ready"
    assert store.render_asset is not None
    assert store.render_asset.storage_uri == (
        f"s3://content-lab/reels/packages/{request.reel_id}/final_video.mp4"
    )
    assert {item.ref.key for item in storage.objects} == {
        f"reels/packages/{request.reel_id}/final_video.mp4",
        f"reels/packages/{request.reel_id}/cover.png",
        f"reels/packages/{request.reel_id}/composition_manifest.json",
        f"reels/packages/{request.reel_id}/package_manifest.json",
    }
    assert {usage.usage_role for usage in store.asset_usages} == {"background", "final_render"}
    assert store.package_payload is not None
    assert store.package_payload["composition_manifest"]["duration"] == manifest["duration"]


def test_process_layered_composition_marks_render_failure_retryable() -> None:
    request, _, source_asset_id = _request_with_manifest()
    store = FakeLayeredCompositionStore(
        request,
        asset_sources={
            source_asset_id: {
                "source": "https://cdn.example.com/source.mp4",
                "status": "ready",
                "media_type": "video",
            }
        },
    )

    with pytest.raises(RetryableCompositionActorError, match="ffmpeg failed"):
        process_layered_composition(
            run_id=request.run_id,
            task_id=request.task_id,
            store=store,
            storage_client=FakeStorageClient(),
            renderer=FakeRenderer(error=RuntimeError("ffmpeg failed")),
            cover_extractor=fake_cover_extractor,
        )

    assert store.state.run_status == "running"
    assert store.state.task_status == "retrying"
    assert store.state.reel_status == "editing"
    assert store.state.task_result is not None
    assert store.state.task_result["retryable"] is True
    assert store.state.task_result["phase"] == "render"


def test_process_layered_composition_marks_missing_source_terminal() -> None:
    request, _, _ = _request_with_manifest()
    store = FakeLayeredCompositionStore(request, asset_sources={})
    renderer = FakeRenderer()

    with pytest.raises(TerminalCompositionActorError, match="composition preflight failed"):
        process_layered_composition(
            run_id=request.run_id,
            task_id=request.task_id,
            store=store,
            storage_client=FakeStorageClient(),
            renderer=renderer,
            cover_extractor=fake_cover_extractor,
        )

    assert renderer.calls == 0
    assert store.state.run_status == "failed"
    assert store.state.task_status == "failed"
    assert store.state.reel_status == "qa_failed"
    assert store.state.task_result is not None
    assert store.state.task_result["retryable"] is False
    assert store.state.task_result["phase"] == "preflight"
    assert store.state.task_result["details"]["issues"][0]["code"] == "asset_source_missing"


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe is not installed")
def test_layered_composition_smoke_renders_vertical_package_with_cover_and_provenance(
    tmp_path: Path,
) -> None:
    background_id = str(uuid.uuid4())
    object_id = str(uuid.uuid4())
    hook_id = str(uuid.uuid4())
    audio_id = str(uuid.uuid4())
    source_ids = {background_id, object_id, hook_id, audio_id}
    background = tmp_path / "background.png"
    cutout = tmp_path / "object.png"
    hook = tmp_path / "hook.txt"
    audio = tmp_path / "audio.wav"

    _run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x172033:s=1080x1920:d=1",
            "-frames:v",
            "1",
            str(background),
        ]
    )
    _run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0xf4d35e@0.78:s=360x360:d=1",
            "-frames:v",
            "1",
            "-pix_fmt",
            "rgba",
            str(cutout),
        ]
    )
    _run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            "1",
            str(audio),
        ]
    )
    hook.write_text("Luxury starts before anyone can see it.", encoding="utf-8")

    manifest = {
        "canvas_width": 1080,
        "canvas_height": 1920,
        "duration": 1.0,
        "fps": 24,
        "background_layer": {
            "layer_id": "background",
            "asset_id": background_id,
            "asset_kind": "background_image",
            "media_type": "image",
            "z_index": 0,
            "start_time": 0.0,
            "end_time": 1.0,
        },
        "layers": [
            {
                "layer_id": "object",
                "asset_id": object_id,
                "asset_kind": "transparent_cutout_png",
                "media_type": "image",
                "z_index": 1,
                "start_time": 0.0,
                "end_time": 1.0,
                "x": 360,
                "y": 780,
                "width": 360,
                "height": 360,
                "mask_mode": "alpha",
            },
            {
                "layer_id": "hook",
                "asset_id": hook_id,
                "asset_kind": "hook_text",
                "media_type": "text",
                "z_index": 2,
                "start_time": 0.0,
                "end_time": 1.0,
                "x": 90,
                "y": 180,
                "height": 68,
            },
        ],
        "audio_layers": [
            {
                "layer_id": "audio",
                "asset_id": audio_id,
                "asset_kind": "audio_track",
                "media_type": "audio",
                "z_index": 0,
                "start_time": 0.0,
                "end_time": 1.0,
            }
        ],
    }
    request = _request_for_manifest(manifest)
    store = FakeLayeredCompositionStore(
        request,
        asset_sources={
            background_id: {"source": str(background), "status": "ready", "media_type": "image"},
            object_id: {"source": str(cutout), "status": "ready", "media_type": "image/png"},
            hook_id: {"source": str(hook), "status": "ready", "media_type": "text/plain"},
            audio_id: {"source": str(audio), "status": "ready", "media_type": "audio/wav"},
        },
    )
    storage = FakeStorageClient()

    result = process_layered_composition(
        run_id=request.run_id,
        task_id=request.task_id,
        store=store,
        storage_client=storage,
        timeout_seconds=30.0,
    )

    final_video_uri = f"s3://content-lab/reels/packages/{request.reel_id}/final_video.mp4"
    cover_uri = f"s3://content-lab/reels/packages/{request.reel_id}/cover.png"
    final_video = tmp_path / "final_video.mp4"
    final_video.write_bytes(storage.data_by_uri[final_video_uri])
    metadata = _probe_media(final_video)

    assert result["status"] == "ready"
    assert metadata["width"] == 1080
    assert metadata["height"] == 1920
    assert metadata["has_audio_track"] is True
    assert storage.data_by_uri[cover_uri].startswith(b"\x89PNG")
    assert store.package_payload is not None
    provenance = store.package_payload["provenance"]
    assert set(provenance["asset_ids"]) == source_ids
    assert {asset["asset_id"] for asset in provenance["assets"]} == source_ids


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe is not installed")
def test_asset_pack_to_multiple_reels_smoke_renders_distinct_candidates_with_lineage(
    tmp_path: Path,
) -> None:
    asset_ids = {
        "background_a": str(uuid.uuid4()),
        "background_b": str(uuid.uuid4()),
        "object_a": str(uuid.uuid4()),
        "object_b": str(uuid.uuid4()),
        "hook_a": str(uuid.uuid4()),
        "hook_b": str(uuid.uuid4()),
        "audio_a": str(uuid.uuid4()),
        "audio_b": str(uuid.uuid4()),
    }
    source_paths = _write_candidate_source_assets(tmp_path, asset_ids)
    pack_assets = [
        _pack_asset(asset_ids["background_a"], "background_image", "background", 0.91),
        _pack_asset(asset_ids["background_b"], "background_image", "background", 0.84),
        _pack_asset(asset_ids["object_a"], "transparent_cutout_png", "foreground", 0.88),
        _pack_asset(asset_ids["object_b"], "transparent_cutout_png", "foreground", 0.82),
        _pack_asset(asset_ids["hook_a"], "hook_text", "hook", 0.93),
        _pack_asset(asset_ids["hook_b"], "hook_text", "hook", 0.86),
        _pack_asset(asset_ids["audio_a"], "audio_track", "audio", 0.9),
        _pack_asset(asset_ids["audio_b"], "audio_track", "audio", 0.83),
    ]

    candidates = generate_candidate_compositions(
        pack_assets,
        target_reel_count=5,
        format_filters=["hook_led_tip"],
        style_filters=["cinematic"],
    )

    assert len(candidates) == 5
    assert len({candidate.composition_id for candidate in candidates}) == 5
    assert all(
        set(candidate.roles) == {"audio", "background", "foreground", "hook"}
        for candidate in candidates
    )
    role_asset_ids = [asset.asset_id for candidate in candidates for asset in candidate.roles.values()]
    assert len(set(role_asset_ids)) < len(role_asset_ids)

    first_candidate, second_candidate = _overlapping_distinct_candidate_pair(candidates)
    first_render = _render_candidate(first_candidate, source_paths=source_paths)
    second_render = _render_candidate(second_candidate, source_paths=source_paths)

    assert first_render["final_video_bytes"] != second_render["final_video_bytes"]
    for render in (first_render, second_render):
        store = render["store"]
        assert isinstance(store, FakeLayeredCompositionStore)
        assert store.package_payload is not None
        provenance = store.package_payload["provenance"]
        source_ids = {asset.asset_id for asset in render["candidate"].roles.values()}
        component_roles = {usage.component_role for usage in store.asset_usages}
        usage_roles = {usage.usage_role for usage in store.asset_usages}

        assert set(provenance["asset_ids"]) == source_ids
        assert {"background_image", "transparent_cutout_png", "hook_text", "audio_track"}.issubset(
            component_roles
        )
        assert "final_render" in usage_roles
        assert "generated_clip" not in component_roles
        assert any(usage.layer_role == "visual" for usage in store.asset_usages)


def _request_with_manifest() -> tuple[LayeredCompositionRequest, dict[str, Any], str]:
    source_asset_id = str(uuid.uuid4())
    manifest = {
        "duration": 3.0,
        "fps": 24,
        "background_layer": {
            "layer_id": "background",
            "asset_id": source_asset_id,
            "asset_kind": "clip",
            "media_type": "video",
            "z_index": 0,
            "start_time": 0.0,
            "end_time": 3.0,
        },
        "layers": [],
        "audio_layers": [],
    }
    request = LayeredCompositionRequest(
        run_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        reel_id=uuid.uuid4(),
        workflow_key="process_reel",
        run_status="queued",
        run_input_params={
            "reel_id": "",
            "layered_composition_manifest": manifest,
        },
        run_metadata={},
        task_id=uuid.uuid4(),
        task_type="layered_composition.render",
        task_status="queued",
        task_payload={},
        reel_status="planning",
        reel_metadata={},
    )
    request = replace(
        request,
        run_input_params={
            "reel_id": str(request.reel_id),
            "layered_composition_manifest": manifest,
        },
    )
    return request, manifest, source_asset_id


def _request_for_manifest(manifest: Mapping[str, Any]) -> LayeredCompositionRequest:
    request = LayeredCompositionRequest(
        run_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        reel_id=uuid.uuid4(),
        workflow_key="process_reel",
        run_status="queued",
        run_input_params={},
        run_metadata={},
        task_id=uuid.uuid4(),
        task_type="layered_composition.render",
        task_status="queued",
        task_payload={},
        reel_status="planning",
        reel_metadata={},
    )
    return replace(
        request,
        run_input_params={
            "reel_id": str(request.reel_id),
            "layered_composition_manifest": dict(manifest),
        },
    )


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no output captured"
        raise RuntimeError(detail)
    return completed


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


def _pack_asset(
    asset_id: str,
    asset_kind: str,
    pack_role: str,
    performance_score: float,
) -> PackAsset:
    return PackAsset(
        asset_id=asset_id,
        asset_kind=AssetKind(asset_kind),
        pack_role=pack_role,
        title=f"{pack_role} {asset_kind}",
        compatibility={
            "niche": ["luxury_mindset"],
            "visual_style": ["cinematic"],
            "format_type": ["hook_led_tip"],
            "emotion": ["aspirational"],
        },
        metadata={"label": f"{pack_role} {asset_kind}"},
        performance_score=performance_score,
    )


def _write_candidate_source_assets(tmp_path: Path, asset_ids: Mapping[str, str]) -> dict[str, Path]:
    paths = {
        asset_ids["background_a"]: tmp_path / "background_a.png",
        asset_ids["background_b"]: tmp_path / "background_b.png",
        asset_ids["object_a"]: tmp_path / "object_a.png",
        asset_ids["object_b"]: tmp_path / "object_b.png",
        asset_ids["hook_a"]: tmp_path / "hook_a.txt",
        asset_ids["hook_b"]: tmp_path / "hook_b.txt",
        asset_ids["audio_a"]: tmp_path / "audio_a.wav",
        asset_ids["audio_b"]: tmp_path / "audio_b.wav",
    }
    _run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x172033:s=1080x1920:d=1",
            "-frames:v",
            "1",
            str(paths[asset_ids["background_a"]]),
        ]
    )
    _run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x3a1f5d:s=1080x1920:d=1",
            "-frames:v",
            "1",
            str(paths[asset_ids["background_b"]]),
        ]
    )
    _run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0xf4d35e@0.78:s=360x360:d=1",
            "-frames:v",
            "1",
            "-pix_fmt",
            "rgba",
            str(paths[asset_ids["object_a"]]),
        ]
    )
    _run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x70c1b3@0.78:s=360x360:d=1",
            "-frames:v",
            "1",
            "-pix_fmt",
            "rgba",
            str(paths[asset_ids["object_b"]]),
        ]
    )
    _run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            "1",
            str(paths[asset_ids["audio_a"]]),
        ]
    )
    _run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=660:sample_rate=48000",
            "-t",
            "1",
            str(paths[asset_ids["audio_b"]]),
        ]
    )
    paths[asset_ids["hook_a"]].write_text(
        "Luxury starts before anyone can see it.",
        encoding="utf-8",
    )
    paths[asset_ids["hook_b"]].write_text(
        "Act like the result is already normal.",
        encoding="utf-8",
    )
    return paths


def _overlapping_distinct_candidate_pair(
    candidates: Sequence[CandidateComposition],
) -> tuple[CandidateComposition, CandidateComposition]:
    for left_index, left in enumerate(candidates):
        left_ids = {asset.asset_id for asset in left.roles.values()}
        for right in candidates[left_index + 1 :]:
            right_ids = {asset.asset_id for asset in right.roles.values()}
            if left_ids != right_ids and left_ids.intersection(right_ids):
                return left, right
    raise AssertionError("Expected at least two candidates with overlapping reusable assets")


def _render_candidate(
    candidate: CandidateComposition,
    *,
    source_paths: Mapping[str, Path],
) -> dict[str, Any]:
    manifest = _manifest_from_candidate(candidate)
    request = _request_for_manifest(manifest)
    store = FakeLayeredCompositionStore(
        request,
        asset_sources={
            asset.asset_id: {
                "source": str(source_paths[asset.asset_id]),
                "status": "ready",
                "media_type": _source_media_type(asset.asset_kind.value),
            }
            for asset in candidate.roles.values()
        },
    )
    storage = FakeStorageClient()
    result = process_layered_composition(
        run_id=request.run_id,
        task_id=request.task_id,
        store=store,
        storage_client=storage,
        timeout_seconds=30.0,
    )
    assert result["status"] == "ready"
    final_video_uri = f"s3://content-lab/reels/packages/{request.reel_id}/final_video.mp4"
    return {
        "candidate": candidate,
        "store": store,
        "final_video_bytes": storage.data_by_uri[final_video_uri],
    }


def _manifest_from_candidate(candidate: CandidateComposition) -> dict[str, object]:
    background = candidate.roles["background"]
    foreground = candidate.roles["foreground"]
    hook = candidate.roles["hook"]
    audio = candidate.roles["audio"]
    return {
        "canvas_width": 1080,
        "canvas_height": 1920,
        "duration": 1.0,
        "fps": 24,
        "background_layer": {
            "layer_id": "background",
            "asset_id": background.asset_id,
            "asset_kind": background.asset_kind.value,
            "media_type": "image",
            "z_index": 0,
            "start_time": 0.0,
            "end_time": 1.0,
        },
        "layers": [
            {
                "layer_id": "foreground",
                "asset_id": foreground.asset_id,
                "asset_kind": foreground.asset_kind.value,
                "media_type": "image",
                "z_index": 1,
                "start_time": 0.0,
                "end_time": 1.0,
                "x": 360,
                "y": 780,
                "width": 360,
                "height": 360,
                "mask_mode": "alpha",
            },
            {
                "layer_id": "hook",
                "asset_id": hook.asset_id,
                "asset_kind": hook.asset_kind.value,
                "media_type": "text",
                "z_index": 2,
                "start_time": 0.0,
                "end_time": 1.0,
                "x": 90,
                "y": 180,
                "height": 68,
            },
        ],
        "audio_layers": [
            {
                "layer_id": "audio",
                "asset_id": audio.asset_id,
                "asset_kind": audio.asset_kind.value,
                "media_type": "audio",
                "z_index": 0,
                "start_time": 0.0,
                "end_time": 1.0,
            }
        ],
    }


def _source_media_type(asset_kind: str) -> str:
    if asset_kind == "audio_track":
        return "audio/wav"
    if asset_kind == "hook_text":
        return "text/plain"
    return "image/png"
