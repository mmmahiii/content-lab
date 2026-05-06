"""Typed asset-resolution contracts shared across resolver and API layers."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from math import gcd
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

PHASE1_GENERATION_TASK_TYPE = "asset.generate"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class AssetKind(StrEnum):
    """Component-aware asset roles managed by the Asset Registry."""

    BACKGROUND_IMAGE = "background_image"
    BACKGROUND_VIDEO = "background_video"
    OBJECT_IMAGE = "object_image"
    OBJECT_VIDEO = "object_video"
    SUBJECT_IMAGE = "subject_image"
    SUBJECT_VIDEO = "subject_video"
    PROP_IMAGE = "prop_image"
    PROP_VIDEO = "prop_video"
    FOREGROUND_LAYER_IMAGE = "foreground_layer_image"
    FOREGROUND_LAYER_VIDEO = "foreground_layer_video"
    TRANSPARENT_CUTOUT_PNG = "transparent_cutout_png"
    MASKED_IMAGE = "masked_image"
    EFFECT_IMAGE = "effect_image"
    EFFECT_VIDEO = "effect_video"
    TRANSITION_LAYER = "transition_layer"
    GENERATED_CLIP = "generated_clip"
    SOURCE_CLIP = "source_clip"
    FINAL_RENDER = "final_render"
    COVER_IMAGE = "cover_image"
    HOOK_TEXT = "hook_text"
    OVERLAY_PLAN = "overlay_plan"
    SUBTITLE_PLAN = "subtitle_plan"
    CAPTION_TEXT = "caption_text"
    DESIGN_TEMPLATE = "design_template"
    AUDIO_TRACK = "audio_track"
    SOUND_EFFECT = "sound_effect"
    VOICEOVER = "voiceover"
    TRIMMED_AUDIO = "trimmed_audio"
    PACKAGE_ARTIFACT = "package_artifact"
    PROVENANCE_ARTIFACT = "provenance_artifact"
    POSTING_PLAN_ARTIFACT = "posting_plan_artifact"


class MediaType(StrEnum):
    """File/data format category for an asset."""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    TEXT = "text"
    JSON = "json"
    PACKAGE = "package"
    UNKNOWN = "unknown"


class AssetSource(StrEnum):
    """Origin category for an asset."""

    UPLOADED = "uploaded"
    GENERATED = "generated"
    IMPORTED = "imported"
    OBSERVED_REFERENCE = "observed_reference"
    DERIVED = "derived"
    MANUAL_TEMPLATE = "manual_template"
    PACKAGE_OUTPUT = "package_output"


class AssetSourceType(StrEnum):
    """Fine-grained provenance for assets (CAR-5A-002).

    Complements :class:`AssetSource` (API / registry transport) with a stable
    vocabulary for provenance, QA, and acquisition policy.
    """

    GENERATED = "generated"
    OPERATOR_UPLOADED = "operator_uploaded"
    APPROVED_EXTERNAL_SOURCE = "approved_external_source"
    EXISTING_REGISTRY_ASSET = "existing_registry_asset"
    DERIVED_FROM_EXISTING = "derived_from_existing"
    PACKAGE_OUTPUT = "package_output"
    UNKNOWN = "unknown"


class AssetSourceMetadata(BaseModel):
    """Structured source / licence / import metadata for registry assets."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source_type: AssetSourceType = AssetSourceType.UNKNOWN
    source_provider: str | None = Field(default=None, max_length=128)
    external_source_url: str | None = Field(default=None, max_length=2048)
    source_reference_id: str | None = Field(default=None, max_length=256)
    licence_type: str | None = Field(default=None, max_length=128)
    licence_notes: str | None = Field(default=None, max_length=4000)
    usage_allowed: bool | None = None
    commercial_use_allowed: bool | None = None
    attribution_required: bool | None = None
    attribution_text: str | None = Field(default=None, max_length=4000)
    imported_by: str | None = Field(default=None, max_length=256)
    imported_at: datetime | None = None
    original_content_hash: str | None = Field(default=None, max_length=128)
    stored_asset_id: uuid.UUID | None = None
    source_quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    source_risk_notes: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _validate_usage_and_attribution(self) -> AssetSourceMetadata:
        if self.usage_allowed is False and self.commercial_use_allowed is True:
            raise ValueError("commercial_use_allowed cannot be true when usage_allowed is false")
        if self.attribution_required is True:
            text = (self.attribution_text or "").strip()
            if not text:
                raise ValueError("attribution_text is required when attribution_required is true")
        if self.usage_allowed is None and self.commercial_use_allowed is True:
            raise ValueError("commercial_use_allowed requires explicit usage_allowed")
        return self


def infer_asset_source_type_from_asset_source(asset_source: AssetSource | str) -> AssetSourceType:
    """Map legacy :class:`AssetSource` values to :class:`AssetSourceType` for provenance."""

    normalized = AssetSource(asset_source)
    return {
        AssetSource.GENERATED: AssetSourceType.GENERATED,
        AssetSource.UPLOADED: AssetSourceType.OPERATOR_UPLOADED,
        AssetSource.IMPORTED: AssetSourceType.APPROVED_EXTERNAL_SOURCE,
        AssetSource.OBSERVED_REFERENCE: AssetSourceType.UNKNOWN,
        AssetSource.DERIVED: AssetSourceType.DERIVED_FROM_EXISTING,
        AssetSource.MANUAL_TEMPLATE: AssetSourceType.OPERATOR_UPLOADED,
        AssetSource.PACKAGE_OUTPUT: AssetSourceType.PACKAGE_OUTPUT,
    }.get(normalized, AssetSourceType.UNKNOWN)


class AlphaMode(StrEnum):
    """How transparency or masking should be interpreted for layerable assets."""

    NONE = "none"
    ALPHA = "alpha"
    MASK = "mask"
    CHROMA_KEY = "chroma_key"
    UNKNOWN = "unknown"


class AssetRegion(BaseModel):
    """Normalized rectangle metadata for subject bounds and safe crop areas."""

    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)


class AssetTransparencyMetadata(BaseModel):
    """Transparency metadata for PNG cut-outs, masks, and future chroma-key flows."""

    model_config = ConfigDict(extra="forbid")

    alpha_mode: AlphaMode = AlphaMode.UNKNOWN
    has_transparency: bool = False
    mask_uri: str | None = None
    subject_bbox: AssetRegion | None = None
    safe_crop: AssetRegion | None = None

    @model_validator(mode="after")
    def _validate_transparency_state(self) -> AssetTransparencyMetadata:
        if self.alpha_mode is AlphaMode.NONE and self.has_transparency:
            raise ValueError("alpha_mode='none' cannot have transparency")
        if self.alpha_mode is AlphaMode.MASK and self.mask_uri is None:
            raise ValueError("mask_uri is required when alpha_mode='mask'")
        return self


class AssetVisualMetadata(BaseModel):
    """Visual metadata used to filter and combine assets for realistic compositions."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    duration_seconds: float | None = Field(
        default=None,
        gt=0,
        validation_alias=AliasChoices("duration_seconds", "duration"),
    )
    fps: float | None = Field(default=None, gt=0)
    aspect_ratio: str | None = None
    shot_type: str | None = Field(default=None, max_length=64)
    camera_angle: str | None = Field(default=None, max_length=64)
    perspective: str | None = Field(default=None, max_length=64)
    lighting: str | None = Field(default=None, max_length=128)
    colour_temperature: str | None = Field(default=None, max_length=64)
    visual_style: str | None = Field(default=None, max_length=128)
    motion_type: str | None = Field(default=None, max_length=64)
    loopable: bool | None = None
    foreground_safe: bool | None = None
    background_safe: bool | None = None

    @field_validator(
        "aspect_ratio",
        "shot_type",
        "camera_angle",
        "perspective",
        "lighting",
        "colour_temperature",
        "visual_style",
        "motion_type",
        mode="before",
    )
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(str(value).strip().split())
        return normalized or None

    @field_validator("aspect_ratio")
    @classmethod
    def _normalize_aspect_ratio(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.lower().replace(" ", "").replace("x", ":").replace("/", ":")

    @model_validator(mode="after")
    def _fill_derived_visual_metadata(self) -> AssetVisualMetadata:
        if self.aspect_ratio is None and self.width is not None and self.height is not None:
            self.aspect_ratio = aspect_ratio_from_dimensions(self.width, self.height)
        return self


_ASSET_KIND_MEDIA_TYPES: dict[AssetKind, frozenset[MediaType]] = {
    AssetKind.BACKGROUND_IMAGE: frozenset({MediaType.IMAGE}),
    AssetKind.BACKGROUND_VIDEO: frozenset({MediaType.VIDEO}),
    AssetKind.OBJECT_IMAGE: frozenset({MediaType.IMAGE}),
    AssetKind.OBJECT_VIDEO: frozenset({MediaType.VIDEO}),
    AssetKind.SUBJECT_IMAGE: frozenset({MediaType.IMAGE}),
    AssetKind.SUBJECT_VIDEO: frozenset({MediaType.VIDEO}),
    AssetKind.PROP_IMAGE: frozenset({MediaType.IMAGE}),
    AssetKind.PROP_VIDEO: frozenset({MediaType.VIDEO}),
    AssetKind.FOREGROUND_LAYER_IMAGE: frozenset({MediaType.IMAGE}),
    AssetKind.FOREGROUND_LAYER_VIDEO: frozenset({MediaType.VIDEO}),
    AssetKind.TRANSPARENT_CUTOUT_PNG: frozenset({MediaType.IMAGE}),
    AssetKind.MASKED_IMAGE: frozenset({MediaType.IMAGE}),
    AssetKind.EFFECT_IMAGE: frozenset({MediaType.IMAGE}),
    AssetKind.EFFECT_VIDEO: frozenset({MediaType.VIDEO}),
    AssetKind.TRANSITION_LAYER: frozenset({MediaType.VIDEO}),
    AssetKind.GENERATED_CLIP: frozenset({MediaType.VIDEO}),
    AssetKind.SOURCE_CLIP: frozenset({MediaType.VIDEO}),
    AssetKind.FINAL_RENDER: frozenset({MediaType.VIDEO}),
    AssetKind.COVER_IMAGE: frozenset({MediaType.IMAGE}),
    AssetKind.HOOK_TEXT: frozenset({MediaType.TEXT}),
    AssetKind.OVERLAY_PLAN: frozenset({MediaType.JSON, MediaType.TEXT}),
    AssetKind.SUBTITLE_PLAN: frozenset({MediaType.JSON, MediaType.TEXT}),
    AssetKind.CAPTION_TEXT: frozenset({MediaType.TEXT}),
    AssetKind.DESIGN_TEMPLATE: frozenset({MediaType.JSON, MediaType.PACKAGE}),
    AssetKind.AUDIO_TRACK: frozenset({MediaType.AUDIO}),
    AssetKind.SOUND_EFFECT: frozenset({MediaType.AUDIO}),
    AssetKind.VOICEOVER: frozenset({MediaType.AUDIO}),
    AssetKind.TRIMMED_AUDIO: frozenset({MediaType.AUDIO}),
    AssetKind.PACKAGE_ARTIFACT: frozenset({MediaType.PACKAGE, MediaType.JSON}),
    AssetKind.PROVENANCE_ARTIFACT: frozenset({MediaType.JSON}),
    AssetKind.POSTING_PLAN_ARTIFACT: frozenset({MediaType.JSON}),
}


def compatible_media_types_for_asset_kind(
    asset_kind: AssetKind | str,
) -> frozenset[MediaType]:
    """Return explicit media types compatible with an asset role."""

    return _ASSET_KIND_MEDIA_TYPES[AssetKind(asset_kind)]


def infer_media_type_for_asset_kind(asset_kind: AssetKind | str) -> MediaType:
    """Return the default media type for an asset role."""

    compatible = compatible_media_types_for_asset_kind(asset_kind)
    if len(compatible) == 1:
        return next(iter(compatible))
    if MediaType.JSON in compatible:
        return MediaType.JSON
    return next(iter(compatible))


def validate_asset_kind_media_type(
    *,
    asset_kind: AssetKind | str,
    media_type: MediaType | str,
) -> MediaType:
    """Validate and normalize a media type for an asset role."""

    normalized_media_type = MediaType(media_type)
    if normalized_media_type is MediaType.UNKNOWN:
        return normalized_media_type
    compatible = compatible_media_types_for_asset_kind(asset_kind)
    if normalized_media_type not in compatible:
        expected = ", ".join(sorted(media.value for media in compatible))
        raise ValueError(
            f"media_type='{normalized_media_type.value}' is not compatible with "
            f"asset_kind='{AssetKind(asset_kind).value}'; expected one of: {expected}"
        )
    return normalized_media_type


def aspect_ratio_from_dimensions(width: int, height: int) -> str:
    """Return a reduced width:height aspect-ratio string."""

    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    divisor = gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def _read_png_header(data: bytes) -> tuple[int, int, int] | None:
    if not data.startswith(_PNG_SIGNATURE):
        return None
    offset = len(_PNG_SIGNATURE)
    while offset + 8 <= len(data):
        chunk_length = int.from_bytes(data[offset : offset + 4], byteorder="big")
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data_start = offset + 8
        chunk_data_end = chunk_data_start + chunk_length
        if chunk_data_end > len(data):
            return None
        chunk_data = data[chunk_data_start:chunk_data_end]
        if chunk_type == b"IHDR" and len(chunk_data) >= 10:
            width = int.from_bytes(chunk_data[0:4], byteorder="big")
            height = int.from_bytes(chunk_data[4:8], byteorder="big")
            color_type = chunk_data[9]
            if width <= 0 or height <= 0:
                return None
            return width, height, color_type
        if chunk_type == b"IEND":
            return None
        offset = chunk_data_end + 4
    return None


def detect_png_transparency(data: bytes) -> AssetTransparencyMetadata:
    """Inspect PNG bytes for alpha-channel or tRNS transparency metadata.

    This intentionally avoids heavyweight image dependencies; it only reads PNG
    chunk headers and enough IHDR/tRNS data to classify transparency.
    """

    header = _read_png_header(data)
    if header is None:
        return AssetTransparencyMetadata(alpha_mode=AlphaMode.UNKNOWN, has_transparency=False)

    offset = len(_PNG_SIGNATURE)
    _, _, color_type = header
    has_transparency = False
    while offset + 8 <= len(data):
        chunk_length = int.from_bytes(data[offset : offset + 4], byteorder="big")
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data_start = offset + 8
        chunk_data_end = chunk_data_start + chunk_length
        if chunk_data_end > len(data):
            break

        if chunk_type == b"IHDR":
            has_transparency = color_type in {4, 6}
        elif chunk_type == b"tRNS":
            has_transparency = True
        elif chunk_type == b"IEND":
            break

        offset = chunk_data_end + 4

    if has_transparency:
        return AssetTransparencyMetadata(alpha_mode=AlphaMode.ALPHA, has_transparency=True)
    return AssetTransparencyMetadata(alpha_mode=AlphaMode.NONE, has_transparency=False)


def detect_png_visual_metadata(data: bytes) -> AssetVisualMetadata | None:
    """Return dimensions/aspect ratio for PNG bytes when the header can be parsed."""

    header = _read_png_header(data)
    if header is None:
        return None
    width, height, _ = header
    return AssetVisualMetadata(width=width, height=height)


class GenerationIntent(BaseModel):
    """Persistable intent envelope for later provider submission."""

    model_config = ConfigDict(extra="forbid")

    asset_id: uuid.UUID
    asset_status: str
    storage_uri: str
    task_id: uuid.UUID | None = None
    task_type: str = PHASE1_GENERATION_TASK_TYPE
    task_status: str | None = None
    idempotency_key: str
    asset_class: str
    asset_kind: AssetKind = AssetKind.GENERATED_CLIP
    media_type: MediaType = MediaType.VIDEO
    asset_source: AssetSource = AssetSource.GENERATED
    provider: str
    model: str
    asset_key: str
    asset_key_hash: str
    payload: dict[str, Any] = Field(default_factory=dict)


class AssetPromptTrace(BaseModel):
    """Trace metadata for provider prompts stored beside generation requests."""

    model_config = ConfigDict(extra="forbid")

    compiler_name: str = Field(min_length=1, max_length=80)
    prompt_kind: str = Field(min_length=1, max_length=80)
    source_hash: str = Field(min_length=64, max_length=64)
    prompt_hash: str = Field(min_length=64, max_length=64)
    scene_ids: list[str] = Field(default_factory=list)
    final_prompt_chars: int = Field(ge=1)
    negative_prompt: str = Field(min_length=1, max_length=500)
    payload: dict[str, Any] = Field(default_factory=dict)


class DecisionPolicyMetadata(BaseModel):
    """Stable policy envelope reserved for later reuse enforcement and QA."""

    model_config = ConfigDict(extra="forbid")

    family_id: str | None = None
    family_reuse_count: int | None = Field(default=None, ge=0)
    family_reuse_cap: int | None = Field(default=None, ge=1)
    cooldown_seconds: int | None = Field(default=None, ge=1)
    last_reused_at: datetime | None = None
    active_rules: list[str] = Field(default_factory=list)


class AssetResolutionDecisionBase(BaseModel):
    """Shared fields returned by the asset resolver."""

    model_config = ConfigDict(extra="forbid")

    decision: str
    asset_key: str
    asset_key_hash: str
    asset_class: str
    asset_kind: AssetKind = AssetKind.GENERATED_CLIP
    media_type: MediaType = MediaType.VIDEO
    asset_source: AssetSource = AssetSource.GENERATED
    provider: str
    model: str
    canonical_params: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    policy: DecisionPolicyMetadata = Field(default_factory=DecisionPolicyMetadata)


class ReuseExactDecision(AssetResolutionDecisionBase):
    """Resolve to an already-registered asset with an identical AssetKey."""

    decision: Literal["reuse_exact"] = "reuse_exact"
    asset_id: uuid.UUID
    storage_uri: str


class GenerateDecision(AssetResolutionDecisionBase):
    """Resolve to a fresh generation-intent task."""

    decision: Literal["generate"] = "generate"
    generation_intent: GenerationIntent


class ReuseWithTransformDecision(AssetResolutionDecisionBase):
    """Resolve to a deterministic mutation of an existing asset."""

    decision: Literal["reuse_with_transform"] = "reuse_with_transform"
    asset_id: uuid.UUID
    storage_uri: str | None = None
    reason: str
    reason_code: str
    transform_recipe: dict[str, Any] = Field(default_factory=dict)


class BlockedDecision(AssetResolutionDecisionBase):
    """Resolve to a policy or safety block."""

    decision: Literal["blocked"] = "blocked"
    reason: str
    reason_code: str
    retry_after_seconds: int | None = Field(default=None, ge=1)


AssetResolutionDecision = (
    ReuseExactDecision | GenerateDecision | ReuseWithTransformDecision | BlockedDecision
)


__all__ = [
    "AlphaMode",
    "AssetKind",
    "AssetRegion",
    "AssetResolutionDecision",
    "AssetResolutionDecisionBase",
    "AssetPromptTrace",
    "AssetSource",
    "AssetSourceMetadata",
    "AssetSourceType",
    "AssetTransparencyMetadata",
    "AssetVisualMetadata",
    "BlockedDecision",
    "DecisionPolicyMetadata",
    "GenerateDecision",
    "GenerationIntent",
    "MediaType",
    "PHASE1_GENERATION_TASK_TYPE",
    "ReuseExactDecision",
    "ReuseWithTransformDecision",
    "aspect_ratio_from_dimensions",
    "compatible_media_types_for_asset_kind",
    "detect_png_transparency",
    "detect_png_visual_metadata",
    "infer_asset_source_type_from_asset_source",
    "infer_media_type_for_asset_kind",
    "validate_asset_kind_media_type",
]
