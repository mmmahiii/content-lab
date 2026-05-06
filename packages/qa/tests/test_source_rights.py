from __future__ import annotations

from content_lab_core.types import QAVerdict
from content_lab_qa.source_rights import SourceRightsPolicy, validate_source_rights


def _asset(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "role": "component",
        "asset_id": "asset-1",
        "asset_kind": "object_image",
        "media_type": "image",
        "storage_uri": "s3://content-lab/assets/raw/asset-1/component.png",
        "stored_content_hash": "sha256:" + ("a" * 64),
        "used_as_component_role": "component",
    }
    payload.update(updates)
    return payload


def test_source_rights_generated_asset_passes() -> None:
    result = validate_source_rights({"assets": [_asset(source_type="generated")]})

    assert result.verdict is QAVerdict.PASS
    assert result.details["findings"] == []


def test_source_rights_uploaded_asset_with_usage_confirmation_passes() -> None:
    result = validate_source_rights(
        {"assets": [_asset(source_type="operator_uploaded", usage_allowed=True)]}
    )

    assert result.verdict is QAVerdict.PASS


def test_source_rights_approved_external_with_metadata_passes() -> None:
    result = validate_source_rights(
        {
            "assets": [
                _asset(
                    source_type="approved_external_source",
                    source_provider="Example Stock",
                    licence_type="custom",
                    usage_allowed=True,
                    attribution_required=False,
                )
            ]
        }
    )

    assert result.verdict is QAVerdict.PASS


def test_source_rights_external_missing_usage_metadata_warns_by_default() -> None:
    result = validate_source_rights(
        {"assets": [_asset(source_type="approved_external_source", source_provider="Example Stock")]}
    )

    assert result.verdict is QAVerdict.WARN
    findings = result.details["findings"]
    assert isinstance(findings, list)
    assert findings[0]["code"] == "external_licence_metadata_incomplete"


def test_source_rights_unknown_source_can_fail_by_policy() -> None:
    result = validate_source_rights(
        {"assets": [_asset(source_type="unknown")]},
        policy=SourceRightsPolicy(unknown_source_verdict=QAVerdict.FAIL),
    )

    assert result.verdict is QAVerdict.FAIL
    findings = result.details["findings"]
    assert isinstance(findings, list)
    assert findings[0]["code"] == "source_type_unknown"


def test_source_rights_external_missing_attribution_fails() -> None:
    result = validate_source_rights(
        {
            "assets": [
                _asset(
                    source_type="approved_external_source",
                    source_provider="Example Stock",
                    licence_type="cc-by",
                    usage_allowed=True,
                    attribution_required=True,
                )
            ]
        }
    )

    assert result.verdict is QAVerdict.FAIL
    findings = result.details["findings"]
    assert isinstance(findings, list)
    assert findings[0]["code"] == "external_attribution_missing"
