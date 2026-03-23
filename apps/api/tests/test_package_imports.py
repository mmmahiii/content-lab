"""Smoke tests verifying the refactored package layout is importable."""


def test_import_models() -> None:
    from content_lab_api.models import (
        Asset,
        AuditLog,
        Experiment,
        OutboxEvent,
        Page,
        PolicyState,
        ProviderJob,
        Reel,
        ReelFamily,
        Run,
        RunAsset,
        StorageIntegrityCheck,
        Task,
    )

    assert Asset.__tablename__ == "assets"
    assert Page.__tablename__ == "pages"
    assert ReelFamily.__tablename__ == "reel_families"
    assert Reel.__tablename__ == "reels"
    assert Run.__tablename__ == "runs"
    assert RunAsset.__tablename__ == "run_assets"
    assert OutboxEvent.__tablename__ == "outbox_events"
    assert PolicyState.__tablename__ == "policy_state"
    assert Experiment.__tablename__ == "experiments"
    assert Task.__tablename__ == "tasks"
    assert ProviderJob.__tablename__ == "provider_jobs"
    assert AuditLog.__tablename__ == "audit_log"
    assert StorageIntegrityCheck.__tablename__ == "storage_integrity_checks"
    assert "asset_class" in Asset.__table__.c
    assert "source" in Asset.__table__.c
    assert "asset_key" in Asset.__table__.c
    assert "content_hash" in Asset.__table__.c
    assert "phash" in Asset.__table__.c
    assert "status" in Asset.__table__.c
    assert "storage_uri" in Asset.__table__.c
    assert "asset_key_hash" in Asset.__table__.c
    assert "family_id" in Asset.__table__.c
    assert "workflow_key" in Run.__table__.c
    assert "flow_trigger" in Run.__table__.c
    assert "idempotency_key" in Run.__table__.c
    assert "run_metadata" in Run.__table__.c
    assert "dispatched_at" in OutboxEvent.__table__.c
    assert "delivery_status" in OutboxEvent.__table__.c
    assert "attempt_count" in OutboxEvent.__table__.c
    assert "next_attempt_at" in OutboxEvent.__table__.c
    assert "asset_role" in RunAsset.__table__.c


def test_import_schemas() -> None:
    from content_lab_api.schemas import (
        AssetCreate,
        AssetDetailOut,
        AssetOut,
        FlowTrigger,
        OutboxEventOut,
        PackageArtifactOut,
        PackageDetailOut,
        PageConstraints,
        PageCreate,
        PageMetadata,
        PageOut,
        PageUpdate,
        PersonaProfile,
        PolicyBudgetGuardrails,
        PolicyModeRatios,
        PolicyScopeType,
        PolicySimilarityThresholds,
        PolicyStateDocument,
        PolicyStateOut,
        PolicyStateUpdate,
        PolicyThresholds,
        ReelCreate,
        ReelFamilyCreate,
        ReelFamilyMode,
        ReelFamilyOut,
        ReelOut,
        ReelPostingInfo,
        ReelReviewInfo,
        ReelTriggerCreate,
        ReelVariantSummary,
        RunCreate,
        RunDetailOut,
        RunOut,
        SignedDownloadOut,
        TaskSummaryOut,
        WorkflowKey,
    )

    for cls in (
        AssetCreate,
        AssetDetailOut,
        AssetOut,
        FlowTrigger,
        OutboxEventOut,
        PageConstraints,
        PageCreate,
        PageMetadata,
        PageOut,
        PageUpdate,
        PersonaProfile,
        PackageArtifactOut,
        PackageDetailOut,
        PolicyBudgetGuardrails,
        PolicyModeRatios,
        PolicyScopeType,
        PolicySimilarityThresholds,
        PolicyStateDocument,
        PolicyStateOut,
        PolicyStateUpdate,
        PolicyThresholds,
        ReelFamilyCreate,
        ReelFamilyMode,
        ReelFamilyOut,
        ReelCreate,
        ReelOut,
        ReelPostingInfo,
        ReelReviewInfo,
        ReelTriggerCreate,
        ReelVariantSummary,
        RunCreate,
        RunDetailOut,
        RunOut,
        SignedDownloadOut,
        TaskSummaryOut,
        WorkflowKey,
    ):
        assert issubclass(cls, object)


def test_import_deps() -> None:
    from content_lab_api.deps import get_db

    assert callable(get_db)


def test_import_routes() -> None:
    from content_lab_api.routes import api_router

    paths = [getattr(r, "path", None) for r in api_router.routes]
    assert "/health" in paths
    assert "/orgs/{org_id}/pages" in paths
    assert "/orgs/{org_id}/pages/{page_id}" in paths
    assert "/orgs/{org_id}/policy/global" in paths
    assert "/orgs/{org_id}/policy/page/{page_id}" in paths
    assert "/orgs/{org_id}/policy/niche/{niche_key}" in paths
    assert "/orgs/{org_id}/pages/{page_id}/reel-families" in paths
    assert "/orgs/{org_id}/pages/{page_id}/reel-families/{family_id}" in paths
    assert "/orgs/{org_id}/pages/{page_id}/reels" in paths
    assert "/orgs/{org_id}/pages/{page_id}/reels/{reel_id}" in paths
    assert "/orgs/{org_id}/pages/{page_id}/reels/{reel_id}/trigger" in paths
    assert "/orgs/{org_id}/runs" in paths
    assert "/orgs/{org_id}/runs/{run_id}" in paths
    assert "/orgs/{org_id}/assets/{asset_id}" in paths
    assert "/orgs/{org_id}/assets/{asset_id}/download" in paths
    assert "/orgs/{org_id}/packages/{run_id}" in paths


def test_import_db_base() -> None:
    from content_lab_api.db import Base

    assert hasattr(Base, "metadata")


def test_entrypoint_app() -> None:
    from content_lab_api.main import app

    assert app.title == "Content Lab API"
