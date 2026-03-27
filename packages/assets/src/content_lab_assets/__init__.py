"""Asset registry: cataloging, deduplication, and embedding lookup."""

from content_lab_assets.registry import (
    AssetRecord,
    AssetRegistry,
    GenerateDecision,
    Phase1AssetRegistryStore,
    ReuseExactDecision,
    build_generation_idempotency_key,
    is_ready_asset_status,
    resolve_phase1_asset,
)
from content_lab_assets.store import RunwayAssetStore, SQLRunwayAssetStore, StoredRunwayGeneration

__all__ = [
    "AssetRecord",
    "AssetRegistry",
    "GenerateDecision",
    "Phase1AssetRegistryStore",
    "RunwayAssetStore",
    "ReuseExactDecision",
    "SQLRunwayAssetStore",
    "StoredRunwayGeneration",
    "build_generation_idempotency_key",
    "is_ready_asset_status",
    "resolve_phase1_asset",
]
