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
from content_lab_editing.harmonisation import (
    HarmonisationParams,
    build_harmonisation_filter_segments,
    build_harmonisation_params_for_layer,
)
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
    harmonisation_trace: tuple[dict[str, object], ...] = ()


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
    harmonisation_by_layer, harmonisation_trace = _build_harmonisation_params(
        manifest,
        staged_assets=staged_assets,
    )
    args, filter_complex = build_layered_ffmpeg_args(
        manifest,
        staged_assets=staged_assets,
        output_path=output,
        harmonisation_by_layer=harmonisation_by_layer,
    )
    result = resolved_runner.run_ffmpeg(args, timeout_seconds=timeout_seconds)
    return LayeredCompositionResult(
        output_path=output,
        command=result.command,
        filter_complex=filter_complex,
        staged_assets=staged_assets,
        ffmpeg_result=result,
        harmonisation_trace=harmonisation_trace,
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


def _build_harmonisation_params(
    manifest: CompositionManifest,
    *,
    staged_assets: Mapping[str, Path],
) -> tuple[dict[str, HarmonisationParams], tuple[dict[str, object], ...]]:
    background_path = staged_assets[manifest.background_layer.asset_id]
    by_layer: dict[str, HarmonisationParams] = {}
    traces: list[dict[str, object]] = []
    for layer in manifest.visual_layers_in_render_order:
        if layer.media_type == "text":
            continue
        foreground_path = staged_assets[layer.asset_id]
        params, trace = build_harmonisation_params_for_layer(
            layer,
            background_path=background_path,
            foreground_path=foreground_path,
            canvas_width=manifest.canvas_width,
            canvas_height=manifest.canvas_height,
        )
        traces.append(trace)
        if params is not None:
            by_layer[layer.layer_id] = params
    return by_layer, tuple(traces)


def build_layered_ffmpeg_args(
    manifest: CompositionManifest,
    *,
    staged_assets: Mapping[str, Path],
    output_path: str | Path,
    harmonisation_by_layer: Mapping[str, HarmonisationParams] | None = None,
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
        harmonisation_by_layer=harmonisation_by_layer or {},
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
    harmonisation_by_layer: Mapping[str, HarmonisationParams] | None = None,
) -> str:
    """Build the FFmpeg filter graph for phase-1 layered composition."""

    harmonisation_by_layer = harmonisation_by_layer or {}
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
        harmonisation = harmonisation_by_layer.get(layer.layer_id)
        filters.extend(
            _visual_layer_filter_segments(
                input_index,
                layer,
                prepared_label,
                harmonisation=harmonisation,
            )
        )
        if harmonisation is not None and harmonisation.shadow_blend:
            shadow_label = f"{prepared_label}_shadow"
            shadow_y = f"{_motion_y_expression(layer)}+{harmonisation.shadow_offset_y}"
            filters.append(
                f"[{prepared_label}]split=2[{prepared_label}_fg][{shadow_label}_a];"
                f"[{shadow_label}_a]alphaextract,boxblur={harmonisation.shadow_blur_radius}:"
                f"{harmonisation.shadow_blur_radius},"
                f"colorchannelmixer=aa={_fmt(harmonisation.shadow_opacity)}[{shadow_label}];"
                f"[{current}][{shadow_label}]overlay=x='{_motion_x_expression(layer)}':"
                f"y='{shadow_y}':eof_action=pass:enable='{_between(layer)}'[{next_label}_shadow];"
                f"[{next_label}_shadow][{prepared_label}_fg]overlay=x='{_motion_x_expression(layer)}':"
                f"y='{_motion_y_expression(layer)}':eof_action=pass:"
                f"enable='{_between(layer)}'[{next_label}]"
            )
        else:
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


def _visual_layer_filter_segments(
    input_index: int,
    layer: CompositionLayer,
    output_label: str,
    *,
    harmonisation: HarmonisationParams | None,
) -> list[str]:
    pre_label = f"{output_label}_pre"
    segments = [_prepare_visual_layer_base_filter(input_index, layer, pre_label)]
    source_label = pre_label
    if harmonisation is not None:
        harm_label = f"{output_label}_harm"
        harm_segments = build_harmonisation_filter_segments(pre_label, harm_label, harmonisation)
        if harm_segments:
            segments.extend(harm_segments)
            source_label = harm_label
    segments.append(_finalize_visual_layer_filter(source_label, output_label, layer))
    return segments


def _prepare_visual_layer_base_filter(
    input_index: int, layer: CompositionLayer, output_label: str
) -> str:
    width, height = _scale_dimensions(layer)
    return (
        f"[{input_index}:v]"
        f"{_crop_filter(layer)}"
        f"scale={width}:{height}{_scale_eval_option(layer)},"
        f"format=rgba[{output_label}]"
    )


def _finalize_visual_layer_filter(
    input_label: str, output_label: str, layer: CompositionLayer
) -> str:
    rotate = "" if layer.rotation == 0 else f"rotate={_radians(layer.rotation)}:c=none,"
    return (
        f"[{input_label}]{rotate}"
        f"colorchannelmixer=aa={layer.opacity},"
        f"trim=duration={_seconds(layer.duration)},"
        f"setpts=PTS-STARTPTS+{_seconds(layer.start_time)}/TB[{output_label}]"
    )


def _prepare_visual_layer_filter(
    input_index: int, layer: CompositionLayer, output_label: str
) -> str:
    """Legacy single-string visual layer filter (no harmonisation)."""

    return ";".join(
        _visual_layer_filter_segments(input_index, layer, output_label, harmonisation=None)
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

    # FFmpeg 4.x rejects the `t` time variable inside scale expressions on some builds.
    # Use the largest intended transform scale statically and keep animation in overlay
    # position expressions, which are supported across the local/dev FFmpeg versions.
    safe_scale = _static_motion_scale(layer)
    width = "iw" if layer.width is None else str(round(layer.width * safe_scale))
    height = "ih" if layer.height is None else str(round(layer.height * safe_scale))
    return width, height


def _scale_eval_option(layer: CompositionLayer) -> str:
    """Omit ``eval=frame`` animated scale (incompatible with FFmpeg 4.2 + ``t``); see ``_ken_burns_shift_exprs``."""

    _ = layer
    return ""


def _static_motion_scale(layer: CompositionLayer) -> float:
    spec = motion_spec_for_layer(layer)
    return layer.scale * max(spec.scale_from, spec.scale_to)


def _ken_burns_shift_exprs(layer: CompositionLayer) -> tuple[str, str] | None:
    """Return (dx, dy) expressions so overlay x/y can simulate scale ramps without animated scale.

    The layer bitmap is scaled statically to the larger of ``scale_from`` / ``scale_to``; these
    offsets move the top-left so the viewport appears to zoom while staying compatible with
    FFmpeg 4.x builds that reject ``t`` inside ``scale`` eval expressions.
    """

    spec = motion_spec_for_layer(layer)
    if spec.scale_from == spec.scale_to:
        return None
    if layer.width is None or layer.height is None:
        return None
    rel = _relative_time_expression(layer)
    hi = max(spec.scale_from, spec.scale_to)
    w_full = round(layer.width * layer.scale * hi)
    w_s = round(layer.width * layer.scale * spec.scale_from)
    w_e = round(layer.width * layer.scale * spec.scale_to)
    h_full = round(layer.height * layer.scale * hi)
    h_s = round(layer.height * layer.scale * spec.scale_from)
    h_e = round(layer.height * layer.scale * spec.scale_to)
    if w_s == w_e and h_s == h_e:
        return None
    dx = (
        f"({_expr_number(w_full)}-({_expr_number(w_s)}+"
        f"({_expr_number(w_e)}-{_expr_number(w_s)})*{rel}))/2"
    )
    dy = (
        f"({_expr_number(h_full)}-({_expr_number(h_s)}+"
        f"({_expr_number(h_e)}-{_expr_number(h_s)})*{rel}))/2"
    )
    return dx, dy


def _motion_x_expression(layer: CompositionLayer) -> str:
    transform = layer.motion_transform
    phase = 0.0 if transform is None else transform.phase
    spec = motion_spec_for_layer(layer)
    rel = _relative_time_expression(layer)
    if spec.preset == "pan_left":
        ex = f"{_expr_number(layer.x + spec.amplitude)}-{_expr_number(spec.amplitude * 2)}*{rel}"
    elif spec.preset == "pan_right":
        ex = f"{_expr_number(layer.x - spec.amplitude)}+{_expr_number(spec.amplitude * 2)}*{rel}"
    elif spec.preset == "shake_light":
        ex = (
            f"{_expr_number(layer.x)}+{_expr_number(spec.amplitude)}*"
            f"sin(2*PI*{_expr_number(spec.frequency)}*t+{_expr_number(phase)})"
        )
    elif spec.preset == "parallax_basic":
        ex = f"{_expr_number(layer.x)}+{_expr_number(spec.translate_x)}*{rel}"
    else:
        ex = _expr_number(layer.x)

    kb = _ken_burns_shift_exprs(layer)
    if kb is not None:
        dx, _dy = kb
        ex = f"{ex}-({dx})"
    return ex


def _motion_y_expression(layer: CompositionLayer) -> str:
    transform = layer.motion_transform
    phase = 0.0 if transform is None else transform.phase
    spec = motion_spec_for_layer(layer)
    rel = _relative_time_expression(layer)
    if spec.preset == "float":
        ex = (
            f"{_expr_number(layer.y)}+{_expr_number(spec.amplitude)}*"
            f"sin(2*PI*{_expr_number(spec.frequency)}*{rel}+{_expr_number(phase)})"
        )
    elif spec.preset == "shake_light":
        ex = (
            f"{_expr_number(layer.y)}+{_expr_number(spec.amplitude)}*"
            f"sin(2*PI*{_expr_number(spec.frequency + 1.3)}*t+{_expr_number(phase)})"
        )
    elif spec.preset == "parallax_basic":
        ex = f"{_expr_number(layer.y)}+{_expr_number(spec.translate_y)}*{rel}"
    else:
        ex = _expr_number(layer.y)

    kb = _ken_burns_shift_exprs(layer)
    if kb is not None:
        _dx, dy = kb
        ex = f"{ex}-({dy})"
    return ex


def _relative_time_expression(layer: CompositionLayer) -> str:
    return f"((t-{_expr_number(layer.start_time)})/{_expr_number(layer.duration)})"


def _expr_number(value: float | int) -> str:
    return f"{float(value):.6f}".rstrip("0").rstrip(".")


def _fmt(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


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
