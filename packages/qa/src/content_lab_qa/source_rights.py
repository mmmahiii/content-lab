"""Source/licence QA gate for source-first asset provenance.

This is intentionally a policy surface, not legal clearance. It checks whether
the provenance contains enough usage metadata to proceed or to flag review.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

from content_lab_core.types import QAVerdict
from content_lab_qa.gate import QAResult


class SourceRightsPolicy(BaseModel):
    """Configurable severity policy for source-rights metadata gaps."""

    model_config = ConfigDict(extra="forbid")

    unknown_source_verdict: QAVerdict = QAVerdict.WARN
    incomplete_external_verdict: QAVerdict = QAVerdict.WARN
    incomplete_upload_verdict: QAVerdict = QAVerdict.WARN


def validate_source_rights(
    provenance_or_assets: Mapping[str, Any] | Sequence[Mapping[str, Any]] | object,
    *,
    policy: SourceRightsPolicy | None = None,
) -> QAResult:
    """Check that sourced/imported package assets expose usable rights metadata."""

    resolved_policy = policy or SourceRightsPolicy()
    assets = _extract_assets(provenance_or_assets)
    if assets is None:
        return QAResult(
            gate_name="source_rights",
            verdict=QAVerdict.FAIL,
            message="Source rights QA requires a provenance object or asset list.",
            details={"findings": [{"code": "source_rights_payload_invalid", "severity": "fail"}]},
        )

    findings: list[dict[str, Any]] = []
    for index, asset in enumerate(assets, start=1):
        finding = _asset_source_rights_finding(asset, index=index, policy=resolved_policy)
        if finding is not None:
            findings.append(finding)

    fail_count = sum(1 for finding in findings if finding["severity"] == "fail")
    warn_count = sum(1 for finding in findings if finding["severity"] == "warn")
    if fail_count:
        return QAResult(
            gate_name="source_rights",
            verdict=QAVerdict.FAIL,
            message="Source rights metadata has blocking gaps.",
            details={"findings": findings, "asset_count": len(assets)},
        )
    if warn_count:
        return QAResult(
            gate_name="source_rights",
            verdict=QAVerdict.WARN,
            message="Source rights metadata needs review before packaging.",
            details={"findings": findings, "asset_count": len(assets)},
        )
    return QAResult(
        gate_name="source_rights",
        verdict=QAVerdict.PASS,
        message="Source rights metadata is sufficient for phase-1 policy.",
        details={"findings": [], "asset_count": len(assets)},
    )


def _extract_assets(
    provenance_or_assets: Mapping[str, Any] | Sequence[Mapping[str, Any]] | object,
) -> list[Mapping[str, Any]] | None:
    if isinstance(provenance_or_assets, Mapping):
        raw_assets = provenance_or_assets.get("assets")
        if raw_assets is None:
            raw_assets = [provenance_or_assets]
    elif isinstance(provenance_or_assets, Sequence) and not isinstance(
        provenance_or_assets, str | bytes | bytearray
    ):
        raw_assets = provenance_or_assets
    else:
        return None
    if not isinstance(raw_assets, Sequence) or isinstance(raw_assets, str | bytes | bytearray):
        return None
    return [asset for asset in raw_assets if isinstance(asset, Mapping)]


def _asset_source_rights_finding(
    asset: Mapping[str, Any],
    *,
    index: int,
    policy: SourceRightsPolicy,
) -> dict[str, Any] | None:
    source_type = _normalized(_asset_value(asset, "source_type"))
    usage_allowed = _optional_bool(_asset_value(asset, "usage_allowed"))
    licence_type = _normalized(_asset_value(asset, "licence_type"))
    licence_notes = _normalized(_asset_value(asset, "licence_notes"))
    source_provider = _normalized(_asset_value(asset, "source_provider"))
    attribution_required = _optional_bool(_asset_value(asset, "attribution_required"))
    attribution_text = _normalized(_asset_value(asset, "attribution_text"))

    if source_type == "generated":
        return None
    if source_type == "operator_uploaded":
        if usage_allowed is True:
            return None
        if usage_allowed is False:
            return _finding(asset, index, "operator_upload_usage_disallowed", QAVerdict.FAIL)
        return _finding(asset, index, "operator_upload_usage_unconfirmed", policy.incomplete_upload_verdict)
    if source_type == "approved_external_source":
        if usage_allowed is False:
            return _finding(asset, index, "external_usage_disallowed", QAVerdict.FAIL)
        if attribution_required is True and not attribution_text:
            return _finding(asset, index, "external_attribution_missing", QAVerdict.FAIL)
        if usage_allowed is True and source_provider and (licence_type or licence_notes):
            return None
        return _finding(
            asset,
            index,
            "external_licence_metadata_incomplete",
            policy.incomplete_external_verdict,
        )
    if source_type == "derived_from_existing":
        if _normalized(_asset_value(asset, "derived_from_asset_id")) or _asset_value(
            asset, "transform_recipe"
        ):
            return None
        return _finding(asset, index, "derived_source_missing_origin", policy.unknown_source_verdict)
    return _finding(asset, index, "source_type_unknown", policy.unknown_source_verdict)


def _asset_value(asset: Mapping[str, Any], field_name: str) -> Any:
    value = asset.get(field_name)
    if value is not None:
        return value
    metadata = asset.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    source_metadata = metadata.get("source_metadata")
    source_metadata = source_metadata if isinstance(source_metadata, Mapping) else {}
    if field_name in source_metadata:
        return source_metadata[field_name]
    if field_name == "source_type":
        return metadata.get("asset_source") or asset.get("source")
    if field_name == "licence_notes":
        return source_metadata.get("licence_notes")
    return metadata.get(field_name)


def _finding(
    asset: Mapping[str, Any],
    index: int,
    code: str,
    verdict: QAVerdict,
) -> dict[str, Any]:
    severity = "fail" if verdict is QAVerdict.FAIL else "warn"
    return {
        "code": code,
        "severity": severity,
        "asset_index": index,
        "asset_id": _normalized(asset.get("asset_id")),
        "role": _normalized(asset.get("used_as_component_role") or asset.get("role")),
    }


def _normalized(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


__all__ = ["SourceRightsPolicy", "validate_source_rights"]
