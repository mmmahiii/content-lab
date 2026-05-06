from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from content_lab_editing.composition_manifest import (
    CompositionLayer,
    CompositionManifest,
    MotionTransform,
)
from content_lab_editing.ffmpeg import FFmpegRunner, FFmpegRunResult
from content_lab_editing.layered_ffmpeg import (
    build_layered_ffmpeg_args,
    compose_and_store_layered_reel,
    compose_layered_reel,
    stage_composition_assets,
)
from content_lab_storage import CanonicalStorageLayout, StorageRef, StoredObject
from tests._media_helpers import probe_media, run_command


def _manifest(*, duration: float = 1.0) -> CompositionManifest:
    return CompositionManifest(
        canvas_width=1080,
        canvas_height=1920,
        duration=duration,
        fps=24,
        background_layer=CompositionLayer(
            layer_id="bg",
            asset_id="asset-bg",
            asset_kind="background_image",
            media_type="image",
            z_index=0,
            start_time=0.0,
            end_time=duration,
        ),
        layers=[
            CompositionLayer(
                layer_id="fg",
                asset_id="asset-fg",
                asset_kind="transparent_cutout_png",
                media_type="image",
                z_index=1,
                start_time=0.0,
                end_time=duration,
                x=320,
                y=720,
                width=420,
                height=420,
                opacity=0.85,
                mask_mode="alpha",
            ),
            CompositionLayer(
                layer_id="hook",
                asset_id="asset-hook",
                asset_kind="hook_text",
                media_type="text",
                z_index=2,
                start_time=0.0,
                end_time=duration,
                x=90,
                y=180,
                height=72,
            ),
        ],
        audio_layers=[
            CompositionLayer(
                layer_id="audio",
                asset_id="asset-audio",
                asset_kind="audio_track",
                media_type="audio",
                z_index=0,
                start_time=0.0,
                end_time=duration,
            )
        ],
    )


def test_build_layered_ffmpeg_args_from_manifest(tmp_path: Path) -> None:
    manifest = _manifest()
    text_path = tmp_path / "hook.txt"
    text_path.write_text("Nobody sees this part", encoding="utf-8")
    staged = {
        "asset-bg": tmp_path / "bg.png",
        "asset-fg": tmp_path / "fg.png",
        "asset-hook": text_path,
        "asset-audio": tmp_path / "audio.wav",
    }

    args, filter_complex = build_layered_ffmpeg_args(
        manifest,
        staged_assets=staged,
        output_path=tmp_path / "final.mp4",
    )

    assert "-filter_complex" in args
    assert "scale=1080:1920:force_original_aspect_ratio=increase" in filter_complex
    assert "overlay=x='320':y='720'" in filter_complex
    assert "drawtext=text='Nobody sees this part'" in filter_complex
    assert "amix=inputs=1" in filter_complex
    assert args[-1] == tmp_path / "final.mp4"


def test_motion_transform_presets_emit_ffmpeg_expressions(tmp_path: Path) -> None:
    manifest = _manifest().model_copy(
        update={
            "layers": [
                CompositionLayer(
                    layer_id="fg",
                    asset_id="asset-fg",
                    asset_kind="transparent_cutout_png",
                    media_type="image",
                    z_index=1,
                    start_time=0.0,
                    end_time=1.0,
                    x=320,
                    y=720,
                    width=420,
                    height=420,
                    motion_transform=MotionTransform(preset="slow_zoom"),
                ),
                CompositionLayer(
                    layer_id="hook",
                    asset_id="asset-hook",
                    asset_kind="hook_text",
                    media_type="text",
                    z_index=2,
                    start_time=0.0,
                    end_time=1.0,
                    x=90,
                    y=180,
                    height=72,
                ),
            ]
        }
    )
    text_path = tmp_path / "hook.txt"
    text_path.write_text("Nobody sees this part", encoding="utf-8")
    _, filter_complex = build_layered_ffmpeg_args(
        manifest,
        staged_assets={
            "asset-bg": tmp_path / "bg.png",
            "asset-fg": tmp_path / "fg.png",
            "asset-hook": text_path,
            "asset-audio": tmp_path / "audio.wav",
        },
        output_path=tmp_path / "final.mp4",
    )

    assert "eval=frame" in filter_complex
    assert "trunc(420*(1+(1.06-1)*(t/1)))" in filter_complex


def test_pan_motion_transform_moves_overlay_position(tmp_path: Path) -> None:
    manifest = _manifest().model_copy(
        update={
            "layers": [
                CompositionLayer(
                    layer_id="fg",
                    asset_id="asset-fg",
                    asset_kind="transparent_cutout_png",
                    media_type="image",
                    z_index=1,
                    start_time=0.0,
                    end_time=1.0,
                    x=320,
                    y=720,
                    width=420,
                    height=420,
                    motion_transform=MotionTransform(preset="pan_left", amplitude=24),
                )
            ]
        }
    )
    _, filter_complex = build_layered_ffmpeg_args(
        manifest,
        staged_assets={
            "asset-bg": tmp_path / "bg.png",
            "asset-fg": tmp_path / "fg.png",
            "asset-audio": tmp_path / "audio.wav",
        },
        output_path=tmp_path / "final.mp4",
    )

    assert "overlay=x='344-48*((t-0)/1)':y='720'" in filter_complex


@dataclass(frozen=True, slots=True)
class _DownloadedObject:
    body: bytes


class _FakeStorageClient:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects

    def get_object(self, *, storage_uri: str) -> _DownloadedObject:
        return _DownloadedObject(body=self.objects[storage_uri])


def test_stage_composition_assets_downloads_s3_objects(tmp_path: Path) -> None:
    manifest = _manifest()
    sources = {
        "asset-bg": "s3://content-lab/bg.png",
        "asset-fg": "s3://content-lab/fg.png",
        "asset-hook": "s3://content-lab/hook.txt",
        "asset-audio": "s3://content-lab/audio.wav",
    }
    storage = _FakeStorageClient(
        {uri: f"bytes-{asset_id}".encode() for asset_id, uri in sources.items()}
    )

    staged = stage_composition_assets(
        manifest,
        asset_sources=sources,
        staging_dir=tmp_path / "staged",
        storage_client=storage,
    )

    assert staged["asset-bg"].read_bytes() == b"bytes-asset-bg"
    assert staged["asset-hook"].suffix == ".txt"
    assert set(staged) == {"asset-bg", "asset-fg", "asset-hook", "asset-audio"}


class _FakeRunner:
    def run_ffmpeg(
        self,
        args: list[str | Path],
        *,
        timeout_seconds: float | None = None,
    ) -> FFmpegRunResult:
        _ = timeout_seconds
        output_path = Path(args[-1])
        output_path.write_bytes(b"rendered-mp4")
        return FFmpegRunResult(
            command=("ffmpeg", *(str(arg) for arg in args)),
            returncode=0,
            stdout="",
            stderr="",
            duration_seconds=0.01,
        )


class _FakeAssetStorageClient:
    def __init__(self) -> None:
        self.puts: list[dict[str, object]] = []

    def put_object(
        self,
        *,
        data: bytes,
        ref: StorageRef | None = None,
        storage_uri: str | None = None,
        key: str | None = None,
        bucket: str | None = None,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
        checksum_sha256: str | None = None,
    ) -> StoredObject:
        _ = storage_uri, key, bucket
        assert ref is not None
        self.puts.append(
            {
                "data": data,
                "ref": ref,
                "content_type": content_type,
                "metadata": metadata or {},
                "checksum_sha256": checksum_sha256,
            }
        )
        return StoredObject(
            ref=ref,
            size_bytes=len(data),
            content_type=content_type,
            metadata=metadata or {},
            checksum_sha256=checksum_sha256,
        )


def test_compose_and_store_layered_reel_persists_derived_render(tmp_path: Path) -> None:
    bg = tmp_path / "bg.png"
    fg = tmp_path / "fg.png"
    hook = tmp_path / "hook.txt"
    audio = tmp_path / "audio.wav"
    for path in (bg, fg, audio):
        path.write_bytes(b"asset")
    hook.write_text("Nobody sees this part", encoding="utf-8")
    storage = _FakeAssetStorageClient()

    result = compose_and_store_layered_reel(
        _manifest(),
        asset_sources={
            "asset-bg": bg,
            "asset-fg": fg,
            "asset-hook": hook,
            "asset-audio": audio,
        },
        output_path=tmp_path / "final.mp4",
        client=storage,  # type: ignore[arg-type]
        layout=CanonicalStorageLayout(bucket="content-lab"),
        render_asset_id="render-asset-1",
        runner=_FakeRunner(),  # type: ignore[arg-type]
        staging_dir=tmp_path / "staged",
        upload_metadata={"composition_manifest": "v1"},
    )

    assert result.stored_asset.storage_uri == (
        "s3://content-lab/assets/derived/render-asset-1/final.mp4"
    )
    assert storage.puts[0]["data"] == b"rendered-mp4"
    assert storage.puts[0]["metadata"] == {"composition_manifest": "v1"}


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe is not installed")
def test_compose_layered_reel_renders_vertical_mp4_with_alpha_text_and_audio(
    tmp_path: Path,
) -> None:
    bg = tmp_path / "bg.png"
    fg = tmp_path / "fg.png"
    hook = tmp_path / "hook.txt"
    audio = tmp_path / "audio.wav"
    output = tmp_path / "final.mp4"

    run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=navy:s=1080x1920:d=1",
            "-frames:v",
            "1",
            str(bg),
        ]
    )
    run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red@0.65:s=360x360:d=1",
            "-frames:v",
            "1",
            "-pix_fmt",
            "rgba",
            str(fg),
        ]
    )
    run_command(
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
    hook.write_text("Nobody sees this part", encoding="utf-8")

    compose_layered_reel(
        _manifest(duration=1.0),
        asset_sources={
            "asset-bg": bg,
            "asset-fg": fg,
            "asset-hook": hook,
            "asset-audio": audio,
        },
        output_path=output,
        runner=FFmpegRunner(timeout_seconds=20.0),
        staging_dir=tmp_path / "staged",
    )

    metadata = probe_media(output)
    assert metadata["width"] == 1080
    assert metadata["height"] == 1920
    assert metadata["has_audio_track"] is True
