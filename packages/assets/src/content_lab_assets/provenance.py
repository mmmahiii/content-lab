"""Stable package-provenance artifact generation for audit and debugging."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("role", mode="before")
    @classmethod
    def _normalize_role(cls, value: str) -> str:
        return _clean_text(value, field_name="role", max_length=64)

    @field_validator(
        "stage", "asset_id", "kind", "source", "content_hash", "asset_key_hash", mode="before"
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


class PackageProvenanceArtifact(BaseModel):
    """Stable JSON-ready provenance artifact for packaged reels."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["phase_1"] = "phase_1"
    artifact_type: Literal["provenance"] = "provenance"
    editor_version: str = Field(min_length=1, max_length=80)
    generation_params: dict[str, Any] = Field(default_factory=dict)
    package_timestamps: list[PackageTimestampEntry] = Field(default_factory=list)
    assets: list[PackageAssetProvenance] = Field(default_factory=list)
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

    return PackageProvenanceArtifact(
        editor_version=editor_version,
        generation_params=sanitized_generation_params,
        package_timestamps=normalized_timestamps,
        assets=list(normalized_assets),
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


__all__ = [
    "PackageAssetProvenance",
    "PackageProvenanceArtifact",
    "PackageProvenanceSummary",
    "PackageTimestampEntry",
    "ProviderJobProvenance",
    "build_provenance",
    "serialize_provenance_json",
]
