"""Motion transform presets for static layered assets."""

from __future__ import annotations

from dataclasses import dataclass

from content_lab_editing.composition_manifest import CompositionLayer, MotionPreset


@dataclass(frozen=True, slots=True)
class MotionPresetSpec:
    """Default values for one motion preset."""

    preset: MotionPreset
    scale_from: float
    scale_to: float
    translate_x: float = 0.0
    translate_y: float = 0.0
    amplitude: float = 0.0
    frequency: float = 1.0


MOTION_TRANSFORM_PRESETS: dict[MotionPreset, MotionPresetSpec] = {
    "none": MotionPresetSpec("none", scale_from=1.0, scale_to=1.0),
    "slow_zoom": MotionPresetSpec("slow_zoom", scale_from=1.0, scale_to=1.06),
    "pan_left": MotionPresetSpec("pan_left", scale_from=1.02, scale_to=1.02, amplitude=36.0),
    "pan_right": MotionPresetSpec("pan_right", scale_from=1.02, scale_to=1.02, amplitude=36.0),
    "float": MotionPresetSpec(
        "float", scale_from=1.0, scale_to=1.0, amplitude=14.0, frequency=0.55
    ),
    "scale_in": MotionPresetSpec("scale_in", scale_from=0.92, scale_to=1.0),
    "scale_out": MotionPresetSpec("scale_out", scale_from=1.0, scale_to=0.94),
    "shake_light": MotionPresetSpec(
        "shake_light",
        scale_from=1.0,
        scale_to=1.0,
        amplitude=3.0,
        frequency=7.5,
    ),
    "parallax_basic": MotionPresetSpec(
        "parallax_basic",
        scale_from=1.03,
        scale_to=1.03,
        translate_x=-24.0,
        translate_y=8.0,
    ),
}


def motion_preset_for_layer(layer: CompositionLayer) -> MotionPreset:
    """Return the selected motion preset for a layer."""

    if layer.motion_transform is None:
        return "none"
    return layer.motion_transform.preset


def motion_spec_for_layer(layer: CompositionLayer) -> MotionPresetSpec:
    """Merge layer-specific transform values onto the preset defaults."""

    transform = layer.motion_transform
    preset = motion_preset_for_layer(layer)
    defaults = MOTION_TRANSFORM_PRESETS[preset]
    if transform is None:
        return defaults
    return MotionPresetSpec(
        preset=preset,
        scale_from=transform.scale_from
        if transform.scale_from is not None
        else defaults.scale_from,
        scale_to=transform.scale_to if transform.scale_to is not None else defaults.scale_to,
        translate_x=transform.translate_x or defaults.translate_x,
        translate_y=transform.translate_y or defaults.translate_y,
        amplitude=transform.amplitude if transform.amplitude is not None else defaults.amplitude,
        frequency=transform.frequency if transform.frequency is not None else defaults.frequency,
    )


def layer_has_motion(layer: CompositionLayer) -> bool:
    """Return whether a layer has an intentional non-static transform."""

    return motion_preset_for_layer(layer) != "none"


__all__ = [
    "MOTION_TRANSFORM_PRESETS",
    "MotionPresetSpec",
    "layer_has_motion",
    "motion_preset_for_layer",
    "motion_spec_for_layer",
]
