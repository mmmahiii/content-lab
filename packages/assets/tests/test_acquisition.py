from __future__ import annotations

import uuid

import pytest

from content_lab_assets.acquisition import (
    AssetAcquisitionPath,
    acquisition_decision_for_compatible_registry_reuse,
    acquisition_decision_for_operator_upload,
    evaluate_acquisition_before_generation,
)
from content_lab_assets.types import AssetSourceMetadata, AssetSourceType


def test_evaluate_acquisition_defaults_to_generate() -> None:
    spec_id = uuid.uuid4()
    decision = evaluate_acquisition_before_generation(
        planned_asset_spec_id=spec_id,
        required_traits={},
        compatible_with={},
        pack_niche="coffee",
    )
    assert decision.recommended_acquisition_path is AssetAcquisitionPath.GENERATE_NEW_ASSET
    assert decision.resolved_acquisition_path is None
    assert decision.fallback_path is AssetAcquisitionPath.REUSE_EXISTING_REGISTRY_ASSET


def test_evaluate_acquisition_force_block() -> None:
    spec_id = uuid.uuid4()
    decision = evaluate_acquisition_before_generation(
        planned_asset_spec_id=spec_id,
        required_traits={"acquisition": {"force_block": True, "block_reason": "policy"}},
        compatible_with={},
        pack_niche="coffee",
    )
    assert decision.recommended_acquisition_path is AssetAcquisitionPath.BLOCK_OR_REPLACE_ASSET
    assert decision.resolved_acquisition_path is AssetAcquisitionPath.BLOCK_OR_REPLACE_ASSET
    assert "policy" in decision.rationale


def test_evaluate_acquisition_all_high_risks_blocks() -> None:
    spec_id = uuid.uuid4()
    decision = evaluate_acquisition_before_generation(
        planned_asset_spec_id=spec_id,
        required_traits={
            "acquisition": {
                "quality_risk": "high",
                "licence_risk": "high",
                "realism_risk": "high",
            }
        },
        compatible_with={},
        pack_niche="coffee",
    )
    assert decision.recommended_acquisition_path is AssetAcquisitionPath.BLOCK_OR_REPLACE_ASSET


def test_evaluate_acquisition_approved_external() -> None:
    spec_id = uuid.uuid4()
    ext_id = uuid.uuid4()
    decision = evaluate_acquisition_before_generation(
        planned_asset_spec_id=spec_id,
        required_traits={"acquisition": {"approved_external_asset_id": str(ext_id)}},
        compatible_with={},
        pack_niche="coffee",
    )
    assert decision.recommended_acquisition_path is AssetAcquisitionPath.USE_APPROVED_EXTERNAL_ASSET
    assert decision.candidate_asset_id == ext_id
    assert decision.fallback_path is AssetAcquisitionPath.GENERATE_NEW_ASSET


def test_evaluate_acquisition_reuse_with_transform() -> None:
    spec_id = uuid.uuid4()
    base_id = uuid.uuid4()
    decision = evaluate_acquisition_before_generation(
        planned_asset_spec_id=spec_id,
        required_traits={
            "acquisition": {
                "reuse_with_transform": {
                    "base_asset_id": str(base_id),
                    "reason": "Crop to vertical",
                    "transform_recipe": {"op": "crop", "ratio": "9:16"},
                }
            }
        },
        compatible_with={},
        pack_niche="coffee",
    )
    assert decision.recommended_acquisition_path is AssetAcquisitionPath.REUSE_WITH_TRANSFORM
    assert decision.candidate_asset_id == base_id
    assert decision.transform_recipe == {"op": "crop", "ratio": "9:16"}


def test_evaluate_acquisition_require_operator_upload_blocks() -> None:
    spec_id = uuid.uuid4()
    decision = evaluate_acquisition_before_generation(
        planned_asset_spec_id=spec_id,
        required_traits={"acquisition": {"require_operator_upload": True}},
        compatible_with={},
        pack_niche="coffee",
    )
    assert decision.recommended_acquisition_path is AssetAcquisitionPath.BLOCK_OR_REPLACE_ASSET
    assert decision.fallback_path is AssetAcquisitionPath.USE_OPERATOR_UPLOADED_ASSET


def test_acquisition_decision_for_compatible_registry_reuse() -> None:
    spec_id = uuid.uuid4()
    aid = uuid.uuid4()
    d = acquisition_decision_for_compatible_registry_reuse(
        planned_asset_spec_id=spec_id,
        match_metadata={"asset_id": str(aid), "score": 10, "matched_on": ["asset_kind"]},
    )
    assert d.recommended_acquisition_path is AssetAcquisitionPath.REUSE_EXISTING_REGISTRY_ASSET
    assert d.candidate_asset_id == aid
    assert d.resolved_acquisition_path is AssetAcquisitionPath.REUSE_EXISTING_REGISTRY_ASSET


def test_acquisition_decision_for_operator_upload() -> None:
    spec_id = uuid.uuid4()
    aid = uuid.uuid4()
    sm = AssetSourceMetadata(
        source_type=AssetSourceType.OPERATOR_UPLOADED,
        usage_allowed=True,
        commercial_use_allowed=False,
    )
    d = acquisition_decision_for_operator_upload(
        planned_asset_spec_id=spec_id,
        asset_id=aid,
        source_metadata=sm,
    )
    assert d.recommended_acquisition_path is AssetAcquisitionPath.USE_OPERATOR_UPLOADED_ASSET
    assert d.source_metadata is not None
    assert d.source_metadata.source_type is AssetSourceType.OPERATOR_UPLOADED


def test_asset_source_metadata_attribution_validation() -> None:
    with pytest.raises(ValueError):
        AssetSourceMetadata(
            source_type=AssetSourceType.APPROVED_EXTERNAL_SOURCE,
            attribution_required=True,
            attribution_text=None,
        )
