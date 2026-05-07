"""Pre-render realism checks for layered composition manifests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from content_lab_editing.composition_manifest import CompositionLayer, CompositionManifest
from content_lab_editing.motion_transforms import (
    layer_has_motion,
    motion_preset_for_layer,
    motion_spec_for_layer,
)

RealismSeverity = Literal["warn", "fail"]

_FOREGROUND_KINDS = frozenset(
    {
        "foreground_layer_image",
        "foreground_layer_video",
        "transparent_cutout_png",
        "masked_image",
        "object_image",
        "object_video",
        "subject_image",
        "subject_video",
        "prop_image",
        "prop_video",
    }
)


@dataclass(frozen=True, slots=True)
class CompositionRealismFinding:
    """One realism issue detected before rendering/package readiness."""

    code: str
    severity: RealismSeverity
    message: str
    layer_id: str | None
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "layer_id": self.layer_id,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class CompositionRealismReport:
    """Realism validation report that package readiness can inspect."""

    findings: tuple[CompositionRealismFinding, ...]

    @property
    def has_failures(self) -> bool:
        return any(finding.severity == "fail" for finding in self.findings)

    @property
    def passed(self) -> bool:
        return not self.has_failures

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "composition_realism_v1",
            "passed": self.passed,
            "findings": [finding.as_dict() for finding in self.findings],
            "failure_codes": [
                finding.code for finding in self.findings if finding.severity == "fail"
            ],
            "warning_codes": [
                finding.code for finding in self.findings if finding.severity == "warn"
            ],
        }


def validate_composition_realism(
    manifest: CompositionManifest,
    *,
    asset_metadata: Mapping[str, Mapping[str, Any]] | None = None,
) -> CompositionRealismReport:
    """Return fail/warn findings for fake-looking layered outputs."""

    metadata = asset_metadata or {}
    findings: list[CompositionRealismFinding] = []
    foreground_layers = [_layer for _layer in manifest.layers if _is_foreground_layer(_layer)]
    text_layers = [_layer for _layer in manifest.layers if _layer.media_type == "text"]

    _check_background_presence(manifest, findings=findings)
    _check_layer_count(manifest, findings=findings)
    for layer in foreground_layers:
        _check_foreground_size(manifest, layer, findings=findings)
        _check_layer_bounds(manifest, layer, findings=findings)
        _check_unintentional_clipping(manifest, layer, findings=findings)
        _check_safe_area(manifest, layer, findings=findings)
        _check_static_motion(layer, findings=findings)
        _check_alpha_edges(layer, metadata=metadata.get(layer.asset_id, {}), findings=findings)
        _check_layer_duration(layer, findings=findings)

    for layer in text_layers:
        _check_text_readability(manifest, layer, findings=findings)
        _check_layer_bounds(manifest, layer, findings=findings)
        _check_safe_area(manifest, layer, findings=findings)
        _check_layer_duration(layer, findings=findings)

    _check_text_object_overlap(
        manifest,
        text_layers=text_layers,
        foreground_layers=foreground_layers,
        findings=findings,
    )
    _check_style_compatibility(
        manifest,
        foreground_layers=foreground_layers,
        metadata=metadata,
        findings=findings,
    )
    return CompositionRealismReport(findings=tuple(findings))


def _check_background_presence(
    manifest: CompositionManifest,
    *,
    findings: list[CompositionRealismFinding],
) -> None:
    background = manifest.background_layer
    if background is None or background.media_type not in {"image", "video"}:
        findings.append(
            _finding(
                "background_missing",
                "fail",
                "Composition is missing an image or video background layer.",
                None,
            )
        )
        return
    if background.opacity <= 0:
        findings.append(
            _finding(
                "background_invisible",
                "fail",
                "Background layer is fully transparent.",
                background,
            )
        )


def _check_layer_count(
    manifest: CompositionManifest,
    *,
    findings: list[CompositionRealismFinding],
) -> None:
    visual_layer_count = len(manifest.layers) + 1
    active_text_layers = sum(1 for layer in manifest.layers if layer.media_type == "text")
    if visual_layer_count > 9:
        findings.append(
            _finding(
                "too_many_visual_layers",
                "warn",
                "Composition has enough visual layers to risk cluttering the frame.",
                None,
                visual_layer_count=visual_layer_count,
            )
        )
    if active_text_layers > 3:
        findings.append(
            _finding(
                "too_many_text_layers",
                "warn",
                "Composition has many text layers competing for attention.",
                None,
                text_layer_count=active_text_layers,
            )
        )


def _check_text_readability(
    manifest: CompositionManifest,
    layer: CompositionLayer,
    *,
    findings: list[CompositionRealismFinding],
) -> None:
    height = float(layer.height or 0)
    minimum_height = max(32.0, manifest.canvas_height * 0.025)
    if height <= 0:
        findings.append(
            _finding(
                "text_missing_dimensions",
                "warn",
                "Text layer dimensions are missing, so readability cannot be verified.",
                layer,
            )
        )
        return
    if height < minimum_height:
        findings.append(
            _finding(
                "text_too_small",
                "warn",
                "Text layer may be too small to read on a vertical reel.",
                layer,
                height=height,
                minimum_height=minimum_height,
            )
        )


def _check_unintentional_clipping(
    manifest: CompositionManifest,
    layer: CompositionLayer,
    *,
    findings: list[CompositionRealismFinding],
) -> None:
    if _allows_clipping(layer):
        return
    x, y, width, height = _estimated_layer_box(manifest, layer)
    clipped_width = max(0.0, -x) + max(0.0, x + width - manifest.canvas_width)
    clipped_height = max(0.0, -y) + max(0.0, y + height - manifest.canvas_height)
    clipped_area_estimate = min(width, clipped_width) * height + min(height, clipped_height) * width
    layer_area = width * height
    if layer_area <= 0:
        return
    clipped_ratio = min(1.0, clipped_area_estimate / layer_area)
    if clipped_ratio > 0.02:
        findings.append(
            _finding(
                "object_clipped_unintentionally",
                "warn",
                "Foreground object appears clipped without an intentional crop or mask.",
                layer,
                clipped_ratio=clipped_ratio,
            )
        )


def _check_foreground_size(
    manifest: CompositionManifest,
    layer: CompositionLayer,
    *,
    findings: list[CompositionRealismFinding],
) -> None:
    box = _layer_box(layer)
    if box is None:
        findings.append(
            _finding(
                "foreground_missing_dimensions",
                "warn",
                "Foreground object dimensions are missing, so size realism cannot be verified.",
                layer,
            )
        )
        return

    _, _, width, height = box
    area_ratio = (width * height) / (manifest.canvas_width * manifest.canvas_height)
    if area_ratio > 0.85:
        findings.append(
            _finding(
                "foreground_too_large",
                "fail",
                "Foreground object covers too much of the frame.",
                layer,
                area_ratio=area_ratio,
            )
        )
    elif area_ratio > 0.65:
        findings.append(
            _finding(
                "foreground_large",
                "warn",
                "Foreground object is large enough to look pasted unless intentionally framed.",
                layer,
                area_ratio=area_ratio,
            )
        )

    if area_ratio < 0.01:
        findings.append(
            _finding(
                "foreground_too_small",
                "fail",
                "Foreground object is too small to read as intentional.",
                layer,
                area_ratio=area_ratio,
            )
        )
    elif area_ratio < 0.035:
        findings.append(
            _finding(
                "foreground_small",
                "warn",
                "Foreground object may be too small to feel deliberate.",
                layer,
                area_ratio=area_ratio,
            )
        )


def _check_layer_bounds(
    manifest: CompositionManifest,
    layer: CompositionLayer,
    *,
    findings: list[CompositionRealismFinding],
) -> None:
    box = _estimated_layer_box(manifest, layer)
    x, y, width, height = box
    if x < 0 or y < 0 or x + width > manifest.canvas_width or y + height > manifest.canvas_height:
        findings.append(
            _finding(
                "layer_out_of_frame",
                "fail",
                "Layer placement extends outside the render canvas.",
                layer,
                box=box,
                canvas=(manifest.canvas_width, manifest.canvas_height),
            )
        )


def _check_safe_area(
    manifest: CompositionManifest,
    layer: CompositionLayer,
    *,
    findings: list[CompositionRealismFinding],
) -> None:
    constraints = layer.safe_area_constraints
    if constraints is None or not constraints.enforce:
        return
    x, y, width, height = _estimated_layer_box(manifest, layer)
    left = constraints.left
    top = constraints.top
    right = manifest.canvas_width - constraints.right
    bottom = manifest.canvas_height - constraints.bottom
    if x < left or y < top or x + width > right or y + height > bottom:
        findings.append(
            _finding(
                "safe_area_violation",
                "fail",
                "Layer violates its safe-area constraints.",
                layer,
                box=(x, y, width, height),
                safe_area=(left, top, right, bottom),
            )
        )


def _check_static_motion(
    layer: CompositionLayer,
    *,
    findings: list[CompositionRealismFinding],
) -> None:
    if layer.media_type == "image" and layer.duration > 1.0 and not layer_has_motion(layer):
        findings.append(
            _finding(
                "static_asset_without_motion",
                "warn",
                "Static image layer is held long enough to benefit from a motion transform.",
                layer,
                duration=layer.duration,
            )
        )
    if motion_preset_for_layer(layer) == "shake_light" and layer.duration > 2.5:
        findings.append(
            _finding(
                "awkward_motion_duration",
                "warn",
                "Light shake is usually best as a short accent, not a long continuous motion.",
                layer,
                duration=layer.duration,
            )
        )


def _check_layer_duration(
    layer: CompositionLayer,
    *,
    findings: list[CompositionRealismFinding],
) -> None:
    if layer.duration < 0.35:
        findings.append(
            _finding(
                "layer_duration_too_short",
                "fail",
                "Layer duration is too short to read cleanly.",
                layer,
                duration=layer.duration,
            )
        )


def _check_alpha_edges(
    layer: CompositionLayer,
    *,
    metadata: Mapping[str, Any],
    findings: list[CompositionRealismFinding],
) -> None:
    if not _is_alpha_like_layer(layer):
        return
    if layer.mask_mode == "none":
        findings.append(
            _finding(
                "alpha_layer_without_mask_mode",
                "warn",
                "Layer looks like a cutout but does not declare alpha/mask handling.",
                layer,
            )
        )
    has_alpha = _first_optional_bool(
        metadata.get("has_alpha"),
        metadata.get("alpha_channel_present"),
        metadata.get("transparency_present"),
    )
    transparency = metadata.get("transparency")
    if has_alpha is None and isinstance(transparency, Mapping):
        has_alpha = _first_optional_bool(
            transparency.get("has_alpha"),
            transparency.get("alpha_channel_present"),
        )
    if has_alpha is False:
        findings.append(
            _finding(
                "expected_transparency_missing",
                "fail",
                "Layer expects transparency, but asset metadata reports no alpha channel.",
                layer,
            )
        )
    edge_score = _edge_quality_score(metadata)
    if edge_score is None:
        return
    if edge_score < 0.45:
        findings.append(
            _finding(
                "alpha_edges_low_quality",
                "fail",
                "Alpha or matte edge quality is low enough to risk a pasted-object look.",
                layer,
                edge_quality_score=edge_score,
            )
        )
    elif edge_score < 0.7:
        findings.append(
            _finding(
                "alpha_edges_need_review",
                "warn",
                "Alpha or matte edges may need review before package readiness.",
                layer,
                edge_quality_score=edge_score,
            )
        )


def _check_text_object_overlap(
    manifest: CompositionManifest,
    *,
    text_layers: Sequence[CompositionLayer],
    foreground_layers: Sequence[CompositionLayer],
    findings: list[CompositionRealismFinding],
) -> None:
    for text_layer in text_layers:
        text_box = _estimated_layer_box(manifest, text_layer)
        for object_layer in foreground_layers:
            object_box = _estimated_layer_box(manifest, object_layer)
            overlap = _overlap_area(text_box, object_box)
            object_area = object_box[2] * object_box[3]
            if object_area <= 0:
                continue
            ratio = overlap / object_area
            if ratio > 0.22:
                findings.append(
                    _finding(
                        "text_covers_critical_object_area",
                        "fail",
                        "Text overlaps too much of a foreground object.",
                        text_layer,
                        object_layer_id=object_layer.layer_id,
                        overlap_ratio=ratio,
                    )
                )
            elif ratio > 0.08:
                findings.append(
                    _finding(
                        "text_near_object_area",
                        "warn",
                        "Text is close enough to the object to deserve layout review.",
                        text_layer,
                        object_layer_id=object_layer.layer_id,
                        overlap_ratio=ratio,
                    )
                )


def _check_style_compatibility(
    manifest: CompositionManifest,
    *,
    foreground_layers: Sequence[CompositionLayer],
    metadata: Mapping[str, Mapping[str, Any]],
    findings: list[CompositionRealismFinding],
) -> None:
    background_styles = _style_tags(metadata.get(manifest.background_layer.asset_id, {}))
    if not background_styles:
        return
    for layer in foreground_layers:
        styles = _style_tags(metadata.get(layer.asset_id, {}))
        if styles and not background_styles.intersection(styles):
            findings.append(
                _finding(
                    "background_object_style_mismatch",
                    "warn",
                    "Foreground and background style tags do not overlap.",
                    layer,
                    background_styles=sorted(background_styles),
                    object_styles=sorted(styles),
                )
            )


def _is_foreground_layer(layer: CompositionLayer) -> bool:
    return layer.media_type in {"image", "video"} and layer.asset_kind in _FOREGROUND_KINDS


def _is_alpha_like_layer(layer: CompositionLayer) -> bool:
    return layer.mask_mode in {"alpha", "luma", "chroma_key"} or layer.asset_kind in {
        "transparent_cutout_png",
        "masked_image",
        "foreground_layer_image",
        "foreground_layer_video",
    }


def _allows_clipping(layer: CompositionLayer) -> bool:
    metadata = layer.motion_transform.params if layer.motion_transform is not None else {}
    return (
        layer.crop is not None
        or layer.mask_mode in {"luma", "chroma_key"}
        or bool(metadata.get("intentional_clipping"))
        or bool(metadata.get("allow_clipping"))
    )


def _layer_box(layer: CompositionLayer) -> tuple[float, float, float, float] | None:
    if layer.width is None or layer.height is None:
        return None
    spec = motion_spec_for_layer(layer)
    max_scale = max(spec.scale_from, spec.scale_to) * layer.scale
    return (
        float(layer.x),
        float(layer.y),
        float(layer.width) * max_scale,
        float(layer.height) * max_scale,
    )


def _estimated_layer_box(
    manifest: CompositionManifest,
    layer: CompositionLayer,
) -> tuple[float, float, float, float]:
    box = _layer_box(layer)
    if box is not None:
        return box
    if layer.media_type == "text":
        width = float(layer.width or max(1, manifest.canvas_width - (layer.x * 2)))
        height = float(layer.height or 96)
        return (float(layer.x), float(layer.y), width, height)
    return (
        float(layer.x),
        float(layer.y),
        float(manifest.canvas_width),
        float(manifest.canvas_height),
    )


def _overlap_area(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    left_x, left_y, left_w, left_h = left
    right_x, right_y, right_w, right_h = right
    overlap_w = max(0.0, min(left_x + left_w, right_x + right_w) - max(left_x, right_x))
    overlap_h = max(0.0, min(left_y + left_h, right_y + right_h) - max(left_y, right_y))
    return overlap_w * overlap_h


def _style_tags(metadata: Mapping[str, Any]) -> set[str]:
    values: list[Any] = []
    for key in ("style_tags", "visual_style", "styles"):
        values.extend(_as_list(metadata.get(key)))
    compatibility = metadata.get("compatibility")
    if isinstance(compatibility, Mapping):
        values.extend(_as_list(compatibility.get("visual_style")))
    return {_normalize_tag(value) for value in values if _normalize_tag(value)}


def _edge_quality_score(metadata: Mapping[str, Any]) -> float | None:
    for key in ("alpha_edge_score", "edge_quality_score", "matte_quality_score"):
        score = _as_float(metadata.get(key))
        if score is not None:
            return score
    transparency = metadata.get("transparency")
    if isinstance(transparency, Mapping):
        return _as_float(transparency.get("edge_quality_score"))
    return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return list(value)
    return [value]


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None


def _first_optional_bool(*values: Any) -> bool | None:
    for value in values:
        parsed = _optional_bool(value)
        if parsed is not None:
            return parsed
    return None


def _normalize_tag(value: Any) -> str:
    return "_".join(str(value).strip().lower().replace("-", "_").split())


def _finding(
    code: str,
    severity: RealismSeverity,
    message: str,
    layer: CompositionLayer | None,
    **details: Any,
) -> CompositionRealismFinding:
    return CompositionRealismFinding(
        code=code,
        severity=severity,
        message=message,
        layer_id=None if layer is None else layer.layer_id,
        details=details,
    )


__all__ = [
    "CompositionRealismFinding",
    "CompositionRealismReport",
    "RealismSeverity",
    "validate_composition_realism",
]
