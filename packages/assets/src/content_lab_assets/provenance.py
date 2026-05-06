"""Stable package-provenance artifact generation for audit and debugging."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from content_lab_assets.providers.base import redact_provider_data


def _clean_text(value: str, *, field_name: str, max_length: int) -> str:
    normalized = " ".join(str(value).strip().split())
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return normalized


def _clean_optional_text(
    value: str | None,
    *,
    field_name: str,
    max_length: int,
) -> str | None:
    if value is None:
        return None
    return _clean_text(value, field_name=field_name, max_length=max_length)


def _stable_json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _stable_json_value(value.model_dump(mode="json", exclude_none=True))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {
            str(key): _stable_json_value(raw_value)
            for key, raw_value in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_stable_json_value(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _optional_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


class PackageAssetProvenance(BaseModel):
    """Asset lineage entry included in the package provenance artifact."""

    model_config = ConfigDict(extra="forbid")

    role: str = Field(min_length=1, max_length=64)
    stage: str | None = Field(default=None, max_length=32)
    asset_id: str | None = Field(default=None, max_length=128)
    storage_uri: str = Field(min_length=1, max_length=2_048)
    kind: str | None = Field(default=None, max_length=64)
    source: str | None = Field(default=None, max_length=128)
    content_hash: str | None = Field(default=None, max_length=256)
    asset_key_hash: str | None = Field(default=None, max_length=256)
    asset_kind: str | None = Field(default=None, max_length=64)
    media_type: str | None = Field(default=None, max_length=64)
    source_type: str | None = Field(default=None, max_length=128)
    source_provider: str | None = Field(default=None, max_length=128)
    external_source_url: str | None = Field(default=None, max_length=2_048)
    source_reference_id: str | None = Field(default=None, max_length=256)
    licence_type: str | None = Field(default=None, max_length=128)
    usage_allowed: bool | None = None
    attribution_required: bool | None = None
    attribution_text: str | None = Field(default=None, max_length=4_000)
    original_content_hash: str | None = Field(default=None, max_length=256)
    stored_content_hash: str | None = Field(default=None, max_length=256)
    derived_from_asset_id: str | None = Field(default=None, max_length=128)
    imported_at: datetime | None = None
    generation_params: dict[str, Any] = Field(default_factory=dict)
    transform_recipe: dict[str, Any] = Field(default_factory=dict)
    transform_version: str | None = Field(default=None, max_length=64)
    used_in_reel_id: str | None = Field(default=None, max_length=128)
    used_as_component_role: str | None = Field(default=None, max_length=128)
    layer_role: str | None = Field(default=None, max_length=64)
    sequence_index: int | None = None
    z_index: int | None = None
    start_time: float | None = None
    end_time: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("role", mode="before")
    @classmethod
    def _normalize_role(cls, value: str) -> str:
        return _clean_text(value, field_name="role", max_length=64)

    @field_validator(
        "stage",
        "asset_id",
        "kind",
        "source",
        "content_hash",
        "asset_key_hash",
        "asset_kind",
        "media_type",
        "source_type",
        "source_provider",
        "external_source_url",
        "source_reference_id",
        "licence_type",
        "attribution_text",
        "original_content_hash",
        "stored_content_hash",
        "derived_from_asset_id",
        "transform_version",
        "used_in_reel_id",
        "used_as_component_role",
        "layer_role",
        mode="before",
    )
    @classmethod
    def _normalize_optional_fields(cls, value: str | None, info: Any) -> str | None:
        limits = {
            "stage": 32,
            "asset_id": 128,
            "kind": 64,
            "source": 128,
            "content_hash": 256,
            "asset_key_hash": 256,
            "asset_kind": 64,
            "media_type": 64,
            "source_type": 128,
            "source_provider": 128,
            "external_source_url": 2_048,
            "source_reference_id": 256,
            "licence_type": 128,
            "attribution_text": 4_000,
            "original_content_hash": 256,
            "stored_content_hash": 256,
            "derived_from_asset_id": 128,
            "transform_version": 64,
            "used_in_reel_id": 128,
            "used_as_component_role": 128,
            "layer_role": 64,
        }
        return _clean_optional_text(
            value,
            field_name=str(info.field_name),
            max_length=limits[str(info.field_name)],
        )

    @field_validator("storage_uri", mode="before")
    @classmethod
    def _normalize_storage_uri(cls, value: str) -> str:
        return _clean_text(value, field_name="storage_uri", max_length=2_048)

    @field_validator("metadata", mode="before")
    @classmethod
    def _sanitize_metadata(cls, value: Mapping[str, Any] | None) -> dict[str, Any]:
        return dict(_stable_json_value(redact_provider_data(value or {})))

    @field_validator("generation_params", "transform_recipe", mode="before")
    @classmethod
    def _sanitize_lineage_payloads(cls, value: Mapping[str, Any] | None) -> dict[str, Any]:
        return dict(_stable_json_value(redact_provider_data(value or {})))

    @model_validator(mode="after")
    def _backfill_source_first_fields(self) -> PackageAssetProvenance:
        source_metadata = self.metadata.get("source_metadata")
        if isinstance(source_metadata, Mapping):
            self.source_type = self.source_type or _optional_str(source_metadata.get("source_type"))
            self.source_provider = self.source_provider or _optional_str(
                source_metadata.get("source_provider")
            )
            self.external_source_url = self.external_source_url or _optional_str(
                source_metadata.get("external_source_url")
            )
            self.source_reference_id = self.source_reference_id or _optional_str(
                source_metadata.get("source_reference_id")
            )
            self.licence_type = self.licence_type or _optional_str(
                source_metadata.get("licence_type")
            )
            self.usage_allowed = (
                self.usage_allowed
                if self.usage_allowed is not None
                else _optional_bool(source_metadata.get("usage_allowed"))
            )
            self.attribution_required = (
                self.attribution_required
                if self.attribution_required is not None
                else _optional_bool(source_metadata.get("attribution_required"))
            )
            self.attribution_text = self.attribution_text or _optional_str(
                source_metadata.get("attribution_text")
            )
            self.original_content_hash = self.original_content_hash or _optional_str(
                source_metadata.get("original_content_hash")
            )
            self.imported_at = self.imported_at or _optional_datetime(
                source_metadata.get("imported_at")
            )

        self.asset_kind = self.asset_kind or _optional_str(self.metadata.get("asset_kind"))
        self.media_type = self.media_type or _optional_str(self.metadata.get("media_type"))
        self.source_type = (
            self.source_type or _optional_str(self.metadata.get("asset_source")) or self.source
        )
        self.stored_content_hash = self.stored_content_hash or self.content_hash
        self.used_as_component_role = self.used_as_component_role or self.role
        return self


class ProviderJobProvenance(BaseModel):
    """Provider execution details retained for later audit and debugging."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=80)
    model: str | None = Field(default=None, max_length=80)
    status: str = Field(min_length=1, max_length=64)
    job_id: str | None = Field(default=None, max_length=128)
    task_id: str | None = Field(default=None, max_length=128)
    external_ref: str | None = Field(default=None, max_length=256)
    asset_id: str | None = Field(default=None, max_length=128)
    submitted_at: datetime | None = None
    completed_at: datetime | None = None
    request: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider", mode="before")
    @classmethod
    def _normalize_provider(cls, value: str) -> str:
        return _clean_text(value, field_name="provider", max_length=80)

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, value: str) -> str:
        return _clean_text(value, field_name="status", max_length=64)

    @field_validator("model", "job_id", "task_id", "external_ref", "asset_id", mode="before")
    @classmethod
    def _normalize_optional_fields(cls, value: str | None, info: Any) -> str | None:
        limits = {
            "model": 80,
            "job_id": 128,
            "task_id": 128,
            "external_ref": 256,
            "asset_id": 128,
        }
        return _clean_optional_text(
            value,
            field_name=str(info.field_name),
            max_length=limits[str(info.field_name)],
        )

    @field_validator("request", "response", "metadata", mode="before")
    @classmethod
    def _sanitize_payloads(cls, value: Mapping[str, Any] | None) -> dict[str, Any]:
        return dict(_stable_json_value(redact_provider_data(value or {})))


class PackageTimestampEntry(BaseModel):
    """Named package timestamp retained in stable audit output."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=64)
    timestamp: datetime

    @field_validator("label", mode="before")
    @classmethod
    def _normalize_label(cls, value: str) -> str:
        return _clean_text(value, field_name="label", max_length=64)


class PackageProvenanceSummary(BaseModel):
    """Small summary block for quick QA and web rendering."""

    model_config = ConfigDict(extra="forbid")

    asset_count: int = Field(ge=0)
    provider_job_count: int = Field(ge=0)
    asset_roles: list[str] = Field(default_factory=list)
    provider_refs: list[str] = Field(default_factory=list)
    timestamp_labels: list[str] = Field(default_factory=list)
    provider_credentials_redacted: bool = True


class PackageArtifactProvenance(BaseModel):
    """Package artifact reference retained in provenance."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    filename: str | None = Field(default=None, max_length=256)
    storage_uri: str | None = Field(default=None, max_length=2_048)
    checksum_sha256: str | None = Field(default=None, max_length=256)
    content_type: str | None = Field(default=None, max_length=128)
    kind: str | None = Field(default=None, max_length=64)
    size_bytes: int | None = Field(default=None, ge=0)


class TransformProvenance(BaseModel):
    """Transform or layer operation used to derive the final render."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str | None = Field(default=None, max_length=128)
    layer_id: str | None = Field(default=None, max_length=128)
    role: str | None = Field(default=None, max_length=128)
    transform_recipe: dict[str, Any] = Field(default_factory=dict)
    transform_version: str | None = Field(default=None, max_length=64)
    start_time: float | None = None
    end_time: float | None = None
    z_index: int | None = None


class PackageProvenanceArtifact(BaseModel):
    """Stable JSON-ready provenance artifact for packaged reels."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["phase_1"] = "phase_1"
    artifact_type: Literal["provenance"] = "provenance"
    reel_id: str | None = Field(default=None, max_length=128)
    asset_pack_id: str | None = Field(default=None, max_length=128)
    composition_manifest_hash: str | None = Field(default=None, max_length=256)
    editor_version: str = Field(min_length=1, max_length=80)
    render_timestamp: datetime | None = None
    generation_params: dict[str, Any] = Field(default_factory=dict)
    package_timestamps: list[PackageTimestampEntry] = Field(default_factory=list)
    assets: list[PackageAssetProvenance] = Field(default_factory=list)
    source_assets: list[PackageAssetProvenance] = Field(default_factory=list)
    derived_assets: list[PackageAssetProvenance] = Field(default_factory=list)
    final_render_asset_id: str | None = Field(default=None, max_length=128)
    package_artifacts: list[PackageArtifactProvenance] = Field(default_factory=list)
    transforms: list[TransformProvenance] = Field(default_factory=list)
    provider_jobs: list[ProviderJobProvenance] = Field(default_factory=list)
    summary: PackageProvenanceSummary

    @field_validator("editor_version", mode="before")
    @classmethod
    def _normalize_editor_version(cls, value: str) -> str:
        return _clean_text(value, field_name="editor_version", max_length=80)


def build_provenance(
    *,
    assets: Sequence[PackageAssetProvenance | Mapping[str, Any]],
    generation_params: Mapping[str, Any] | None = None,
    provider_jobs: Sequence[ProviderJobProvenance | Mapping[str, Any]] = (),
    editor_version: str,
    package_timestamps: (
        Mapping[str, datetime | str] | Sequence[PackageTimestampEntry | Mapping[str, Any]]
    ),
    reel_id: str | None = None,
    asset_pack_id: str | None = None,
    composition_manifest_hash: str | None = None,
    source_assets: Sequence[PackageAssetProvenance | Mapping[str, Any]] | None = None,
    derived_assets: Sequence[PackageAssetProvenance | Mapping[str, Any]] | None = None,
    final_render_asset_id: str | None = None,
    package_artifacts: Sequence[PackageArtifactProvenance | Mapping[str, Any]] = (),
    transforms: Sequence[TransformProvenance | Mapping[str, Any]] = (),
    render_timestamp: datetime | str | None = None,
) -> PackageProvenanceArtifact:
    """Build a stable provenance artifact while redacting provider secrets."""

    normalized_assets = sorted(
        (PackageAssetProvenance.model_validate(asset) for asset in assets),
        key=lambda item: (
            "" if item.stage is None else item.stage,
            item.role,
            "" if item.asset_id is None else item.asset_id,
            item.storage_uri,
        ),
    )
    normalized_provider_jobs = sorted(
        (ProviderJobProvenance.model_validate(job) for job in provider_jobs),
        key=lambda item: (
            item.provider,
            "" if item.model is None else item.model,
            "" if item.job_id is None else item.job_id,
            "" if item.task_id is None else item.task_id,
            "" if item.external_ref is None else item.external_ref,
        ),
    )
    normalized_timestamps = _coerce_package_timestamps(package_timestamps)
    sanitized_generation_params = dict(
        _stable_json_value(redact_provider_data(generation_params or {}))
    )
    normalized_source_assets = _normalize_asset_subset(
        source_assets,
        normalized_assets,
        default="source",
    )
    normalized_derived_assets = _normalize_asset_subset(
        derived_assets,
        normalized_assets,
        default="derived",
    )

    return PackageProvenanceArtifact(
        reel_id=_optional_str(reel_id),
        asset_pack_id=_optional_str(asset_pack_id),
        composition_manifest_hash=_optional_str(composition_manifest_hash),
        editor_version=editor_version,
        render_timestamp=_optional_datetime(render_timestamp),
        generation_params=sanitized_generation_params,
        package_timestamps=normalized_timestamps,
        assets=list(normalized_assets),
        source_assets=normalized_source_assets,
        derived_assets=normalized_derived_assets,
        final_render_asset_id=_optional_str(final_render_asset_id)
        or _final_render_asset_id(normalized_assets),
        package_artifacts=[
            PackageArtifactProvenance.model_validate(artifact) for artifact in package_artifacts
        ],
        transforms=[TransformProvenance.model_validate(transform) for transform in transforms],
        provider_jobs=list(normalized_provider_jobs),
        summary=PackageProvenanceSummary(
            asset_count=len(normalized_assets),
            provider_job_count=len(normalized_provider_jobs),
            asset_roles=[asset.role for asset in normalized_assets],
            provider_refs=[
                reference
                for reference in (_provider_reference(job) for job in normalized_provider_jobs)
                if reference is not None
            ],
            timestamp_labels=[entry.label for entry in normalized_timestamps],
        ),
    )


def serialize_provenance_json(provenance: PackageProvenanceArtifact | Mapping[str, Any]) -> str:
    """Serialize a provenance artifact into stable JSON."""

    return json.dumps(
        _stable_json_value(provenance),
        sort_keys=True,
        separators=(",", ":"),
    )


def _coerce_package_timestamps(
    package_timestamps: (
        Mapping[str, datetime | str] | Sequence[PackageTimestampEntry | Mapping[str, Any]]
    ),
) -> list[PackageTimestampEntry]:
    if isinstance(package_timestamps, Mapping):
        raw_entries: list[PackageTimestampEntry | Mapping[str, Any]] = [
            {"label": label, "timestamp": timestamp}
            for label, timestamp in package_timestamps.items()
        ]
    else:
        raw_entries = list(package_timestamps)

    return sorted(
        (PackageTimestampEntry.model_validate(entry) for entry in raw_entries),
        key=lambda item: (item.timestamp.isoformat(), item.label),
    )


def _provider_reference(job: ProviderJobProvenance) -> str | None:
    for value in (job.job_id, job.task_id, job.external_ref):
        if value is not None:
            return value
    return None


def _normalize_asset_subset(
    explicit_assets: Sequence[PackageAssetProvenance | Mapping[str, Any]] | None,
    all_assets: Sequence[PackageAssetProvenance],
    *,
    default: Literal["source", "derived"],
) -> list[PackageAssetProvenance]:
    if explicit_assets is not None:
        return sorted(
            (PackageAssetProvenance.model_validate(asset) for asset in explicit_assets),
            key=lambda item: (
                "" if item.stage is None else item.stage,
                item.role,
                "" if item.asset_id is None else item.asset_id,
                item.storage_uri,
            ),
        )
    predicate = _is_source_asset if default == "source" else _is_derived_asset
    return [asset for asset in all_assets if predicate(asset)]


def _is_source_asset(asset: PackageAssetProvenance) -> bool:
    stage = (asset.stage or "").strip().lower()
    source = (asset.source_type or asset.source or "").strip().lower()
    return (
        stage in {"input", "source", "raw"}
        or source in {"uploaded", "operator_upload", "approved_external_source", "generated"}
    ) and not _is_derived_asset(asset)


def _is_derived_asset(asset: PackageAssetProvenance) -> bool:
    stage = (asset.stage or "").strip().lower()
    source = (asset.source_type or asset.source or "").strip().lower()
    role = asset.role.strip().lower()
    return (
        stage in {"derived", "output", "render"}
        or source in {"derived", "package_output"}
        or role in {"final_video", "final_render", "cover"}
        or asset.derived_from_asset_id is not None
    )


def _final_render_asset_id(assets: Sequence[PackageAssetProvenance]) -> str | None:
    for asset in assets:
        if asset.asset_id and asset.role.strip().lower() in {"final_video", "final_render"}:
            return asset.asset_id
    return None


__all__ = [
    "PackageAssetProvenance",
    "PackageArtifactProvenance",
    "PackageProvenanceArtifact",
    "PackageProvenanceSummary",
    "PackageTimestampEntry",
    "ProviderJobProvenance",
    "TransformProvenance",
    "build_provenance",
    "serialize_provenance_json",
]
