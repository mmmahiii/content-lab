from __future__ import annotations

import uuid

from content_lab_assets.types import (
    AssetKind,
    AssetSource,
    AssetSourceType,
    GenerateDecision,
    GenerationIntent,
    MediaType,
)


def test_asset_source_includes_required_values() -> None:
    assert {source.value for source in AssetSource} == {
        "uploaded",
        "generated",
        "imported",
        "observed_reference",
        "derived",
        "manual_template",
        "package_output",
    }


def test_asset_source_type_includes_backlog_values() -> None:
    assert {st.value for st in AssetSourceType} == {
        "generated",
        "operator_uploaded",
        "approved_external_source",
        "existing_registry_asset",
        "derived_from_existing",
        "package_output",
        "unknown",
    }


def test_generated_and_derived_asset_sources_are_distinct() -> None:
    assert {
        AssetSource.UPLOADED,
        AssetSource.GENERATED,
        AssetSource.DERIVED,
        AssetSource.PACKAGE_OUTPUT,
    } <= set(AssetSource)
    assert (
        len(
            {
                AssetSource.UPLOADED.value,
                AssetSource.GENERATED.value,
                AssetSource.DERIVED.value,
                AssetSource.PACKAGE_OUTPUT.value,
            }
        )
        == 4
    )


def test_registry_payloads_default_to_generated_source() -> None:
    intent = GenerationIntent(
        asset_id=uuid.UUID("00000000-0000-4000-8000-000000000001"),
        asset_status="staged",
        storage_uri="s3://content-lab/assets/raw/asset-1/source.bin",
        idempotency_key="asset.generate:abc",
        asset_class="clip",
        provider="runway",
        model="gen4.5",
        asset_key="{}",
        asset_key_hash="abc",
    )
    decision = GenerateDecision(
        asset_class="clip",
        asset_key="{}",
        asset_key_hash="abc",
        provider="runway",
        model="gen4.5",
        generation_intent=intent,
    )

    assert intent.asset_source is AssetSource.GENERATED
    assert decision.asset_source is AssetSource.GENERATED
    assert decision.asset_kind is AssetKind.GENERATED_CLIP
    assert decision.media_type is MediaType.VIDEO
    assert decision.model_dump(mode="json")["asset_source"] == "generated"
