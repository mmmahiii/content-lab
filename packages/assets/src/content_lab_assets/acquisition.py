"""Planned-asset acquisition ladder (reuse, upload, external, generate, block)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from content_lab_assets.motion_suitability import (
    MotionSuitabilityAssessment,
    evaluate_motion_suitability,
)
from content_lab_assets.types import AssetSourceMetadata, AssetSourceType


class AssetAcquisitionPath(StrEnum):
    """Ordered acquisition outcomes for a planned asset spec."""

    REUSE_EXISTING_REGISTRY_ASSET = "reuse_existing_registry_asset"
    REUSE_WITH_TRANSFORM = "reuse_with_transform"
    USE_OPERATOR_UPLOADED_ASSET = "use_operator_uploaded_asset"
    USE_APPROVED_EXTERNAL_ASSET = "use_approved_external_asset"
    GENERATE_NEW_ASSET = "generate_new_asset"
    BLOCK_OR_REPLACE_ASSET = "block_or_replace_asset"


class AcquisitionDecision(BaseModel):
    """Structured acquisition outcome for one planned asset spec."""

    model_config = ConfigDict(extra="forbid")

    planned_asset_spec_id: uuid.UUID
    recommended_acquisition_path: AssetAcquisitionPath
    rationale: str = Field(min_length=1, max_length=4000)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    quality_risk: str | None = Field(default=None, max_length=32)
    licence_risk: str | None = Field(default=None, max_length=32)
    realism_risk: str | None = Field(default=None, max_length=32)
    expected_cost_impact: str | None = Field(default=None, max_length=32)
    fallback_path: AssetAcquisitionPath | None = None
    candidate_asset_id: uuid.UUID | None = None
    transform_recipe: dict[str, Any] = Field(default_factory=dict)
    resolved_acquisition_path: AssetAcquisitionPath | None = None
    source_metadata: AssetSourceMetadata | None = None
    motion_suitability: MotionSuitabilityAssessment | None = None

    @field_validator("quality_risk", "licence_risk", "realism_risk", "expected_cost_impact")
    @classmethod
    def _normalize_risk_token(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        return normalized or None


def _acquisition_traits(required_traits: Mapping[str, Any] | None) -> dict[str, Any]:
    traits = dict(required_traits or {})
    raw = traits.get("acquisition")
    return dict(raw) if isinstance(raw, Mapping) else {}


def _risk_levels(traits: Mapping[str, Any]) -> tuple[str | None, str | None, str | None]:
    return (
        traits.get("quality_risk"),
        traits.get("licence_risk"),
        traits.get("realism_risk"),
    )


def _all_high(
    quality: str | None,
    licence: str | None,
    realism: str | None,
) -> bool:
    def is_high(value: str | None) -> bool:
        return str(value or "").strip().lower() == "high"

    return is_high(quality) and is_high(licence) and is_high(realism)


def acquisition_decision_for_compatible_registry_reuse(
    *,
    planned_asset_spec_id: uuid.UUID,
    match_metadata: Mapping[str, Any],
) -> AcquisitionDecision:
    """Decision when a ready org asset was attached via compatibility scoring."""

    asset_raw = match_metadata.get("asset_id")
    asset_uuid = uuid.UUID(str(asset_raw)) if asset_raw is not None else None
    score = int(match_metadata.get("score") or 0)
    confidence = min(1.0, 0.35 + score / 25.0)
    return AcquisitionDecision(
        planned_asset_spec_id=planned_asset_spec_id,
        recommended_acquisition_path=AssetAcquisitionPath.REUSE_EXISTING_REGISTRY_ASSET,
        rationale="Reused a ready registry asset compatible with the planned spec.",
        confidence=confidence,
        quality_risk="low",
        licence_risk="low",
        realism_risk="low",
        expected_cost_impact="low",
        fallback_path=AssetAcquisitionPath.GENERATE_NEW_ASSET,
        candidate_asset_id=asset_uuid,
        resolved_acquisition_path=AssetAcquisitionPath.REUSE_EXISTING_REGISTRY_ASSET,
        motion_suitability=None,
    )


def acquisition_decision_for_operator_upload(
    *,
    planned_asset_spec_id: uuid.UUID,
    asset_id: uuid.UUID,
    source_metadata: AssetSourceMetadata | None = None,
) -> AcquisitionDecision:
    """Decision when the pack item already references operator-provided bytes."""

    return AcquisitionDecision(
        planned_asset_spec_id=planned_asset_spec_id,
        recommended_acquisition_path=AssetAcquisitionPath.USE_OPERATOR_UPLOADED_ASSET,
        rationale="Planned asset fulfilled by operator-uploaded or imported registry asset.",
        confidence=1.0,
        quality_risk="low",
        licence_risk="low",
        realism_risk="low",
        expected_cost_impact="low",
        fallback_path=AssetAcquisitionPath.GENERATE_NEW_ASSET,
        candidate_asset_id=asset_id,
        resolved_acquisition_path=AssetAcquisitionPath.USE_OPERATOR_UPLOADED_ASSET,
        source_metadata=source_metadata,
        motion_suitability=None,
    )


def evaluate_acquisition_before_generation(
    *,
    planned_asset_spec_id: uuid.UUID,
    required_traits: Mapping[str, Any] | None,
    compatible_with: Mapping[str, Any] | None,
    pack_niche: str,
    asset_kind: str | None = None,
    media_type: str | None = None,
    purpose: str | None = None,
    prompt_or_description: str | None = None,
) -> AcquisitionDecision:
    """Choose acquisition path for a spec that still needs fulfilment (no item.asset_id yet).

    Deterministic rules:
    - Explicit ``acquisition.force_block`` or all three risk flags ``high`` -> block.
    - ``acquisition.approved_external_asset_id`` -> use approved external (caller attaches).
    - ``acquisition.reuse_with_transform`` with ``base_asset_id`` -> reuse_with_transform;
      generation remains the operational fallback until transform execution exists.
    - Otherwise -> generate, with cost impact ``high`` and conservative confidence.
    """

    _ = compatible_with  # reserved for richer matching later
    traits = dict(required_traits or {})
    acq = _acquisition_traits(traits)
    q_risk, l_risk, r_risk = _risk_levels(acq)

    motion: MotionSuitabilityAssessment | None = None
    r_risk_eff = str(r_risk).lower() if r_risk else None
    rationale_motion_note = ""
    if asset_kind and media_type and purpose is not None and prompt_or_description is not None:
        motion = evaluate_motion_suitability(
            asset_kind=asset_kind,
            media_type=media_type,
            purpose=purpose,
            prompt_or_description=prompt_or_description,
        )
        if motion.requires_true_motion and str(media_type).lower() == "image":
            r_risk_eff = r_risk_eff or "medium"
            rationale_motion_note = (
                f" {motion.motion_reason} "
                "(Planned image role vs motion-heavy description: prefer revising media type "
                "or using video/source motion.)"
            )

    if traits.get("block_generation") is True or acq.get("force_block") is True:
        return AcquisitionDecision(
            planned_asset_spec_id=planned_asset_spec_id,
            recommended_acquisition_path=AssetAcquisitionPath.BLOCK_OR_REPLACE_ASSET,
            rationale=str(
                acq.get("block_reason")
                or traits.get("block_reason")
                or "Generation blocked by planned-spec policy flags."
            ),
            confidence=1.0,
            quality_risk=str(q_risk or "high").lower() if q_risk else "high",
            licence_risk=str(l_risk or "high").lower() if l_risk else "high",
            realism_risk=str(r_risk_eff or "high").lower() if r_risk_eff else "high",
            expected_cost_impact="low",
            fallback_path=None,
            resolved_acquisition_path=AssetAcquisitionPath.BLOCK_OR_REPLACE_ASSET,
            motion_suitability=motion,
        )

    if _all_high(
        str(q_risk).lower() if q_risk else None,
        str(l_risk).lower() if l_risk else None,
        str(r_risk).lower() if r_risk else None,
    ):
        return AcquisitionDecision(
            planned_asset_spec_id=planned_asset_spec_id,
            recommended_acquisition_path=AssetAcquisitionPath.BLOCK_OR_REPLACE_ASSET,
            rationale="Combined quality, licence, and realism risks are high; "
            "block generation until assets are replaced or cleared.",
            confidence=0.9,
            quality_risk="high",
            licence_risk="high",
            realism_risk="high",
            expected_cost_impact="low",
            fallback_path=AssetAcquisitionPath.GENERATE_NEW_ASSET,
            resolved_acquisition_path=AssetAcquisitionPath.BLOCK_OR_REPLACE_ASSET,
            motion_suitability=motion,
        )

    ext_raw = acq.get("approved_external_asset_id") or traits.get("approved_external_asset_id")
    if ext_raw is not None:
        try:
            ext_uuid = uuid.UUID(str(ext_raw))
        except (TypeError, ValueError):
            ext_uuid = None
        if ext_uuid is not None:
            return AcquisitionDecision(
                planned_asset_spec_id=planned_asset_spec_id,
                recommended_acquisition_path=AssetAcquisitionPath.USE_APPROVED_EXTERNAL_ASSET,
                rationale="Planned spec names an approved external/registry asset id to attach.",
                confidence=0.85,
                quality_risk=str(q_risk or "low").lower() if q_risk else "low",
                licence_risk=str(l_risk or "low").lower() if l_risk else "low",
                realism_risk=str(r_risk_eff or "low").lower() if r_risk_eff else "low",
                expected_cost_impact="low",
                fallback_path=AssetAcquisitionPath.GENERATE_NEW_ASSET,
                candidate_asset_id=ext_uuid,
                motion_suitability=motion,
            )

    transform = acq.get("reuse_with_transform")
    if isinstance(transform, Mapping):
        base_raw = transform.get("base_asset_id")
        if base_raw is not None:
            try:
                base_uuid = uuid.UUID(str(base_raw))
            except (TypeError, ValueError):
                base_uuid = None
            if base_uuid is not None:
                recipe = transform.get("transform_recipe")
                recipe_dict = dict(recipe) if isinstance(recipe, Mapping) else {}
                return AcquisitionDecision(
                    planned_asset_spec_id=planned_asset_spec_id,
                    recommended_acquisition_path=AssetAcquisitionPath.REUSE_WITH_TRANSFORM,
                    rationale=str(
                        transform.get("reason") or "Deterministic transform of an existing asset."
                    ),
                    confidence=0.75,
                    quality_risk=str(q_risk or "medium").lower() if q_risk else "medium",
                    licence_risk=str(l_risk or "low").lower() if l_risk else "low",
                    realism_risk=str(r_risk_eff or "medium").lower() if r_risk_eff else "medium",
                    expected_cost_impact="medium",
                    fallback_path=AssetAcquisitionPath.GENERATE_NEW_ASSET,
                    candidate_asset_id=base_uuid,
                    transform_recipe=recipe_dict,
                    motion_suitability=motion,
                )

    if acq.get("require_operator_upload") is True:
        return AcquisitionDecision(
            planned_asset_spec_id=planned_asset_spec_id,
            recommended_acquisition_path=AssetAcquisitionPath.BLOCK_OR_REPLACE_ASSET,
            rationale=str(
                acq.get("require_operator_upload_reason")
                or "Operator upload required before this planned asset can be fulfilled."
            ),
            confidence=1.0,
            quality_risk="low",
            licence_risk="low",
            realism_risk="low",
            expected_cost_impact="low",
            fallback_path=AssetAcquisitionPath.USE_OPERATOR_UPLOADED_ASSET,
            resolved_acquisition_path=AssetAcquisitionPath.BLOCK_OR_REPLACE_ASSET,
            motion_suitability=motion,
        )

    niche_note = f" Pack niche: {pack_niche}." if pack_niche else ""
    return AcquisitionDecision(
        planned_asset_spec_id=planned_asset_spec_id,
        recommended_acquisition_path=AssetAcquisitionPath.GENERATE_NEW_ASSET,
        rationale=(
            "No non-generative fulfilment path matched; staged generation is justified."
            + rationale_motion_note
            + niche_note
        ),
        confidence=0.55,
        quality_risk=str(q_risk or "medium").lower() if q_risk else "medium",
        licence_risk=str(l_risk or "low").lower() if l_risk else "low",
        realism_risk=str(r_risk_eff or "medium").lower() if r_risk_eff else "medium",
        expected_cost_impact="high",
        fallback_path=AssetAcquisitionPath.REUSE_EXISTING_REGISTRY_ASSET,
        motion_suitability=motion,
    )


def default_generated_source_metadata() -> AssetSourceMetadata:
    """Default provenance for provider-generated assets."""

    return AssetSourceMetadata(source_type=AssetSourceType.GENERATED)


__all__ = [
    "AcquisitionDecision",
    "AssetAcquisitionPath",
    "MotionSuitabilityAssessment",
    "acquisition_decision_for_compatible_registry_reuse",
    "acquisition_decision_for_operator_upload",
    "default_generated_source_metadata",
    "evaluate_acquisition_before_generation",
]
