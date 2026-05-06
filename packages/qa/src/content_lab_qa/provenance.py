"""Reusable provenance validation for ready-to-post reel packages."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from content_lab_core.types import QAVerdict
from content_lab_qa.gate import QAResult

_REQUIRED_PROVENANCE_FIELDS = ("editor_version", "assets", "provider_jobs")
_REQUIRED_ASSET_FIELDS = (
    "role",
    "storage_uri",
    "asset_id",
    "asset_kind",
    "media_type",
    "source_type",
    "stored_content_hash",
    "used_as_component_role",
)
_REQUIRED_PROVIDER_FIELDS = ("provider", "status")


def validate_package_provenance(provenance: Mapping[str, Any] | object) -> QAResult:
    """Validate the provenance payload needed for package auditability."""

    errors: list[str] = []
    details: dict[str, Any] = {}

    if not isinstance(provenance, Mapping):
        return QAResult(
            gate_name="package_provenance",
            verdict=QAVerdict.FAIL,
            message="Package provenance must be a JSON object.",
            details={"errors": ["Package provenance must be a JSON object."]},
        )

    missing_top_level = [
        field_name
        for field_name in _REQUIRED_PROVENANCE_FIELDS
        if _is_blank(provenance.get(field_name))
    ]
    if missing_top_level:
        errors.append(
            "Package provenance is missing required fields: " + ", ".join(missing_top_level) + "."
        )

    editor_version = provenance.get("editor_version")
    if editor_version is not None and _is_blank(editor_version):
        errors.append("Package provenance editor_version must not be blank.")

    assets = provenance.get("assets")
    if not isinstance(assets, list) or not assets:
        errors.append("Package provenance must include at least one asset lineage entry.")
        asset_count = 0
    else:
        asset_count = len(assets)
        for index, asset in enumerate(assets, start=1):
            if not isinstance(asset, Mapping):
                errors.append(f"Asset lineage entry {index} must be an object.")
                continue
            missing_fields = [
                field_name
                for field_name in _REQUIRED_ASSET_FIELDS
                if _is_blank(_asset_provenance_value(asset, field_name))
            ]
            if missing_fields:
                errors.append(
                    f"Asset lineage entry {index} is missing required fields: "
                    + ", ".join(missing_fields)
                    + "."
                )

    provider_jobs = provenance.get("provider_jobs")
    if not isinstance(provider_jobs, list) or not provider_jobs:
        errors.append("Package provenance must include at least one provider lineage entry.")
        provider_job_count = 0
    else:
        provider_job_count = len(provider_jobs)
        for index, provider_job in enumerate(provider_jobs, start=1):
            if not isinstance(provider_job, Mapping):
                errors.append(f"Provider lineage entry {index} must be an object.")
                continue
            missing_fields = [
                field_name
                for field_name in _REQUIRED_PROVIDER_FIELDS
                if _is_blank(provider_job.get(field_name))
            ]
            if missing_fields:
                errors.append(
                    f"Provider lineage entry {index} is missing required fields: "
                    + ", ".join(missing_fields)
                    + "."
                )

    details["asset_count"] = asset_count
    details["provider_job_count"] = provider_job_count
    if errors:
        details["errors"] = list(errors)
        return QAResult(
            gate_name="package_provenance",
            verdict=QAVerdict.FAIL,
            message=errors[0],
            details=details,
        )

    return QAResult(
        gate_name="package_provenance",
        verdict=QAVerdict.PASS,
        message="Package provenance includes editor, asset, and provider lineage.",
        details=details,
    )


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _asset_provenance_value(asset: Mapping[str, Any], field_name: str) -> Any:
    value = asset.get(field_name)
    if not _is_blank(value):
        return value
    metadata = asset.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    source_metadata = metadata.get("source_metadata")
    source_metadata = source_metadata if isinstance(source_metadata, Mapping) else {}
    if field_name == "asset_kind":
        return metadata.get("asset_kind") or asset.get("kind")
    if field_name == "media_type":
        return metadata.get("media_type") or asset.get("kind")
    if field_name == "source_type":
        return source_metadata.get("source_type") or metadata.get("asset_source") or asset.get("source")
    if field_name == "stored_content_hash":
        return asset.get("content_hash") or metadata.get("content_hash")
    if field_name == "used_as_component_role":
        return asset.get("role")
    return value


__all__ = ["validate_package_provenance"]
