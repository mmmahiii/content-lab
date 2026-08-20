"""Colour and edge harmonisation analysis for layered FFmpeg composition."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content_lab_editing.composition_manifest import (
    CompositionLayer,
    LayerHarmonisationPass,
)

_ALPHA_KINDS = frozenset(
    {
        "transparent_cutout_png",
        "masked_image",
        "foreground_layer_image",
        "subject_image",
        "object_image",
        "prop_image",
    }
)
_ALPHA_THRESHOLD = 16


@dataclass(frozen=True, slots=True)
class SceneColourStats:
    mean_r: float
    mean_g: float
    mean_b: float
    mean_luma: float
    luma_std: float
    sample_count: int


@dataclass(frozen=True, slots=True)
class HarmonisationParams:
    """Derived FFmpeg tuning values for one foreground layer."""

    colour_match_to_scene: bool
    brightness_match: bool
    contrast_match: bool
    shadow_blend: bool
    edge_softening: bool
    brightness_delta: float = 0.0
    contrast_factor: float = 1.0
    red_gain: float = 1.0
    green_gain: float = 1.0
    blue_gain: float = 1.0
    edge_blur_radius: int = 0
    shadow_offset_y: int = 0
    shadow_blur_radius: int = 0
    shadow_opacity: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "colour_match_to_scene": self.colour_match_to_scene,
            "brightness_match": self.brightness_match,
            "contrast_match": self.contrast_match,
            "shadow_blend": self.shadow_blend,
            "edge_softening": self.edge_softening,
            "brightness_delta": self.brightness_delta,
            "contrast_factor": self.contrast_factor,
            "red_gain": self.red_gain,
            "green_gain": self.green_gain,
            "blue_gain": self.blue_gain,
            "edge_blur_radius": self.edge_blur_radius,
            "shadow_offset_y": self.shadow_offset_y,
            "shadow_blur_radius": self.shadow_blur_radius,
            "shadow_opacity": self.shadow_opacity,
        }


def default_harmonisation_for_layer(layer: CompositionLayer) -> LayerHarmonisationPass | None:
    """Return default harmonisation for alpha-like foreground cutouts."""

    if layer.media_type == "text" or layer.media_type == "audio":
        return None
    if layer.mask_mode in {"alpha", "luma"}:
        return LayerHarmonisationPass(
            colour_match_to_scene=True,
            brightness_match=True,
            contrast_match=True,
            shadow_blend=True,
            edge_softening=True,
        )
    if layer.asset_kind in _ALPHA_KINDS:
        return LayerHarmonisationPass(
            colour_match_to_scene=True,
            brightness_match=True,
            contrast_match=True,
            shadow_blend=True,
            edge_softening=True,
        )
    return None


def effective_harmonisation(layer: CompositionLayer) -> LayerHarmonisationPass | None:
    if layer.harmonisation is not None:
        return layer.harmonisation if layer.harmonisation.any_enabled() else None
    return default_harmonisation_for_layer(layer)


def analyse_scene_region(
    background_path: Path,
    layer: CompositionLayer,
    *,
    canvas_width: int,
    canvas_height: int,
) -> SceneColourStats | None:
    """Sample the background image under the layer placement box."""

    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return None

    if not background_path.exists():
        return None
    width = layer.width or canvas_width
    height = layer.height or canvas_height
    left = max(0, min(canvas_width - 1, layer.x))
    top = max(0, min(canvas_height - 1, layer.y))
    right = max(left + 1, min(canvas_width, left + round(width * layer.scale)))
    bottom = max(top + 1, min(canvas_height, top + round(height * layer.scale)))
    try:
        with Image.open(background_path) as image:
            rgb = image.convert("RGB")
            if rgb.width != canvas_width or rgb.height != canvas_height:
                rgb = rgb.resize((canvas_width, canvas_height), Image.Resampling.BILINEAR)
            region = rgb.crop((left, top, right, bottom))
    except OSError:
        return None
    return _stats_from_rgb_image(region)


def analyse_foreground_layer(foreground_path: Path) -> SceneColourStats | None:
    """Sample opaque pixels from a foreground cutout."""

    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return None

    if not foreground_path.exists():
        return None
    try:
        with Image.open(foreground_path) as image:
            rgba = image.convert("RGBA")
    except OSError:
        return None

    total_r = 0.0
    total_g = 0.0
    total_b = 0.0
    total_luma = 0.0
    luma_values: list[float] = []
    count = 0
    for r, g, b, a in rgba.getdata():
        if a < _ALPHA_THRESHOLD:
            continue
        luma = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
        total_r += r / 255.0
        total_g += g / 255.0
        total_b += b / 255.0
        total_luma += luma
        luma_values.append(luma)
        count += 1
    if count == 0:
        return None
    mean_luma = total_luma / count
    variance = sum((value - mean_luma) ** 2 for value in luma_values) / count
    return SceneColourStats(
        mean_r=total_r / count,
        mean_g=total_g / count,
        mean_b=total_b / count,
        mean_luma=mean_luma,
        luma_std=max(0.0001, variance**0.5),
        sample_count=count,
    )


def derive_harmonisation_params(
    layer: CompositionLayer,
    *,
    scene: SceneColourStats,
    foreground: SceneColourStats,
    harmonisation: LayerHarmonisationPass,
) -> HarmonisationParams:
    strength = harmonisation.strength
    brightness_delta = 0.0
    if harmonisation.brightness_match:
        raw = (scene.mean_luma - foreground.mean_luma) * strength
        brightness_delta = max(-0.25, min(0.25, raw))

    contrast_factor = 1.0
    if harmonisation.contrast_match and foreground.luma_std > 0.0001:
        raw = scene.luma_std / foreground.luma_std
        contrast_factor = max(0.75, min(1.35, 1.0 + (raw - 1.0) * strength))

    red_gain = green_gain = blue_gain = 1.0
    if harmonisation.colour_match_to_scene:
        red_gain = _channel_gain(scene.mean_r, foreground.mean_r, strength)
        green_gain = _channel_gain(scene.mean_g, foreground.mean_g, strength)
        blue_gain = _channel_gain(scene.mean_b, foreground.mean_b, strength)

    edge_blur_radius = 0
    if harmonisation.edge_softening:
        edge_blur_radius = max(1, round(1 + 3 * strength))

    shadow_offset_y = 0
    shadow_blur_radius = 0
    shadow_opacity = 0.0
    if harmonisation.shadow_blend:
        layer_height = layer.height or 512
        shadow_offset_y = max(1, round(0.04 * layer_height * strength))
        shadow_blur_radius = max(4, round(8 + 8 * strength))
        shadow_opacity = max(0.25, min(0.45, 0.25 + 0.2 * strength))

    return HarmonisationParams(
        colour_match_to_scene=harmonisation.colour_match_to_scene,
        brightness_match=harmonisation.brightness_match,
        contrast_match=harmonisation.contrast_match,
        shadow_blend=harmonisation.shadow_blend,
        edge_softening=harmonisation.edge_softening,
        brightness_delta=brightness_delta,
        contrast_factor=contrast_factor,
        red_gain=red_gain,
        green_gain=green_gain,
        blue_gain=blue_gain,
        edge_blur_radius=edge_blur_radius,
        shadow_offset_y=shadow_offset_y,
        shadow_blur_radius=shadow_blur_radius,
        shadow_opacity=shadow_opacity,
    )


def build_harmonisation_params_for_layer(
    layer: CompositionLayer,
    *,
    background_path: Path,
    foreground_path: Path,
    canvas_width: int,
    canvas_height: int,
) -> tuple[HarmonisationParams | None, dict[str, Any]]:
    """Analyse assets and derive harmonisation parameters for one layer."""

    harmonisation = effective_harmonisation(layer)
    trace: dict[str, Any] = {
        "layer_id": layer.layer_id,
        "asset_id": layer.asset_id,
        "enabled_passes": None if harmonisation is None else harmonisation.model_dump(mode="json"),
    }
    if harmonisation is None:
        trace["skipped_reason"] = "harmonisation_disabled"
        return None, trace

    scene = analyse_scene_region(
        background_path,
        layer,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
    )
    foreground = analyse_foreground_layer(foreground_path)
    if scene is None or foreground is None:
        trace["skipped_reason"] = "analysis_failed"
        return None, trace

    params = derive_harmonisation_params(
        layer,
        scene=scene,
        foreground=foreground,
        harmonisation=harmonisation,
    )
    trace["params"] = params.as_dict()
    trace["scene_stats"] = {
        "mean_luma": round(scene.mean_luma, 4),
        "luma_std": round(scene.luma_std, 4),
    }
    trace["foreground_stats"] = {
        "mean_luma": round(foreground.mean_luma, 4),
        "luma_std": round(foreground.luma_std, 4),
    }
    return params, trace


def build_harmonisation_filter_segments(
    input_label: str,
    output_label: str,
    params: HarmonisationParams,
) -> list[str]:
    """Return FFmpeg filter_complex segments for colour/edge harmonisation."""

    segments: list[str] = []
    current = input_label
    colour_parts: list[str] = []
    if params.brightness_match or params.contrast_match:
        colour_parts.append(
            f"eq=brightness={_fmt(params.brightness_delta)}:contrast={_fmt(params.contrast_factor)}"
        )
    if params.colour_match_to_scene:
        rs = _fmt((params.red_gain - 1.0) * 0.35)
        gs = _fmt((params.green_gain - 1.0) * 0.35)
        bs = _fmt((params.blue_gain - 1.0) * 0.35)
        colour_parts.append(f"colorbalance=rs={rs}:gs={gs}:bs={bs}")
    if colour_parts:
        mid = f"{output_label}_colour"
        segments.append(f"[{current}]{','.join(colour_parts)}[{mid}]")
        current = mid

    if params.edge_softening and params.edge_blur_radius > 0:
        lr = params.edge_blur_radius
        segments.append(
            f"[{current}]split=2[{output_label}_v][{output_label}_a];"
            f"[{output_label}_a]alphaextract,boxblur={lr}:{lr}[{output_label}_blur];"
            f"[{output_label}_v][{output_label}_blur]alphamerge[{output_label}]"
        )
        return segments

    if current != output_label:
        segments.append(f"[{current}]null[{output_label}]")
    return segments


def _channel_gain(scene_mean: float, foreground_mean: float, strength: float) -> float:
    if foreground_mean <= 0.01:
        return 1.0
    raw = scene_mean / foreground_mean
    return max(0.7, min(1.35, 1.0 + (raw - 1.0) * strength))


def _stats_from_rgb_image(image: object) -> SceneColourStats:
    from PIL import Image

    assert isinstance(image, Image.Image)
    pixels = list(image.getdata())
    if not pixels:
        return SceneColourStats(0.0, 0.0, 0.0, 0.0, 0.0001, 0)
    total_r = total_g = total_b = total_luma = 0.0
    luma_values: list[float] = []
    for pixel in pixels:
        if isinstance(pixel, tuple):
            r, g, b = pixel[0], pixel[1], pixel[2]
        else:
            r = g = b = pixel
        luma = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
        total_r += r / 255.0
        total_g += g / 255.0
        total_b += b / 255.0
        total_luma += luma
        luma_values.append(luma)
    count = len(pixels)
    mean_luma = total_luma / count
    variance = sum((value - mean_luma) ** 2 for value in luma_values) / count
    return SceneColourStats(
        mean_r=total_r / count,
        mean_g=total_g / count,
        mean_b=total_b / count,
        mean_luma=mean_luma,
        luma_std=max(0.0001, variance**0.5),
        sample_count=count,
    )


def _fmt(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


__all__ = [
    "HarmonisationParams",
    "SceneColourStats",
    "analyse_foreground_layer",
    "analyse_scene_region",
    "build_harmonisation_filter_segments",
    "build_harmonisation_params_for_layer",
    "default_harmonisation_for_layer",
    "derive_harmonisation_params",
    "effective_harmonisation",
]
