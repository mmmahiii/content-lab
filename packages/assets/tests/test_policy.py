from __future__ import annotations

import uuid
from datetime import UTC, datetime

from content_lab_assets.policy import (
    AssetReusePolicyHooks,
    NoopAssetReusePolicyHooks,
    ReusePolicyContext,
    ReusePolicySettings,
    build_decision_policy_metadata,
)
from content_lab_assets.types import (
    BlockedDecision,
    GenerateDecision,
    GenerationIntent,
    ReuseExactDecision,
    ReuseWithTransformDecision,
)


def test_decision_models_expose_future_safe_policy_and_mutation_fields() -> None:
    asset_id = uuid.uuid4()
    asset_key = '{"asset_class":"clip"}'
    asset_key_hash = "abc123"
    asset_class = "clip"
    provider = "runway"
    model = "gen4.5"

    exact = ReuseExactDecision(
        asset_id=asset_id,
        storage_uri="s3://bucket/exact.mp4",
        asset_key=asset_key,
        asset_key_hash=asset_key_hash,
        asset_class=asset_class,
        provider=provider,
        model=model,
    )
    generated = GenerateDecision(
        generation_intent=GenerationIntent(
            asset_id=asset_id,
            asset_status="staged",
            storage_uri="s3://bucket/pending.bin",
            idempotency_key="asset.generate:abc123",
            asset_class=asset_class,
            provider=provider,
            model=model,
            asset_key=asset_key,
            asset_key_hash=asset_key_hash,
        ),
        asset_key=asset_key,
        asset_key_hash=asset_key_hash,
        asset_class=asset_class,
        provider=provider,
        model=model,
    )
    transformed = ReuseWithTransformDecision(
        asset_id=asset_id,
        storage_uri="s3://bucket/source.mp4",
        reason="family cooldown prefers mutation",
        reason_code="cooldown_transform",
        transform_recipe={"kind": "reframe"},
        asset_key=asset_key,
        asset_key_hash=asset_key_hash,
        asset_class=asset_class,
        provider=provider,
        model=model,
    )
    blocked = BlockedDecision(
        reason="family reuse cap reached",
        reason_code="family_reuse_cap",
        retry_after_seconds=3600,
        asset_key=asset_key,
        asset_key_hash=asset_key_hash,
        asset_class=asset_class,
        provider=provider,
        model=model,
    )

    assert exact.policy.active_rules == []
    assert generated.decision == "generate"
    assert transformed.transform_recipe == {"kind": "reframe"}
    assert transformed.reason_code == "cooldown_transform"
    assert blocked.reason_code == "family_reuse_cap"
    assert blocked.retry_after_seconds == 3600


def test_policy_context_shape_captures_cooldown_and_family_cap_hooks() -> None:
    reused_at = datetime(2026, 3, 24, 12, 0, tzinfo=UTC)
    context = ReusePolicyContext(
        family_id="family-hero",
        family_reuse_count=2,
        last_reused_at=reused_at,
        settings=ReusePolicySettings.model_validate(
            {
                "cooldown": {"seconds": 1800},
                "family_reuse_cap": {"max_reuses": 3},
            }
        ),
    )

    metadata = build_decision_policy_metadata(context)

    assert metadata.family_id == "family-hero"
    assert metadata.family_reuse_count == 2
    assert metadata.family_reuse_cap == 3
    assert metadata.cooldown_seconds == 1800
    assert metadata.last_reused_at == reused_at
    assert metadata.active_rules == ["cooldown", "family_reuse_cap"]


def test_noop_policy_hooks_preserve_phase1_exact_and_generate_paths() -> None:
    assert isinstance(NoopAssetReusePolicyHooks(), AssetReusePolicyHooks)
