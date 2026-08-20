"""Structured manifest for layered reel composition."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

VisualMediaType = Literal["image", "video", "text"]
MediaType = Literal["image", "video", "audio", "text", "json", "unknown"]
MaskMode = Literal["none", "alpha", "luma", "chroma_key"]
BlendMode = Literal["normal", "multiply", "screen", "overlay", "add"]
MotionPreset = Literal[
    "none",
    "slow_zoom",
    "pan_left",
    "pan_right",
    "float",
    "scale_in",
    "scale_out",
    "shake_light",
    "parallax_basic",
]

VISUAL_MEDIA_TYPES = frozenset({"image", "video", "text"})
BACKGROUND_MEDIA_TYPES = frozenset({"image", "video"})
AUDIO_MEDIA_TYPES = frozenset({"audio"})
TEXT_ASSET_KINDS = frozenset({"hook_text", "caption_text", "subtitle_plan", "overlay_plan"})
AUDIO_ASSET_KINDS = frozenset({"audio_track", "sound_effect", "voiceover", "trimmed_audio"})


class CompositionCrop(BaseModel):
    """Source crop rectangle in source pixels."""

    model_config = ConfigDict(extra="forbid")

    x: int = Field(default=0, ge=0)
    y: int = Field(default=0, ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class SafeAreaConstraints(BaseModel):
    """Optional placement constraints for readable overlays and foreground objects."""

    model_config = ConfigDict(extra="forbid")

    top: int = Field(default=0, ge=0)
    right: int = Field(default=0, ge=0)
    bottom: int = Field(default=0, ge=0)
    left: int = Field(default=0, ge=0)
    enforce: bool = True


class MotionTransform(BaseModel):
    """Simple motion transform metadata for compositor implementations."""

    model_config = ConfigDict(extra="forbid")

    preset: MotionPreset = "none"
    translate_x: float = 0.0
    translate_y: float = 0.0
    scale_from: float | None = Field(default=None, gt=0)
    scale_to: float | None = Field(default=None, gt=0)
    opacity_from: float | None = Field(default=None, ge=0, le=1)
    opacity_to: float | None = Field(default=None, ge=0, le=1)
    amplitude: float | None = Field(default=None, ge=0)
    frequency: float | None = Field(default=None, gt=0)
    phase: float = 0.0
    params: dict[str, Any] = Field(default_factory=dict)


class CompositionAnimation(BaseModel):
    """Named animation preset plus implementation-specific parameters."""

    model_config = ConfigDict(extra="forbid")

    preset: str = Field(default="none", min_length=1, max_length=64)
    duration: float | None = Field(default=None, gt=0)
    easing: str | None = Field(default=None, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)


class LayerHarmonisationPass(BaseModel):
    """Per-layer colour and edge harmonisation applied during FFmpeg composition."""

    model_config = ConfigDict(extra="forbid")

    colour_match_to_scene: bool = False
    brightness_match: bool = False
    contrast_match: bool = False
    shadow_blend: bool = False
    edge_softening: bool = False
    strength: float = Field(default=0.75, ge=0.0, le=1.0)

    def any_enabled(self) -> bool:
        return (
            self.colour_match_to_scene
            or self.brightness_match
            or self.contrast_match
            or self.shadow_blend
            or self.edge_softening
        )


class CompositionLayer(BaseModel):
    """One timed visual or audio layer in a composition manifest."""

    model_config = ConfigDict(extra="forbid")

    layer_id: str = Field(min_length=1, max_length=128)
    asset_id: str = Field(min_length=1, max_length=128)
    asset_kind: str = Field(min_length=1, max_length=64)
    media_type: MediaType
    z_index: int = Field(ge=0)
    start_time: float = Field(ge=0)
    end_time: float = Field(gt=0)
    x: int = 0
    y: int = 0
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    scale: float = Field(default=1.0, gt=0)
    opacity: float = Field(default=1.0, ge=0, le=1)
    crop: CompositionCrop | None = None
    rotation: float = 0.0
    mask_mode: MaskMode = "none"
    blend_mode: BlendMode = "normal"
    animation: CompositionAnimation | None = None
    motion_transform: MotionTransform | None = None
    safe_area_constraints: SafeAreaConstraints | None = None
    harmonisation: LayerHarmonisationPass | None = None

    @model_validator(mode="after")
    def _validate_layer(self) -> CompositionLayer:
        if self.end_time <= self.start_time:
            raise ValueError("layer end_time must be greater than start_time")
        if self.media_type == "text" and self.asset_kind not in TEXT_ASSET_KINDS:
            raise ValueError("text layers must use a text-compatible asset_kind")
        if self.media_type == "audio" and self.asset_kind not in AUDIO_ASSET_KINDS:
            raise ValueError("audio layers must use an audio-compatible asset_kind")
        if self.media_type in {"image", "video"} and self.asset_kind in TEXT_ASSET_KINDS:
            raise ValueError("text asset_kind cannot be used as visual image/video media")
        if self.media_type != "audio" and self.blend_mode != "normal":
            # Keep the contract explicit while the phase-1 compositor only implements normal.
            return self
        return self

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


class CompositionExportPreset(BaseModel):
    """Output encoding preset for the layered compositor."""

    model_config = ConfigDict(extra="forbid")

    container: Literal["mp4"] = "mp4"
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    pixel_format: str = "yuv420p"
    crf: int = Field(default=18, ge=0, le=51)
    video_bitrate: str | None = None
    audio_bitrate: str = "192k"
    preset: str = "medium"


class CompositionManifest(BaseModel):
    """Concrete contract for rendering layered assets into one final reel."""

    model_config = ConfigDict(extra="forbid")

    canvas_width: int = Field(default=1080, gt=0)
    canvas_height: int = Field(default=1920, gt=0)
    duration: float = Field(gt=0)
    fps: int = Field(default=24, gt=0)
    background_layer: CompositionLayer
    layers: list[CompositionLayer] = Field(default_factory=list)
    audio_layers: list[CompositionLayer] = Field(default_factory=list)
    export_preset: CompositionExportPreset = Field(default_factory=CompositionExportPreset)

    @model_validator(mode="after")
    def _validate_manifest(self) -> CompositionManifest:
        _validate_background_layer(self.background_layer, duration=self.duration)
        _validate_visual_layers(self.layers, duration=self.duration)
        _validate_audio_layers(self.audio_layers, duration=self.duration)
        _validate_z_order(self.background_layer, self.layers)
        _validate_layer_ids([self.background_layer, *self.layers, *self.audio_layers])
        return self

    @property
    def visual_layers_in_render_order(self) -> tuple[CompositionLayer, ...]:
        return tuple(sorted(self.layers, key=lambda layer: layer.z_index))

    @property
    def asset_ids(self) -> tuple[str, ...]:
        return tuple(
            layer.asset_id for layer in [self.background_layer, *self.layers, *self.audio_layers]
        )


def _validate_background_layer(layer: CompositionLayer, *, duration: float) -> None:
    if layer.media_type not in BACKGROUND_MEDIA_TYPES:
        raise ValueError("background_layer must use image or video media")
    if layer.start_time != 0:
        raise ValueError("background_layer must start at 0")
    if layer.end_time < duration:
        raise ValueError("background_layer must cover the manifest duration")


def _validate_visual_layers(layers: Sequence[CompositionLayer], *, duration: float) -> None:
    for layer in layers:
        if layer.media_type not in VISUAL_MEDIA_TYPES:
            raise ValueError("layers[] may only contain image, video, or text media")
        _validate_timing_within_duration(layer, duration=duration)


def _validate_audio_layers(layers: Sequence[CompositionLayer], *, duration: float) -> None:
    for layer in layers:
        if layer.media_type not in AUDIO_MEDIA_TYPES:
            raise ValueError("audio_layers[] may only contain audio media")
        _validate_timing_within_duration(layer, duration=duration)


def _validate_timing_within_duration(layer: CompositionLayer, *, duration: float) -> None:
    if layer.end_time > duration:
        raise ValueError(f"layer {layer.layer_id!r} exceeds manifest duration")


def _validate_z_order(background: CompositionLayer, layers: Sequence[CompositionLayer]) -> None:
    z_values = [layer.z_index for layer in layers]
    if z_values != sorted(z_values):
        raise ValueError("layers[] must be sorted by ascending z_index")
    if len(set(z_values)) != len(z_values):
        raise ValueError("layers[] z_index values must be unique")
    if layers and background.z_index >= min(z_values):
        raise ValueError("background_layer z_index must be lower than visual layers")


def _validate_layer_ids(layers: Sequence[CompositionLayer]) -> None:
    ids = [layer.layer_id for layer in layers]
    if len(set(ids)) != len(ids):
        raise ValueError("layer_id values must be unique within a manifest")


__all__ = [
    "AUDIO_ASSET_KINDS",
    "AUDIO_MEDIA_TYPES",
    "BACKGROUND_MEDIA_TYPES",
    "BlendMode",
    "CompositionAnimation",
    "CompositionCrop",
    "CompositionExportPreset",
    "CompositionLayer",
    "CompositionManifest",
    "LayerHarmonisationPass",
    "MaskMode",
    "MediaType",
    "MotionTransform",
    "MotionPreset",
    "SafeAreaConstraints",
    "TEXT_ASSET_KINDS",
    "VISUAL_MEDIA_TYPES",
    "VisualMediaType",
]
