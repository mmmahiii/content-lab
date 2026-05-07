"""Phase-1 FFmpeg compositor for ``CompositionManifest`` payloads."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from content_lab_editing.composition_manifest import CompositionLayer, CompositionManifest
from content_lab_editing.composition_preflight import (
    SourceAssetInput,
    StorageObjectProbe,
    ensure_composition_preflight,
    source_value,
)
from content_lab_editing.ffmpeg import FFmpegRunner, FFmpegRunResult
from content_lab_editing.motion_transforms import layer_has_motion, motion_spec_for_layer
from content_lab_storage import CanonicalStorageLayout, S3StorageClient, StoredAssetBytes
from content_lab_storage.assets import persist_asset_bytes


class StorageDownloader(Protocol):
    """Minimal object-storage surface needed to stage compositor inputs."""

    def get_object(self, *, storage_uri: str) -> object:
        """Return an object with a ``body: bytes`` attribute."""


@dataclass(frozen=True, slots=True)
class LayeredCompositionResult:
    """Completed layered composition details."""

    output_path: Path
    command: tuple[str, ...]
    filter_complex: str
    staged_assets: dict[str, Path]
    ffmpeg_result: FFmpegRunResult


@dataclass(frozen=True, slots=True)
class StoredLayeredCompositionResult:
    """Layered composition result plus derived-asset storage metadata."""

    composition: LayeredCompositionResult
    stored_asset: StoredAssetBytes


def compose_layered_reel(
    manifest: CompositionManifest,
    *,
    asset_sources: Mapping[str, SourceAssetInput],
    output_path: str | Path,
    runner: FFmpegRunner | None = None,
    storage_client: StorageDownloader | None = None,
    staging_dir: str | Path | None = None,
    timeout_seconds: float | None = None,
) -> LayeredCompositionResult:
    """Render a vertical MP4 from a composition manifest and asset source mapping."""

    resolved_runner = runner or FFmpegRunner()
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    ensure_composition_preflight(
        manifest,
        asset_sources=asset_sources,
        storage_client=cast(StorageObjectProbe | None, storage_client),
        require_content_hash=False,
    )
    staged_assets = stage_composition_assets(
        manifest,
        asset_sources=asset_sources,
        staging_dir=staging_dir or output.parent / "composition-assets",
        storage_client=storage_client,
    )
    args, filter_complex = build_layered_ffmpeg_args(
        manifest,
        staged_assets=staged_assets,
        output_path=output,
    )
    result = resolved_runner.run_ffmpeg(args, timeout_seconds=timeout_seconds)
    return LayeredCompositionResult(
        output_path=output,
        command=result.command,
        filter_complex=filter_complex,
        staged_assets=staged_assets,
        ffmpeg_result=result,
    )


def compose_and_store_layered_reel(
    manifest: CompositionManifest,
    *,
    asset_sources: Mapping[str, SourceAssetInput],
    output_path: str | Path,
    client: S3StorageClient,
    layout: CanonicalStorageLayout,
    render_asset_id: str,
    runner: FFmpegRunner | None = None,
    storage_client: StorageDownloader | None = None,
    staging_dir: str | Path | None = None,
    timeout_seconds: float | None = None,
    asset_class: str = "final_render",
    content_type: str = "video/mp4",
    filename: str = "final.mp4",
    upload_metadata: Mapping[str, str] | None = None,
) -> StoredLayeredCompositionResult:
    """Render a layered reel and persist the MP4 as a derived asset."""

    composition = compose_layered_reel(
        manifest,
        asset_sources=asset_sources,
        output_path=output_path,
        runner=runner,
        storage_client=storage_client,
        staging_dir=staging_dir,
        timeout_seconds=timeout_seconds,
    )
    stored_asset = persist_asset_bytes(
        client=client,
        layout=layout,
        asset_id=render_asset_id,
        asset_class=asset_class,
        data=composition.output_path.read_bytes(),
        content_type=content_type,
        metadata=dict(upload_metadata or {}),
        filename=filename,
    )
    return StoredLayeredCompositionResult(composition=composition, stored_asset=stored_asset)


def stage_composition_assets(
    manifest: CompositionManifest,
    *,
    asset_sources: Mapping[str, SourceAssetInput],
    staging_dir: str | Path,
    storage_client: StorageDownloader | None = None,
) -> dict[str, Path]:
    """Resolve manifest asset IDs to local files, downloading S3 objects when needed."""

    stage_root = Path(staging_dir)
    stage_root.mkdir(parents=True, exist_ok=True)
    staged: dict[str, Path] = {}
    for layer in [manifest.background_layer, *manifest.layers, *manifest.audio_layers]:
        if layer.asset_id in staged:
            continue
        raw_source = asset_sources.get(layer.asset_id)
        if raw_source is None:
            raise KeyError(f"missing asset source for asset_id {layer.asset_id!r}")
        source = source_value(raw_source)
        source_text = str(source)
        if source_text.startswith("s3://"):
            if storage_client is None:
                raise ValueError("storage_client is required for s3:// asset sources")
            downloaded = storage_client.get_object(storage_uri=source_text)
            body = getattr(downloaded, "body", None)
            if not isinstance(body, bytes):
                raise TypeError("storage_client.get_object must return an object with bytes body")
            target = (
                stage_root
                / f"{_safe_asset_filename(layer.asset_id)}{_source_suffix(source_text, layer)}"
            )
            target.write_bytes(body)
            staged[layer.asset_id] = target
            continue

        local_path = Path(source)
        if not local_path.exists() or not local_path.is_file():
            raise FileNotFoundError(f"asset source for {layer.asset_id!r} does not exist")
        target = stage_root / local_path.name
        if local_path.resolve() != target.resolve():
            shutil.copyfile(local_path, target)
        staged[layer.asset_id] = target
    return staged


def build_layered_ffmpeg_args(
    manifest: CompositionManifest,
    *,
    staged_assets: Mapping[str, Path],
    output_path: str | Path,
) -> tuple[list[str | Path], str]:
    """Build the FFmpeg argv and filter graph for a manifest."""

    visual_inputs = [manifest.background_layer]
    visual_inputs.extend(
        layer for layer in manifest.visual_layers_in_render_order if layer.media_type != "text"
    )
    audio_inputs = list(manifest.audio_layers)
    args: list[str | Path] = ["-y"]
    input_indexes: dict[str, int] = {}

    for layer in visual_inputs:
        input_indexes[layer.layer_id] = len(input_indexes)
        if layer.media_type == "image":
            args.extend(["-loop", "1", "-t", _seconds(manifest.duration)])
        args.extend(["-i", staged_assets[layer.asset_id]])

    for layer in audio_inputs:
        input_indexes[layer.layer_id] = len(input_indexes)
        args.extend(["-stream_loop", "-1", "-i", staged_assets[layer.asset_id]])

    filter_complex = build_layered_filter_graph(
        manifest,
        input_indexes=input_indexes,
        staged_assets=staged_assets,
    )
    final_video_label = _final_video_label(manifest)
    final_audio_label = "mixedaudio" if manifest.audio_layers else None

    args.extend(["-filter_complex", filter_complex, "-map", f"[{final_video_label}]"])
    if final_audio_label is not None:
        args.extend(["-map", f"[{final_audio_label}]"])
    else:
        args.append("-an")

    preset = manifest.export_preset
    args.extend(
        [
            "-t",
            _seconds(manifest.duration),
            "-r",
            str(manifest.fps),
            "-c:v",
            preset.video_codec,
            "-pix_fmt",
            preset.pixel_format,
            "-preset",
            preset.preset,
            "-crf",
            str(preset.crf),
        ]
    )
    if preset.video_bitrate is not None:
        args.extend(["-b:v", preset.video_bitrate])
    if final_audio_label is not None:
        args.extend(
            ["-c:a", preset.audio_codec, "-b:a", preset.audio_bitrate, "-ar", "48000", "-ac", "2"]
        )
    args.extend(["-movflags", "+faststart", output_path])
    return args, filter_complex


def build_layered_filter_graph(
    manifest: CompositionManifest,
    *,
    input_indexes: Mapping[str, int],
    staged_assets: Mapping[str, Path],
) -> str:
    """Build the FFmpeg filter graph for phase-1 layered composition."""

    filters: list[str] = []
    background = manifest.background_layer
    background_input = input_indexes[background.layer_id]
    filters.append(
        f"[{background_input}:v]"
        f"{_crop_filter(background)}"
        f"scale={manifest.canvas_width}:{manifest.canvas_height}:force_original_aspect_ratio=increase,"
        f"crop={manifest.canvas_width}:{manifest.canvas_height},"
        f"fps={manifest.fps},trim=duration={_seconds(manifest.duration)},"
        "setpts=PTS-STARTPTS,setsar=1[base0]"
    )

    current = "base0"
    overlay_index = 0
    for layer in manifest.visual_layers_in_render_order:
        next_label = f"v{overlay_index + 1}"
        if layer.media_type == "text":
            filters.append(
                _drawtext_filter(current, next_label, layer, staged_assets=staged_assets)
            )
            current = next_label
            overlay_index += 1
            continue

        input_index = input_indexes[layer.layer_id]
        prepared_label = f"layer{overlay_index}"
        filters.append(_prepare_visual_layer_filter(input_index, layer, prepared_label))
        filters.append(
            f"[{current}][{prepared_label}]"
            f"overlay=x='{_motion_x_expression(layer)}':y='{_motion_y_expression(layer)}':"
            "eof_action=pass:"
            f"enable='{_between(layer)}'[{next_label}]"
        )
        current = next_label
        overlay_index += 1

    final_video = _final_video_label(manifest)
    filters.append(f"[{current}]format=yuv420p[{final_video}]")

    if manifest.audio_layers:
        audio_labels: list[str] = []
        for index, layer in enumerate(manifest.audio_layers):
            input_index = input_indexes[layer.layer_id]
            label = f"a{index}"
            delay_ms = max(0, round(layer.start_time * 1000))
            filters.append(
                f"[{input_index}:a]atrim=0:{_seconds(layer.duration)},"
                f"asetpts=PTS-STARTPTS,adelay={delay_ms}|{delay_ms},"
                f"volume={layer.opacity}[{label}]"
            )
            audio_labels.append(label)
        inputs = "".join(f"[{label}]" for label in audio_labels)
        filters.append(
            f"{inputs}amix=inputs={len(audio_labels)}:duration=longest,"
            f"atrim=0:{_seconds(manifest.duration)},asetpts=PTS-STARTPTS[mixedaudio]"
        )

    return ";".join(filters)


def _prepare_visual_layer_filter(
    input_index: int, layer: CompositionLayer, output_label: str
) -> str:
    width, height = _scale_dimensions(layer)
    rotate = "" if layer.rotation == 0 else f"rotate={_radians(layer.rotation)}:c=none,"
    return (
        f"[{input_index}:v]"
        f"{_crop_filter(layer)}"
        f"scale={width}:{height}{_scale_eval_option(layer)},"
        f"format=rgba,{rotate}"
        f"colorchannelmixer=aa={layer.opacity},"
        f"trim=duration={_seconds(layer.duration)},"
        f"setpts=PTS-STARTPTS+{_seconds(layer.start_time)}/TB[{output_label}]"
    )


def _drawtext_filter(
    input_label: str,
    output_label: str,
    layer: CompositionLayer,
    *,
    staged_assets: Mapping[str, Path],
) -> str:
    text_path = staged_assets.get(layer.asset_id)
    text = layer.asset_id if text_path is None else text_path.read_text(encoding="utf-8").strip()
    font_size = layer.height or 72
    line_spacing = max(4, round(font_size * 0.18))
    return (
        f"[{input_label}]drawtext="
        f"text='{_escape_drawtext(text)}':"
        f"x={layer.x}:y={layer.y}:"
        f"fontsize={font_size}:fontcolor=white@{layer.opacity}:"
        f"line_spacing={line_spacing}:box=1:boxcolor=black@0.35:boxborderw=24:"
        f"enable='{_between(layer)}'[{output_label}]"
    )


def _crop_filter(layer: CompositionLayer) -> str:
    if layer.crop is None:
        return ""
    return f"crop={layer.crop.width}:{layer.crop.height}:{layer.crop.x}:{layer.crop.y},"


def _between(layer: CompositionLayer) -> str:
    return f"between(t\\,{_seconds(layer.start_time)}\\,{_seconds(layer.end_time)})"


def _seconds(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _scale_dimensions(layer: CompositionLayer) -> tuple[str, str]:
    if not layer_has_motion(layer):
        width = "iw" if layer.width is None else str(round(layer.width * layer.scale))
        height = "ih" if layer.height is None else str(round(layer.height * layer.scale))
        return width, height

    scale_expr = _motion_scale_expression(layer)
    base_width = "iw" if layer.width is None else str(layer.width)
    base_height = "ih" if layer.height is None else str(layer.height)
    return (
        f"'trunc({base_width}*({scale_expr}))'",
        f"'trunc({base_height}*({scale_expr}))'",
    )


def _scale_eval_option(layer: CompositionLayer) -> str:
    return ":eval=frame" if layer_has_motion(layer) else ""


def _motion_scale_expression(layer: CompositionLayer) -> str:
    spec = motion_spec_for_layer(layer)
    start = spec.scale_from * layer.scale
    end = spec.scale_to * layer.scale
    if start == end:
        return _expr_number(start)
    return (
        f"{_expr_number(start)}+"
        f"({_expr_number(end)}-{_expr_number(start)})*(t/{_expr_number(layer.duration)})"
    )


def _motion_x_expression(layer: CompositionLayer) -> str:
    transform = layer.motion_transform
    phase = 0.0 if transform is None else transform.phase
    spec = motion_spec_for_layer(layer)
    rel = _relative_time_expression(layer)
    if spec.preset == "pan_left":
        return f"{_expr_number(layer.x + spec.amplitude)}-{_expr_number(spec.amplitude * 2)}*{rel}"
    if spec.preset == "pan_right":
        return f"{_expr_number(layer.x - spec.amplitude)}+{_expr_number(spec.amplitude * 2)}*{rel}"
    if spec.preset == "shake_light":
        return (
            f"{_expr_number(layer.x)}+{_expr_number(spec.amplitude)}*"
            f"sin(2*PI*{_expr_number(spec.frequency)}*t+{_expr_number(phase)})"
        )
    if spec.preset == "parallax_basic":
        return f"{_expr_number(layer.x)}+{_expr_number(spec.translate_x)}*{rel}"
    return _expr_number(layer.x)


def _motion_y_expression(layer: CompositionLayer) -> str:
    transform = layer.motion_transform
    phase = 0.0 if transform is None else transform.phase
    spec = motion_spec_for_layer(layer)
    rel = _relative_time_expression(layer)
    if spec.preset == "float":
        return (
            f"{_expr_number(layer.y)}+{_expr_number(spec.amplitude)}*"
            f"sin(2*PI*{_expr_number(spec.frequency)}*{rel}+{_expr_number(phase)})"
        )
    if spec.preset == "shake_light":
        return (
            f"{_expr_number(layer.y)}+{_expr_number(spec.amplitude)}*"
            f"sin(2*PI*{_expr_number(spec.frequency + 1.3)}*t+{_expr_number(phase)})"
        )
    if spec.preset == "parallax_basic":
        return f"{_expr_number(layer.y)}+{_expr_number(spec.translate_y)}*{rel}"
    return _expr_number(layer.y)


def _relative_time_expression(layer: CompositionLayer) -> str:
    return f"((t-{_expr_number(layer.start_time)})/{_expr_number(layer.duration)})"


def _expr_number(value: float | int) -> str:
    return f"{float(value):.6f}".rstrip("0").rstrip(".")


def _radians(degrees: float) -> str:
    return f"{degrees}*PI/180"


def _final_video_label(manifest: CompositionManifest) -> str:
    _ = manifest
    return "finalv"


def _escape_drawtext(value: str) -> str:
    return (
        value.replace("\\", r"\\")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace("[", r"\[")
        .replace("]", r"\]")
        .replace("%", r"\%")
        .replace("\r\n", r"\n")
        .replace("\n", r"\n")
    )


def _source_suffix(source: str, layer: CompositionLayer) -> str:
    suffix = Path(source).suffix
    if suffix:
        return suffix
    return {
        "audio": ".mp3",
        "image": ".png",
        "text": ".txt",
        "video": ".mp4",
    }.get(layer.media_type, ".bin")


def _safe_asset_filename(asset_id: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in asset_id)


__all__ = [
    "LayeredCompositionResult",
    "StorageDownloader",
    "StoredLayeredCompositionResult",
    "build_layered_ffmpeg_args",
    "build_layered_filter_graph",
    "compose_and_store_layered_reel",
    "compose_layered_reel",
    "stage_composition_assets",
]
