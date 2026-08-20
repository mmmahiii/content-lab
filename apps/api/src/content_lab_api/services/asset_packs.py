"""Asset pack planning and persistence services."""

from __future__ import annotations

import base64
import binascii
import hashlib
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

import httpx
from fastapi import HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import insert
from sqlalchemy.orm import Session

from content_lab_api.models import (
    Asset,
    AssetGenParam,
    AssetPack,
    AssetPackItem,
    AssetPackItemStatus,
    AssetPackStatus,
    AuditLog,
    Org,
    PlannedAssetSpec,
    PlannedAssetSpecStatus,
)
from content_lab_api.schemas.asset_packs import (
    ApprovedAssetPackGenerateRequest,
    AssetPackBatchOut,
    AssetPackBatchRequest,
    AssetPackCreate,
    AssetPackItemOut,
    AssetPackOut,
    AssetPackPlanOut,
    AssetPackPlanRequest,
    AssetPackRegeneratePlanRequest,
    AssetPackReviewDecisionRequest,
    PlannedAssetSpecPlanOut,
    PlannedAssetSpecStatusValue,
    SourceAssetRegisterRequest,
)
from content_lab_api.schemas.assets import ApprovedExternalImportRequest
from content_lab_assets.acquisition import (
    AcquisitionDecision,
    AssetAcquisitionPath,
    acquisition_decision_for_compatible_registry_reuse,
    acquisition_decision_for_operator_upload,
    default_generated_source_metadata,
    evaluate_acquisition_before_generation,
)
from content_lab_assets.canonicalise import serialise_canonical_payload
from content_lab_assets.importer import (
    MAX_APPROVED_IMPORT_BYTES,
    ApprovedImportValidationError,
    assert_safe_http_url_for_fetch,
    usage_metadata_sufficient,
)
from content_lab_assets.planner import AssetPackPlan, generate_asset_pack_plan
from content_lab_assets.registry import (
    AssetSource,
    detect_png_transparency,
    detect_png_visual_metadata,
    validate_asset_kind_media_type,
)
from content_lab_assets.store import AssetMediaMetadata, merge_asset_metadata
from content_lab_assets.types import (
    AssetSourceMetadata,
    AssetSourceType,
    infer_asset_source_type_from_asset_source,
)
from content_lab_shared.logging import ANONYMOUS_ACTOR
from content_lab_shared.settings import Settings
from content_lab_storage import (
    CanonicalStorageLayout,
    S3StorageClient,
    S3StorageConfig,
    checksum_bytes,
    persist_source_asset_bytes,
)

_READY_ASSET_STATUSES = frozenset({"active", "ready"})
_AVAILABLE_ITEM_STATUSES = frozenset(
    {
        AssetPackItemStatus.GENERATED.value,
        AssetPackItemStatus.UPLOADED.value,
        AssetPackItemStatus.IMPORTED.value,
        AssetPackItemStatus.REUSED.value,
        AssetPackItemStatus.SELECTED.value,
    }
)


def _merge_acquisition_into_item_metadata(
    item: AssetPackItem, acquisition: AcquisitionDecision
) -> None:
    item.metadata_json = {
        **dict(item.metadata_json or {}),
        "acquisition_decision": jsonable_encoder(acquisition.model_dump(mode="python")),
    }


def _finalize_acquisition_after_generation(acquisition: AcquisitionDecision) -> AcquisitionDecision:
    if acquisition.recommended_acquisition_path is AssetAcquisitionPath.GENERATE_NEW_ASSET:
        return acquisition.model_copy(
            update={"resolved_acquisition_path": AssetAcquisitionPath.GENERATE_NEW_ASSET}
        )
    if acquisition.recommended_acquisition_path is AssetAcquisitionPath.REUSE_WITH_TRANSFORM:
        return acquisition.model_copy(
            update={
                "resolved_acquisition_path": AssetAcquisitionPath.GENERATE_NEW_ASSET,
                "rationale": (
                    f"{acquisition.rationale} "
                    "Operational fallback: generation used until transform execution is wired."
                ),
            }
        )
    if acquisition.recommended_acquisition_path is AssetAcquisitionPath.USE_APPROVED_EXTERNAL_ASSET:
        return acquisition.model_copy(
            update={
                "resolved_acquisition_path": AssetAcquisitionPath.GENERATE_NEW_ASSET,
                "rationale": (
                    f"{acquisition.rationale} "
                    "Approved external asset was missing, incompatible, or not ready; "
                    "generation used."
                ),
            }
        )
    return acquisition.model_copy(
        update={"resolved_acquisition_path": AssetAcquisitionPath.GENERATE_NEW_ASSET}
    )


def _annotate_acquisition_for_pre_fulfilled_items(
    db: Session,
    *,
    org_id: uuid.UUID,
    persisted_specs: list[PlannedAssetSpec],
    items_by_spec: dict[uuid.UUID, AssetPackItem],
) -> None:
    _ = org_id
    for spec in persisted_specs:
        item = items_by_spec[spec.id]
        if item.asset_id is None:
            continue
        current = dict(item.metadata_json or {})
        if current.get("acquisition_decision"):
            continue
        asset_sel = current.get("asset_selection")
        asset_sel = asset_sel if isinstance(asset_sel, Mapping) else {}

        if asset_sel.get("mode") == "compatible_existing":
            acq = acquisition_decision_for_compatible_registry_reuse(
                planned_asset_spec_id=spec.id,
                match_metadata=dict(asset_sel),
            )
            _merge_acquisition_into_item_metadata(item, acq)
            continue

        if current.get("source_registration"):
            asset = db.get(Asset, item.asset_id)
            sm = _parse_optional_source_metadata(dict(asset.metadata_ or {}) if asset else {})
            acq = acquisition_decision_for_operator_upload(
                planned_asset_spec_id=spec.id,
                asset_id=item.asset_id,
                source_metadata=sm,
            )
            _merge_acquisition_into_item_metadata(item, acq)


def _parse_optional_source_metadata(metadata: Mapping[str, Any]) -> AssetSourceMetadata | None:
    raw = metadata.get("source_metadata")
    if not isinstance(raw, Mapping):
        return None
    try:
        return AssetSourceMetadata.model_validate(raw)
    except ValueError:
        return None


def _apply_acquisition_block_to_item(
    db: Session,
    *,
    item: AssetPackItem,
    spec: PlannedAssetSpec,
    acquisition: AcquisitionDecision,
) -> None:
    item.status = AssetPackItemStatus.FAILED.value
    spec.status = PlannedAssetSpecStatus.FAILED.value
    item.metadata_json = jsonable_encoder(
        {
            **dict(item.metadata_json or {}),
            "selection_source": "failed",
            "acquisition_decision": jsonable_encoder(acquisition.model_dump(mode="python")),
        }
    )
    db.flush()


def _try_attach_acquisition_external_asset(
    db: Session,
    *,
    org_id: uuid.UUID,
    spec: PlannedAssetSpec,
    item: AssetPackItem,
    acquisition: AcquisitionDecision,
) -> bool:
    if acquisition.candidate_asset_id is None:
        return False
    asset = db.get(Asset, acquisition.candidate_asset_id)
    if asset is None or asset.org_id != org_id:
        return False
    if asset.status not in _READY_ASSET_STATUSES:
        return False
    match_meta = _asset_match_metadata(asset)
    if (
        match_meta.get("asset_kind") != spec.asset_kind
        or match_meta.get("media_type") != spec.media_type
    ):
        return False
    item.asset_id = asset.id
    item.status = _existing_asset_item_status(
        {"asset_source": str(match_meta.get("asset_source") or asset.source)}
    )
    item.metadata_json = jsonable_encoder(
        {
            **dict(item.metadata_json or {}),
            "selection_source": item.status,
            "asset_selection": {
                "mode": "approved_external_attach",
                "asset_id": str(asset.id),
                "asset_status": asset.status,
                "asset_source": match_meta.get("asset_source"),
                "matched_on": ["approved_external_asset_id", "asset_kind", "media_type"],
                "score": 10,
            },
        }
    )
    spec.status = PlannedAssetSpecStatus.REGISTERED.value
    return True


def _ensure_source_asset_gen_param(
    db: Session,
    *,
    org_id: uuid.UUID,
    asset: Asset,
    asset_key_hash: str,
    canonical_params: dict[str, Any],
) -> None:
    existing = db.query(AssetGenParam).filter(AssetGenParam.asset_id == asset.id).first()
    if existing is not None:
        return
    db.add(
        AssetGenParam(
            org_id=org_id,
            asset_id=asset.id,
            seq=0,
            asset_key_hash=asset_key_hash,
            canonical_params=dict(canonical_params),
        )
    )
    db.flush()


def register_source_asset_for_pack(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: SourceAssetRegisterRequest,
    storage_client: S3StorageClient | None = None,
    settings: Settings | None = None,
) -> tuple[Asset, AssetPackItem, bool]:
    """Persist user-provided source bytes and attach the ready asset to a pack."""

    _get_org_or_404(db, org_id)
    asset_pack = _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=asset_pack_id)
    planned_spec = _planned_spec_for_source_registration(
        db,
        asset_pack_id=asset_pack_id,
        planned_asset_spec_id=body.planned_asset_spec_id,
    )
    _validate_source_asset_media(body)
    data = _decode_source_asset_data(body.data_base64)
    content_hash = checksum_bytes(data).content_hash
    asset_key, asset_key_hash, canonical_params = _source_asset_key(
        body,
        content_hash=content_hash,
    )
    existing_asset = _source_asset_by_key_hash(
        db,
        org_id=org_id,
        asset_key_hash=asset_key_hash,
    )

    if existing_asset is not None:
        if existing_asset.status not in _READY_ASSET_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A matching source asset is already registered but is not ready",
            )
        _ensure_source_asset_gen_param(
            db,
            org_id=org_id,
            asset=existing_asset,
            asset_key_hash=asset_key_hash,
            canonical_params=canonical_params,
        )
        item = _attach_source_asset_to_pack(
            db,
            asset_pack=asset_pack,
            asset=existing_asset,
            body=body,
            planned_spec=planned_spec,
            reused_existing_asset=True,
        )
        _record_source_registration_audit(
            db,
            request,
            org_id=org_id,
            asset_pack=asset_pack,
            asset=existing_asset,
            item=item,
            reused_existing_asset=True,
        )
        db.commit()
        db.refresh(existing_asset)
        db.refresh(item)
        return existing_asset, item, True

    resolved_settings = settings or Settings()
    asset = _create_staged_source_asset(
        db,
        org_id=org_id,
        body=body,
        content_hash=content_hash,
        asset_key=asset_key,
        asset_key_hash=asset_key_hash,
        canonical_params=canonical_params,
    )
    _ensure_source_asset_gen_param(
        db,
        org_id=org_id,
        asset=asset,
        asset_key_hash=asset_key_hash,
        canonical_params=canonical_params,
    )
    stored = persist_source_asset_bytes(
        client=storage_client or _build_storage_client(resolved_settings),
        layout=CanonicalStorageLayout(bucket=resolved_settings.minio_bucket),
        asset_id=asset.id,
        asset_class=body.asset_class,
        data=data,
        content_type=body.content_type,
        filename=body.filename,
        metadata=_source_object_metadata(asset),
    )
    asset.status = "ready"
    asset.storage_uri = stored.storage_uri
    asset.content_hash = stored.checksums.content_hash
    media_metadata, extracted_metadata = _source_media_metadata(body, data)
    asset.metadata_ = {
        **dict(asset.metadata_ or {}),
        **extracted_metadata,
    }
    asset.metadata_ = merge_asset_metadata(
        asset.metadata_,
        media_metadata=media_metadata,
        state="ready",
        storage_uri=stored.storage_uri,
        content_hash=stored.checksums.content_hash,
        size_bytes=stored.stored_object.size_bytes,
        content_type=stored.stored_object.content_type,
    )
    item = _attach_source_asset_to_pack(
        db,
        asset_pack=asset_pack,
        asset=asset,
        body=body,
        planned_spec=planned_spec,
        reused_existing_asset=False,
    )
    _record_source_registration_audit(
        db,
        request,
        org_id=org_id,
        asset_pack=asset_pack,
        asset=asset,
        item=item,
        reused_existing_asset=False,
    )
    refresh_asset_pack_readiness(db, asset_pack=asset_pack)
    db.commit()
    db.refresh(asset)
    db.refresh(item)
    return asset, item, False


def detach_asset_from_pack(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    asset_id: uuid.UUID,
) -> None:
    """Remove pack membership rows for an asset without deleting the registry Asset."""

    _get_org_or_404(db, org_id)
    asset_pack = _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=asset_pack_id)
    items = (
        db.query(AssetPackItem)
        .filter(
            AssetPackItem.asset_pack_id == asset_pack_id,
            AssetPackItem.asset_id == asset_id,
        )
        .all()
    )
    if not items:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not linked to this pack",
        )
    removed = len(items)
    for item in items:
        db.delete(item)
    _record_asset_pack_audit(
        db,
        request,
        org_id=org_id,
        asset_pack=asset_pack,
        action="asset_pack.asset.detached",
        payload={"asset_id": str(asset_id), "removed_items": removed},
    )
    refresh_asset_pack_readiness(db, asset_pack=asset_pack)
    db.commit()


def _download_approved_external_url(url: str) -> tuple[bytes, str | None]:
    assert_safe_http_url_for_fetch(url)
    try:
        with (
            httpx.Client(timeout=120.0, follow_redirects=True, verify=True) as client,
            client.stream("GET", url) as response,
        ):
            response.raise_for_status()
            total = 0
            parts: list[bytes] = []
            for chunk in response.iter_bytes(64 * 1024):
                total += len(chunk)
                if total > MAX_APPROVED_IMPORT_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Download exceeds maximum approved import size",
                    )
                parts.append(chunk)
            data = b"".join(parts)
            raw_ct = response.headers.get("content-type")
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to fetch external asset: {exc}",
        ) from exc
    content_type = raw_ct.split(";")[0].strip() if raw_ct else None
    return data, content_type


def _register_imported_source_org_only(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    body: SourceAssetRegisterRequest,
    data: bytes,
    storage_client: S3StorageClient | None,
    settings: Settings,
) -> tuple[Asset, bool]:
    """Persist imported bytes without an asset pack (registry-only)."""

    content_hash = checksum_bytes(data).content_hash
    asset_key, asset_key_hash, canonical_params = _source_asset_key(
        body,
        content_hash=content_hash,
    )
    existing_asset = _source_asset_by_key_hash(
        db,
        org_id=org_id,
        asset_key_hash=asset_key_hash,
    )
    if existing_asset is not None:
        if existing_asset.status not in _READY_ASSET_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A matching imported asset exists but is not ready",
            )
        _ensure_source_asset_gen_param(
            db,
            org_id=org_id,
            asset=existing_asset,
            asset_key_hash=asset_key_hash,
            canonical_params=canonical_params,
        )
        db.commit()
        db.refresh(existing_asset)
        return existing_asset, True

    asset = _create_staged_source_asset(
        db,
        org_id=org_id,
        body=body,
        content_hash=content_hash,
        asset_key=asset_key,
        asset_key_hash=asset_key_hash,
        canonical_params=canonical_params,
    )
    _ensure_source_asset_gen_param(
        db,
        org_id=org_id,
        asset=asset,
        asset_key_hash=asset_key_hash,
        canonical_params=canonical_params,
    )
    stored = persist_source_asset_bytes(
        client=storage_client or _build_storage_client(settings),
        layout=CanonicalStorageLayout(bucket=settings.minio_bucket),
        asset_id=asset.id,
        asset_class=body.asset_class,
        data=data,
        content_type=body.content_type,
        filename=body.filename,
        metadata=_source_object_metadata(asset),
    )
    asset.status = "ready"
    asset.storage_uri = stored.storage_uri
    asset.content_hash = stored.checksums.content_hash
    media_metadata, extracted_metadata = _source_media_metadata(body, data)
    asset.metadata_ = {
        **dict(asset.metadata_ or {}),
        **extracted_metadata,
    }
    asset.metadata_ = merge_asset_metadata(
        asset.metadata_,
        media_metadata=media_metadata,
        state="ready",
        storage_uri=stored.storage_uri,
        content_hash=stored.checksums.content_hash,
        size_bytes=stored.stored_object.size_bytes,
        content_type=stored.stored_object.content_type,
    )
    actor = getattr(request.state, "actor", ANONYMOUS_ACTOR)
    actor_id = None if actor == ANONYMOUS_ACTOR else actor
    db.execute(
        insert(AuditLog).values(
            id=uuid.uuid4(),
            org_id=org_id,
            action="asset.import.approved_external",
            resource_type="asset",
            actor_type="anonymous" if actor_id is None else "request_header",
            actor_id=actor_id,
            resource_id=str(asset.id),
            payload={
                "asset_key_hash": asset.asset_key_hash,
                "content_hash": asset.content_hash,
                "external_source_url": (asset.metadata_ or {})
                .get("source_metadata", {})
                .get("external_source_url"),
            },
        )
    )
    db.commit()
    db.refresh(asset)
    return asset, False


def import_approved_external_asset(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    body: ApprovedExternalImportRequest,
    settings: Settings | None = None,
) -> tuple[Asset, AssetPackItem | None, bool, list[str], bool]:
    """Operator-initiated import of an approved URL into canonical registry storage."""

    _get_org_or_404(db, org_id)
    resolved_settings = settings or Settings()
    actor = getattr(request.state, "actor", ANONYMOUS_ACTOR)
    actor_id = None if actor == ANONYMOUS_ACTOR else str(actor)

    sm = body.source_metadata.model_copy(
        update={
            "external_source_url": body.external_source_url.strip(),
            "source_type": AssetSourceType.APPROVED_EXTERNAL_SOURCE,
            "imported_at": datetime.now(UTC),
            "imported_by": actor_id or "anonymous",
        }
    )
    licence_complete, warning_codes = usage_metadata_sufficient(
        usage_rights_confirmed=body.usage_rights_confirmed,
        licence_type=sm.licence_type,
        licence_notes=sm.licence_notes,
        usage_allowed=sm.usage_allowed,
        attribution_required=sm.attribution_required,
        attribution_text=sm.attribution_text,
    )
    try:
        data, content_type = _download_approved_external_url(body.external_source_url.strip())
    except ApprovedImportValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    meta_payload = {
        **body.metadata,
        "import_validation": {
            "licence_metadata_complete": licence_complete,
            "warnings": warning_codes,
        },
        "source_metadata": sm.model_dump(mode="python", exclude_none=True),
    }
    if not licence_complete:
        meta_payload["import_flags"] = {"incomplete_licence_metadata": True}

    reg_body = SourceAssetRegisterRequest(
        asset_class=body.asset_class,
        asset_kind=body.asset_kind,
        media_type=body.media_type,
        asset_source=AssetSource.IMPORTED,
        pack_role=body.pack_role,
        reuse_purpose=None,
        priority=0,
        planned_asset_spec_id=body.planned_asset_spec_id,
        filename=body.filename,
        content_type=content_type,
        data_base64=base64.b64encode(data).decode("ascii"),
        metadata=meta_payload,
        source_metadata=sm,
    )
    _validate_source_asset_media(reg_body)

    if body.planned_asset_pack_id is not None:
        asset, item, reused = register_source_asset_for_pack(
            db,
            request,
            org_id=org_id,
            asset_pack_id=body.planned_asset_pack_id,
            body=reg_body,
            settings=resolved_settings,
        )
        return asset, item, reused, list(warning_codes), licence_complete

    asset, reused = _register_imported_source_org_only(
        db,
        request,
        org_id=org_id,
        body=reg_body,
        data=data,
        storage_client=None,
        settings=resolved_settings,
    )
    return asset, None, reused, list(warning_codes), licence_complete


def create_asset_pack(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    body: AssetPackCreate,
) -> AssetPackOut:
    """Create a draft asset pack before planning."""

    _get_org_or_404(db, org_id)
    asset_pack = AssetPack(
        org_id=org_id,
        name=body.name,
        niche=body.niche,
        purpose=body.purpose,
        target_audience=body.target_audience,
        requested_asset_count=body.requested_asset_count,
        asset_mix_requested_json=body.asset_mix_requested_json,
        strategy_summary=body.strategy_summary,
        status=AssetPackStatus.DRAFT.value,
    )
    db.add(asset_pack)
    db.flush()
    _record_asset_pack_audit(
        db,
        request,
        org_id=org_id,
        asset_pack=asset_pack,
        action="asset_pack.created",
        payload={
            "requested_asset_count": asset_pack.requested_asset_count,
            "asset_mix_requested_json": asset_pack.asset_mix_requested_json,
            "status": asset_pack.status,
        },
    )
    db.commit()
    db.refresh(asset_pack)
    return AssetPackOut.model_validate(asset_pack)


def plan_existing_asset_pack(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: AssetPackPlanRequest,
) -> AssetPackPlanOut:
    """Generate or replace the plan for an existing draft/reviewable asset pack."""

    _get_org_or_404(db, org_id)
    asset_pack = _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=asset_pack_id)
    if asset_pack.status not in {
        AssetPackStatus.DRAFT.value,
        AssetPackStatus.PLANNED.value,
        AssetPackStatus.APPROVED.value,
        AssetPackStatus.REJECTED.value,
    }:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only draft or ungenerated asset packs can be planned",
        )

    plan = generate_asset_pack_plan(
        niche=body.niche,
        target_audience=body.target_audience,
        requested_asset_count=body.requested_asset_count,
        asset_mix=body.asset_mix,
        target_reel_types=body.target_reel_types,
        style_persona_constraints=body.style_persona_constraints,
    )
    _replace_plan_rows(db, asset_pack=asset_pack, body=body, plan=plan)
    persisted_specs = _planned_specs_for_pack(db, asset_pack_id=asset_pack.id)
    items_by_spec = _items_by_planned_spec(db, asset_pack_id=asset_pack.id)
    _attach_existing_assets(
        db,
        org_id=org_id,
        asset_pack=asset_pack,
        persisted_specs=persisted_specs,
        items_by_spec=items_by_spec,
    )
    _annotate_acquisition_for_pre_fulfilled_items(
        db,
        org_id=org_id,
        persisted_specs=persisted_specs,
        items_by_spec=items_by_spec,
    )
    refresh_asset_pack_readiness(db, asset_pack=asset_pack)
    planning_summary = _resolution_summary(db, asset_pack_id=asset_pack.id)
    _record_plan_audit(
        db,
        request,
        org_id=org_id,
        asset_pack=asset_pack,
        plan=plan,
        action="asset_pack.plan.created",
    )
    db.commit()
    db.refresh(asset_pack)
    persisted_specs = _planned_specs_for_pack(db, asset_pack_id=asset_pack.id)
    return _plan_out(
        asset_pack=asset_pack,
        plan=plan,
        persisted_specs=persisted_specs,
        planning_resolution_summary=planning_summary,
    )


def create_asset_pack_plan(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    body: AssetPackPlanRequest,
) -> AssetPackPlanOut:
    """Generate and store an asset pack plan before generation begins."""

    _get_org_or_404(db, org_id)
    asset_pack, plan, persisted_specs = _create_plan_rows(db, org_id=org_id, body=body)
    items_by_spec = _items_by_planned_spec(db, asset_pack_id=asset_pack.id)
    _attach_existing_assets(
        db,
        org_id=org_id,
        asset_pack=asset_pack,
        persisted_specs=persisted_specs,
        items_by_spec=items_by_spec,
    )
    _annotate_acquisition_for_pre_fulfilled_items(
        db,
        org_id=org_id,
        persisted_specs=persisted_specs,
        items_by_spec=items_by_spec,
    )
    refresh_asset_pack_readiness(db, asset_pack=asset_pack)
    planning_summary = _resolution_summary(db, asset_pack_id=asset_pack.id)
    _record_plan_audit(
        db,
        request,
        org_id=org_id,
        asset_pack=asset_pack,
        plan=plan,
    )
    db.commit()
    db.refresh(asset_pack)
    for spec in persisted_specs:
        db.refresh(spec)

    return _plan_out(
        asset_pack=asset_pack,
        plan=plan,
        persisted_specs=persisted_specs,
        planning_resolution_summary=planning_summary,
    )


def approve_asset_pack_plan(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: AssetPackReviewDecisionRequest,
) -> AssetPackOut:
    """Approve a planned pack for generation or later use."""

    _get_org_or_404(db, org_id)
    asset_pack = _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=asset_pack_id)
    if asset_pack.status != AssetPackStatus.PLANNED.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only planned asset packs can be approved",
        )
    asset_pack.status = AssetPackStatus.APPROVED.value
    _record_review_audit(
        db,
        request,
        org_id=org_id,
        asset_pack=asset_pack,
        action="asset_pack.plan.approved",
        body=body,
    )
    db.commit()
    db.refresh(asset_pack)
    return AssetPackOut.model_validate(asset_pack)


def reject_asset_pack_plan(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: AssetPackReviewDecisionRequest,
) -> AssetPackOut:
    """Reject a draft, planned, or approved pack before generation."""

    _get_org_or_404(db, org_id)
    asset_pack = _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=asset_pack_id)
    if asset_pack.status not in {
        AssetPackStatus.DRAFT.value,
        AssetPackStatus.PLANNED.value,
        AssetPackStatus.APPROVED.value,
    }:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only draft, planned, or approved asset packs can be rejected",
        )
    asset_pack.status = AssetPackStatus.REJECTED.value
    _record_review_audit(
        db,
        request,
        org_id=org_id,
        asset_pack=asset_pack,
        action="asset_pack.plan.rejected",
        body=body,
    )
    db.commit()
    db.refresh(asset_pack)
    return AssetPackOut.model_validate(asset_pack)


def regenerate_asset_pack_plan(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: AssetPackRegeneratePlanRequest,
) -> AssetPackPlanOut:
    """Edit requested pack inputs and replace planned specs before generation."""

    _get_org_or_404(db, org_id)
    asset_pack = _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=asset_pack_id)
    if asset_pack.status not in {
        AssetPackStatus.PLANNED.value,
        AssetPackStatus.APPROVED.value,
        AssetPackStatus.REJECTED.value,
    }:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only ungenerated asset packs can regenerate their plan",
        )

    plan = generate_asset_pack_plan(
        niche=body.niche,
        target_audience=body.target_audience,
        requested_asset_count=body.requested_asset_count,
        asset_mix=body.asset_mix,
        target_reel_types=body.target_reel_types,
        style_persona_constraints=body.style_persona_constraints,
    )
    _replace_plan_rows(db, asset_pack=asset_pack, body=body, plan=plan)
    persisted_specs = _planned_specs_for_pack(db, asset_pack_id=asset_pack.id)
    items_by_spec = _items_by_planned_spec(db, asset_pack_id=asset_pack.id)
    _attach_existing_assets(
        db,
        org_id=org_id,
        asset_pack=asset_pack,
        persisted_specs=persisted_specs,
        items_by_spec=items_by_spec,
    )
    _annotate_acquisition_for_pre_fulfilled_items(
        db,
        org_id=org_id,
        persisted_specs=persisted_specs,
        items_by_spec=items_by_spec,
    )
    refresh_asset_pack_readiness(db, asset_pack=asset_pack)
    planning_summary = _resolution_summary(db, asset_pack_id=asset_pack.id)
    _record_plan_audit(
        db,
        request,
        org_id=org_id,
        asset_pack=asset_pack,
        plan=plan,
        action="asset_pack.plan.regenerated",
    )
    db.commit()
    db.refresh(asset_pack)
    persisted_specs = _planned_specs_for_pack(db, asset_pack_id=asset_pack.id)
    return _plan_out(
        asset_pack=asset_pack,
        plan=plan,
        persisted_specs=persisted_specs,
        planning_resolution_summary=planning_summary,
    )


def generate_approved_asset_pack(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: ApprovedAssetPackGenerateRequest,
) -> AssetPackBatchOut:
    """Resolve reusable assets and generation intents for an approved pack."""

    _get_org_or_404(db, org_id)
    asset_pack = _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=asset_pack_id)
    if asset_pack.status != AssetPackStatus.APPROVED.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Asset pack must be approved before generation",
        )
    if body.ready_threshold is not None and body.ready_threshold > asset_pack.requested_asset_count:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ready_threshold must be less than or equal to requested_asset_count",
        )

    persisted_specs = _planned_specs_for_pack(db, asset_pack_id=asset_pack.id)
    items_by_spec = _items_by_planned_spec(db, asset_pack_id=asset_pack.id)
    if body.allow_existing_reuse:
        _attach_existing_assets(
            db,
            org_id=org_id,
            asset_pack=asset_pack,
            persisted_specs=persisted_specs,
            items_by_spec=items_by_spec,
        )

    _annotate_acquisition_for_pre_fulfilled_items(
        db,
        org_id=org_id,
        persisted_specs=persisted_specs,
        items_by_spec=items_by_spec,
    )

    asset_pack.status = AssetPackStatus.GENERATING.value
    refresh_asset_pack_readiness(
        db,
        asset_pack=asset_pack,
        ready_threshold=body.ready_threshold,
    )
    db.commit()

    generation_decisions: list[dict[str, Any]] = []
    for spec in sorted(persisted_specs, key=lambda item: item.priority):
        item = items_by_spec[spec.id]
        if item.asset_id is not None:
            continue
        acquisition = evaluate_acquisition_before_generation(
            planned_asset_spec_id=spec.id,
            required_traits=spec.required_traits or {},
            compatible_with=spec.compatible_with or {},
            pack_niche=asset_pack.niche,
            asset_kind=spec.asset_kind,
            media_type=spec.media_type,
            purpose=spec.purpose,
            prompt_or_description=spec.prompt_or_description,
        )
        if acquisition.recommended_acquisition_path is AssetAcquisitionPath.BLOCK_OR_REPLACE_ASSET:
            _apply_acquisition_block_to_item(db, item=item, spec=spec, acquisition=acquisition)
            generation_decisions.append(jsonable_encoder(acquisition.model_dump(mode="python")))
            continue
        if (
            acquisition.recommended_acquisition_path
            is AssetAcquisitionPath.USE_APPROVED_EXTERNAL_ASSET
            and _try_attach_acquisition_external_asset(
                db,
                org_id=org_id,
                spec=spec,
                item=item,
                acquisition=acquisition,
            )
        ):
            acquisition = acquisition.model_copy(
                update={
                    "resolved_acquisition_path": AssetAcquisitionPath.USE_APPROVED_EXTERNAL_ASSET
                }
            )
            _merge_acquisition_into_item_metadata(item, acquisition)
            generation_decisions.append(jsonable_encoder(acquisition.model_dump(mode="python")))
            db.flush()
            continue
        decision = _resolve_planned_spec_generation(
            db,
            request,
            org_id=org_id,
            asset_pack=asset_pack,
            item=item,
            spec=spec,
            body=body,
        )
        finalized = _finalize_acquisition_after_generation(acquisition)
        decision["acquisition_decision"] = jsonable_encoder(finalized.model_dump(mode="python"))
        generation_decisions.append(jsonable_encoder(decision))
        _apply_resolution_to_item(db, item=item, spec=spec, decision=decision)

    refresh_asset_pack_readiness(
        db,
        asset_pack=asset_pack,
        ready_threshold=body.ready_threshold,
    )
    _record_batch_audit(
        db,
        request,
        org_id=org_id,
        asset_pack=asset_pack,
        summary=_resolution_summary(db, asset_pack_id=asset_pack.id),
    )
    db.commit()
    return _batch_out_from_rows(
        db,
        asset_pack_id=asset_pack.id,
        persisted_specs=persisted_specs,
        generation_decisions=generation_decisions,
    )


def create_asset_pack_batch(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    body: AssetPackBatchRequest,
) -> AssetPackBatchOut:
    """Plan a niche asset pack and resolve each item into reuse or generation."""

    _ = (db, request, org_id, body)
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "Direct asset pack generation is disabled; create a plan, approve it, "
            "then generate the approved pack"
        ),
    )


def ensure_asset_pack_generation_is_planned(
    db: Session,
    *,
    org_id: uuid.UUID,
    metadata: dict[str, Any],
) -> None:
    """Guard pack generation calls so every item points to a stored planned spec."""

    raw_pack_id = metadata.get("asset_pack_id")
    if raw_pack_id is None:
        return
    try:
        asset_pack_id = uuid.UUID(str(raw_pack_id))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="metadata.asset_pack_id must be a UUID",
        ) from exc

    asset_pack = (
        db.query(AssetPack)
        .filter(AssetPack.org_id == org_id, AssetPack.id == asset_pack_id)
        .one_or_none()
    )
    if asset_pack is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset pack not found")

    raw_spec_id = metadata.get("planned_asset_spec_id")
    if raw_spec_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Asset pack generation requires metadata.planned_asset_spec_id",
        )
    try:
        planned_asset_spec_id = uuid.UUID(str(raw_spec_id))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="metadata.planned_asset_spec_id must be a UUID",
        ) from exc

    planned_spec = (
        db.query(PlannedAssetSpec)
        .filter(
            PlannedAssetSpec.asset_pack_id == asset_pack_id,
            PlannedAssetSpec.id == planned_asset_spec_id,
        )
        .one_or_none()
    )
    if planned_spec is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="planned_asset_spec_id must belong to the asset pack",
        )
    if planned_spec.status not in {
        PlannedAssetSpecStatus.PLANNED.value,
        PlannedAssetSpecStatus.GENERATING.value,
    }:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="planned asset spec is not ready for generation",
        )
    if asset_pack.status not in {
        AssetPackStatus.APPROVED.value,
        AssetPackStatus.GENERATING.value,
    }:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Asset pack must be approved before generation",
        )


def mark_asset_pack_asset_ready(db: Session, *, asset: Asset) -> None:
    """Mark generated pack items ready when a staged asset is persisted."""

    items = db.query(AssetPackItem).filter(AssetPackItem.asset_id == asset.id).all()
    for item in items:
        if item.status in {AssetPackItemStatus.PLANNED.value, AssetPackItemStatus.GENERATING.value}:
            item.status = AssetPackItemStatus.GENERATED.value
        item.metadata_json = {
            **dict(item.metadata_json or {}),
            "selection_source": "generated",
            "asset_ready": True,
        }
        if item.planned_asset_spec is not None:
            item.planned_asset_spec.status = PlannedAssetSpecStatus.REGISTERED.value
        if item.asset_pack is not None:
            refresh_asset_pack_readiness(db, asset_pack=item.asset_pack)


def mark_asset_pack_asset_failed(db: Session, *, asset: Asset) -> None:
    """Mark generated pack items failed when asset persistence fails."""

    items = db.query(AssetPackItem).filter(AssetPackItem.asset_id == asset.id).all()
    for item in items:
        if item.status in {AssetPackItemStatus.PLANNED.value, AssetPackItemStatus.GENERATING.value}:
            item.status = AssetPackItemStatus.FAILED.value
        item.metadata_json = {
            **dict(item.metadata_json or {}),
            "selection_source": "generated",
            "asset_ready": False,
        }
        if item.planned_asset_spec is not None:
            item.planned_asset_spec.status = PlannedAssetSpecStatus.FAILED.value
        if item.asset_pack is not None:
            refresh_asset_pack_readiness(db, asset_pack=item.asset_pack)


def refresh_asset_pack_readiness(
    db: Session,
    *,
    asset_pack: AssetPack,
    ready_threshold: int | None = None,
) -> None:
    """Move a pack to ready once enough linked assets are available."""

    threshold = ready_threshold or asset_pack.requested_asset_count
    ready_count = (
        db.query(AssetPackItem)
        .join(Asset, Asset.id == AssetPackItem.asset_id)
        .filter(
            AssetPackItem.asset_pack_id == asset_pack.id,
            AssetPackItem.status.in_(_AVAILABLE_ITEM_STATUSES),
            Asset.status.in_(_READY_ASSET_STATUSES),
        )
        .count()
    )
    if ready_count >= threshold:
        if asset_pack.status not in {
            AssetPackStatus.DRAFT.value,
            AssetPackStatus.PLANNED.value,
            AssetPackStatus.APPROVED.value,
            AssetPackStatus.REJECTED.value,
        }:
            asset_pack.status = AssetPackStatus.READY.value
        return

    failed_count = (
        db.query(AssetPackItem)
        .filter(
            AssetPackItem.asset_pack_id == asset_pack.id,
            AssetPackItem.status == AssetPackItemStatus.FAILED.value,
        )
        .count()
    )
    if ready_count + failed_count >= asset_pack.requested_asset_count:
        asset_pack.status = AssetPackStatus.FAILED.value
        return

    if asset_pack.status not in {
        AssetPackStatus.DRAFT.value,
        AssetPackStatus.PLANNED.value,
        AssetPackStatus.APPROVED.value,
        AssetPackStatus.REJECTED.value,
    }:
        asset_pack.status = AssetPackStatus.GENERATING.value


def _get_org_or_404(db: Session, org_id: uuid.UUID) -> Org:
    org = db.get(Org, org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Org not found")
    return org


def _get_asset_pack_or_404(
    db: Session,
    *,
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
) -> AssetPack:
    asset_pack = (
        db.query(AssetPack)
        .filter(AssetPack.org_id == org_id, AssetPack.id == asset_pack_id)
        .one_or_none()
    )
    if asset_pack is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset pack not found")
    return asset_pack


def _planned_spec_for_source_registration(
    db: Session,
    *,
    asset_pack_id: uuid.UUID,
    planned_asset_spec_id: uuid.UUID | None,
) -> PlannedAssetSpec | None:
    if planned_asset_spec_id is None:
        return None
    planned_spec = (
        db.query(PlannedAssetSpec)
        .filter(
            PlannedAssetSpec.asset_pack_id == asset_pack_id,
            PlannedAssetSpec.id == planned_asset_spec_id,
        )
        .one_or_none()
    )
    if planned_spec is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="planned_asset_spec_id must belong to the asset pack",
        )
    return planned_spec


def _validate_source_asset_media(body: SourceAssetRegisterRequest) -> None:
    if body.media_type is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="media_type could not be inferred for asset_kind",
        )
    try:
        validate_asset_kind_media_type(asset_kind=body.asset_kind, media_type=body.media_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


def _decode_source_asset_data(data_base64: str) -> bytes:
    try:
        return base64.b64decode(data_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="data_base64 must be valid base64-encoded asset bytes",
        ) from exc


def _source_asset_key(
    body: SourceAssetRegisterRequest,
    *,
    content_hash: str,
) -> tuple[str, str, dict[str, Any]]:
    canonical_params = {
        "asset_class": " ".join(body.asset_class.strip().lower().split()),
        "asset_kind": body.asset_kind.value,
        "media_type": body.media_type.value if body.media_type is not None else None,
        "asset_source": body.asset_source.value,
        "content_hash": content_hash.lower(),
    }
    asset_key = serialise_canonical_payload(canonical_params)
    asset_key_hash = hashlib.sha256(asset_key.encode("utf-8")).hexdigest()
    return asset_key, asset_key_hash, canonical_params


def _source_asset_by_key_hash(
    db: Session,
    *,
    org_id: uuid.UUID,
    asset_key_hash: str,
) -> Asset | None:
    return (
        db.query(Asset)
        .filter(Asset.org_id == org_id, Asset.asset_key_hash == asset_key_hash)
        .one_or_none()
    )


def _create_staged_source_asset(
    db: Session,
    *,
    org_id: uuid.UUID,
    body: SourceAssetRegisterRequest,
    content_hash: str,
    asset_key: str,
    asset_key_hash: str,
    canonical_params: dict[str, Any],
) -> Asset:
    metadata = _source_asset_metadata(
        body,
        content_hash=content_hash,
        canonical_params=canonical_params,
    )
    asset = Asset(
        org_id=org_id,
        asset_class=body.asset_class,
        storage_uri="s3://content-lab/assets/raw/pending/source.bin",
        source=body.asset_source.value,
        status="staged",
        asset_key=asset_key,
        asset_key_hash=asset_key_hash,
        content_hash=content_hash,
        metadata_=metadata,
    )
    db.add(asset)
    db.flush()
    return asset


def _source_asset_metadata(
    body: SourceAssetRegisterRequest,
    *,
    content_hash: str,
    canonical_params: dict[str, Any],
) -> dict[str, Any]:
    source_meta = body.source_metadata
    if source_meta is None:
        source_meta = AssetSourceMetadata(
            source_type=infer_asset_source_type_from_asset_source(body.asset_source)
        )
    metadata = {
        **dict(body.metadata or {}),
        "asset_kind": body.asset_kind.value,
        "media_type": None if body.media_type is None else body.media_type.value,
        "asset_source": body.asset_source.value,
        "pack_role": body.pack_role,
        "source_metadata": source_meta.model_dump(mode="python", exclude_none=True),
        "source_registration": {
            "filename": body.filename,
            "content_type": body.content_type,
            "content_hash": content_hash,
            "canonical_params": canonical_params,
        },
    }
    if body.reuse_purpose is not None:
        metadata["reuse_purpose"] = body.reuse_purpose
    return cast(dict[str, Any], jsonable_encoder(metadata))


def _source_media_metadata(
    body: SourceAssetRegisterRequest,
    data: bytes,
) -> tuple[AssetMediaMetadata, dict[str, Any]]:
    width = body.width
    height = body.height
    extracted: dict[str, Any] = {}
    if body.content_type == "image/png" or (body.filename or "").lower().endswith(".png"):
        visual = detect_png_visual_metadata(data)
        if visual is not None:
            width = width or visual.width
            height = height or visual.height
            extracted["visual"] = visual.model_dump(mode="python", exclude_none=True)
        transparency = detect_png_transparency(data)
        extracted["transparency"] = transparency.model_dump(mode="python", exclude_none=True)

    return (
        AssetMediaMetadata(
            width=width,
            height=height,
            fps=None if body.fps is None else int(body.fps),
            duration_seconds=body.duration_seconds,
        ),
        extracted,
    )


def _attach_source_asset_to_pack(
    db: Session,
    *,
    asset_pack: AssetPack,
    asset: Asset,
    body: SourceAssetRegisterRequest,
    planned_spec: PlannedAssetSpec | None,
    reused_existing_asset: bool,
) -> AssetPackItem:
    item = None
    if planned_spec is not None:
        item = (
            db.query(AssetPackItem)
            .filter(
                AssetPackItem.asset_pack_id == asset_pack.id,
                AssetPackItem.planned_asset_spec_id == planned_spec.id,
            )
            .one_or_none()
        )

    item_status = _source_pack_item_status(body.asset_source)
    metadata_json = jsonable_encoder(
        {
            **dict(body.metadata or {}),
            "selection_source": item_status,
            "asset_ready": asset.status in _READY_ASSET_STATUSES,
            "source_registration": {
                "reused_existing_asset": reused_existing_asset,
                "asset_id": str(asset.id),
                "content_hash": asset.content_hash,
                "filename": body.filename,
                "content_type": body.content_type,
            },
        }
    )

    if item is None:
        item = AssetPackItem(
            asset_pack_id=asset_pack.id,
            asset_id=asset.id,
            planned_asset_spec_id=None if planned_spec is None else planned_spec.id,
            asset_kind=body.asset_kind.value,
            pack_role=body.pack_role,
            reuse_purpose=body.reuse_purpose,
            priority=body.priority,
            status=item_status,
            metadata_json=metadata_json,
            compatibility_metadata={}
            if planned_spec is None
            else dict(planned_spec.compatibility_metadata or {}),
        )
        db.add(item)
    else:
        item.asset_id = asset.id
        item.asset_kind = body.asset_kind.value
        item.pack_role = body.pack_role
        item.reuse_purpose = body.reuse_purpose
        item.priority = body.priority
        item.status = item_status
        item.metadata_json = {**dict(item.metadata_json or {}), **metadata_json}
        if planned_spec is not None:
            item.compatibility_metadata = dict(planned_spec.compatibility_metadata or {})

    if planned_spec is not None:
        planned_spec.status = PlannedAssetSpecStatus.REGISTERED.value
    refresh_asset_pack_readiness(db, asset_pack=asset_pack)
    db.flush()
    return item


def _source_pack_item_status(asset_source: AssetSource) -> str:
    if asset_source is AssetSource.UPLOADED:
        return AssetPackItemStatus.UPLOADED.value
    if asset_source is AssetSource.IMPORTED:
        return AssetPackItemStatus.IMPORTED.value
    return AssetPackItemStatus.SELECTED.value


def _record_source_registration_audit(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    asset_pack: AssetPack,
    asset: Asset,
    item: AssetPackItem,
    reused_existing_asset: bool,
) -> None:
    actor = getattr(request.state, "actor", ANONYMOUS_ACTOR)
    actor_id = None if actor == ANONYMOUS_ACTOR else actor
    actor_type = "anonymous" if actor_id is None else "request_header"
    db.execute(
        insert(AuditLog).values(
            id=uuid.uuid4(),
            org_id=org_id,
            action="asset_pack.source_asset.registered",
            resource_type="asset_pack",
            actor_type=actor_type,
            actor_id=actor_id,
            resource_id=str(asset_pack.id),
            payload={
                "asset_id": str(asset.id),
                "asset_pack_item_id": str(item.id),
                "asset_source": asset.source,
                "asset_key_hash": asset.asset_key_hash,
                "content_hash": asset.content_hash,
                "reused_existing_asset": reused_existing_asset,
            },
        )
    )


def _source_object_metadata(asset: Asset) -> dict[str, str]:
    meta = dict(asset.metadata_ or {})
    sm = meta.get("source_metadata")
    out: dict[str, str] = {
        "asset-class": asset.asset_class,
        "asset-id": str(asset.id),
        "org-id": str(asset.org_id),
        "asset-source": asset.source,
    }
    if isinstance(sm, Mapping) and sm.get("source_type") is not None:
        out["source-type"] = str(sm["source_type"])
    return out


def _build_storage_client(settings: Settings) -> S3StorageClient:
    return S3StorageClient(
        S3StorageConfig(
            endpoint=settings.minio_endpoint,
            access_key_id=settings.minio_root_user,
            secret_access_key=settings.minio_root_password.get_secret_value(),
            default_bucket=settings.minio_bucket,
        )
    )


def _create_plan_rows(
    db: Session,
    *,
    org_id: uuid.UUID,
    body: AssetPackPlanRequest,
) -> tuple[AssetPack, AssetPackPlan, list[PlannedAssetSpec]]:
    plan = generate_asset_pack_plan(
        niche=body.niche,
        target_audience=body.target_audience,
        requested_asset_count=body.requested_asset_count,
        asset_mix=body.asset_mix,
        target_reel_types=body.target_reel_types,
        style_persona_constraints=body.style_persona_constraints,
    )
    asset_pack = AssetPack(
        org_id=org_id,
        name=body.name or f"{body.niche.title()} asset pack",
        niche=body.niche,
        purpose=body.purpose,
        target_audience=body.target_audience,
        requested_asset_count=body.requested_asset_count,
        asset_mix_requested_json=body.asset_mix,
        asset_mix_final_json=plan.asset_mix,
        status=AssetPackStatus.PLANNED.value,
        strategy_summary=plan.strategy_summary,
    )
    db.add(asset_pack)
    db.flush()
    persisted_specs = _persist_planned_specs(db, asset_pack=asset_pack, plan=plan)
    return asset_pack, plan, persisted_specs


def _replace_plan_rows(
    db: Session,
    *,
    asset_pack: AssetPack,
    body: AssetPackPlanRequest | AssetPackRegeneratePlanRequest,
    plan: AssetPackPlan,
) -> None:
    db.query(AssetPackItem).filter(AssetPackItem.asset_pack_id == asset_pack.id).delete(
        synchronize_session=False
    )
    db.query(PlannedAssetSpec).filter(PlannedAssetSpec.asset_pack_id == asset_pack.id).delete(
        synchronize_session=False
    )
    asset_pack.name = body.name or asset_pack.name
    asset_pack.niche = body.niche
    asset_pack.purpose = body.purpose
    asset_pack.target_audience = body.target_audience
    asset_pack.requested_asset_count = body.requested_asset_count
    asset_pack.asset_mix_requested_json = body.asset_mix
    asset_pack.asset_mix_final_json = plan.asset_mix
    asset_pack.status = AssetPackStatus.PLANNED.value
    asset_pack.strategy_summary = plan.strategy_summary
    db.flush()
    _persist_planned_specs(db, asset_pack=asset_pack, plan=plan)


def _persist_planned_specs(
    db: Session,
    *,
    asset_pack: AssetPack,
    plan: AssetPackPlan,
) -> list[PlannedAssetSpec]:
    persisted: list[PlannedAssetSpec] = []
    for planned in plan.planned_asset_specs:
        spec = PlannedAssetSpec(
            asset_pack_id=asset_pack.id,
            asset_kind=planned.asset_kind.value,
            media_type=planned.media_type.value,
            working_title=planned.working_title,
            purpose=planned.purpose,
            prompt_or_description=planned.prompt_or_description,
            required_traits=planned.required_traits,
            compatible_with=planned.compatible_with,
            compatibility_metadata=planned.compatibility.model_dump(mode="python"),
            intended_reel_formats=planned.intended_reel_formats,
            priority=planned.priority,
            estimated_reuse_count=planned.estimated_reuse_count,
            status=PlannedAssetSpecStatus.PLANNED.value,
        )
        db.add(spec)
        db.flush()
        db.add(
            AssetPackItem(
                asset_pack_id=asset_pack.id,
                planned_asset_spec_id=spec.id,
                asset_kind=planned.asset_kind.value,
                pack_role=planned.category,
                reuse_purpose=planned.rationale,
                priority=planned.priority,
                compatibility_metadata=planned.compatibility.model_dump(mode="python"),
                metadata_json={
                    "category": planned.category,
                    "rationale": planned.rationale,
                    "output_potential_score": planned.output_potential_score,
                    "output_potential_scores": planned.output_potential_scores,
                    "output_potential_rationale": planned.output_potential_rationale,
                    "intended_reel_formats": planned.intended_reel_formats,
                    "generation_requires_planned_asset_spec": True,
                },
            )
        )
        persisted.append(spec)
    db.flush()
    return persisted


def _planned_specs_for_pack(db: Session, *, asset_pack_id: uuid.UUID) -> list[PlannedAssetSpec]:
    return (
        db.query(PlannedAssetSpec)
        .filter(PlannedAssetSpec.asset_pack_id == asset_pack_id)
        .order_by(PlannedAssetSpec.priority)
        .all()
    )


def _items_by_planned_spec(
    db: Session,
    *,
    asset_pack_id: uuid.UUID,
) -> dict[uuid.UUID, AssetPackItem]:
    items = db.query(AssetPackItem).filter(AssetPackItem.asset_pack_id == asset_pack_id).all()
    return {
        item.planned_asset_spec_id: item for item in items if item.planned_asset_spec_id is not None
    }


def _attach_existing_assets(
    db: Session,
    *,
    org_id: uuid.UUID,
    asset_pack: AssetPack,
    persisted_specs: list[PlannedAssetSpec],
    items_by_spec: dict[uuid.UUID, AssetPackItem],
) -> None:
    used_asset_ids: set[uuid.UUID] = set()
    for spec in sorted(persisted_specs, key=lambda item: item.priority):
        match = _find_compatible_asset(
            db,
            org_id=org_id,
            asset_pack=asset_pack,
            spec=spec,
            used_asset_ids=used_asset_ids,
        )
        if match is None:
            continue
        asset, match_metadata = match
        used_asset_ids.add(asset.id)
        item = items_by_spec[spec.id]
        item.asset_id = asset.id
        item.status = _existing_asset_item_status(match_metadata)
        item.metadata_json = {
            **dict(item.metadata_json or {}),
            "selection_source": item.status,
            "asset_selection": match_metadata,
        }
        item.compatibility_metadata = dict(spec.compatibility_metadata or {})
        spec.status = PlannedAssetSpecStatus.REGISTERED.value


def _find_compatible_asset(
    db: Session,
    *,
    org_id: uuid.UUID,
    asset_pack: AssetPack,
    spec: PlannedAssetSpec,
    used_asset_ids: set[uuid.UUID],
) -> tuple[Asset, dict[str, Any]] | None:
    candidates = (
        db.query(Asset)
        .filter(Asset.org_id == org_id, Asset.status.in_(_READY_ASSET_STATUSES))
        .order_by(Asset.created_at.desc())
        .limit(500)
        .all()
    )
    best: tuple[int, Asset, dict[str, Any]] | None = None
    for asset in candidates:
        if asset.id in used_asset_ids:
            continue
        metadata = _asset_match_metadata(asset)
        if metadata["asset_kind"] != spec.asset_kind or metadata["media_type"] != spec.media_type:
            continue
        score = _compatibility_score(asset_pack=asset_pack, spec=spec, metadata=metadata)
        if score < 5:
            continue
        match_metadata = {
            "mode": "compatible_existing",
            "asset_id": str(asset.id),
            "asset_status": asset.status,
            "asset_source": metadata["asset_source"],
            "matched_on": metadata["matched_on"],
            "score": score,
        }
        if best is None or score > best[0]:
            best = (score, asset, match_metadata)
    if best is None:
        return None
    _, asset, match_metadata = best
    return asset, match_metadata


def _asset_match_metadata(asset: Asset) -> dict[str, Any]:
    metadata = dict(asset.metadata_ or {})
    intent = _mapping_or_empty(metadata.get("intent"))
    request_payload = _mapping_or_empty(intent.get("request"))
    request_metadata = _mapping_or_empty(request_payload.get("metadata"))
    compatible_with = _mapping_or_empty(
        metadata.get("compatible_with")
        or request_metadata.get("compatible_with")
        or intent.get("compatible_with")
    )
    required_traits = _mapping_or_empty(
        metadata.get("required_traits")
        or request_metadata.get("required_traits")
        or intent.get("required_traits")
    )
    formats = (
        metadata.get("intended_reel_formats")
        or request_metadata.get("intended_reel_formats")
        or compatible_with.get("reel_formats")
        or []
    )
    return {
        "asset_kind": _optional_str(
            metadata.get("asset_kind")
            or intent.get("asset_kind")
            or request_payload.get("asset_kind")
        ),
        "media_type": _optional_str(
            metadata.get("media_type")
            or intent.get("media_type")
            or request_payload.get("media_type")
        ),
        "asset_source": str(
            metadata.get("asset_source")
            or intent.get("asset_source")
            or request_payload.get("asset_source")
            or asset.source
        ),
        "niche": _optional_str(
            metadata.get("niche")
            or request_metadata.get("asset_pack_niche")
            or request_metadata.get("niche")
            or compatible_with.get("niche")
        ),
        "pack_role": _optional_str(
            metadata.get("pack_role")
            or request_metadata.get("pack_role")
            or required_traits.get("category")
        ),
        "intended_reel_formats": [str(item) for item in formats]
        if isinstance(formats, list)
        else [],
        "matched_on": [],
    }


def _compatibility_score(
    *,
    asset_pack: AssetPack,
    spec: PlannedAssetSpec,
    metadata: dict[str, Any],
) -> int:
    score = 3
    matched_on = metadata["matched_on"]
    matched_on.extend(["asset_kind", "media_type"])
    if _norm(metadata.get("niche")) == _norm(asset_pack.niche):
        score += 3
        matched_on.append("niche")
    spec_category = str(spec.required_traits.get("category", ""))
    if _norm(metadata.get("pack_role")) == _norm(spec_category):
        score += 2
        matched_on.append("pack_role")
    if set(metadata.get("intended_reel_formats", [])) & set(spec.intended_reel_formats):
        score += 1
        matched_on.append("target_reel_formats")
    return score


def _existing_asset_item_status(match_metadata: dict[str, Any]) -> str:
    source = _norm(match_metadata.get("asset_source"))
    if source == AssetSource.UPLOADED.value:
        return AssetPackItemStatus.UPLOADED.value
    if source == AssetSource.IMPORTED.value:
        return AssetPackItemStatus.IMPORTED.value
    return AssetPackItemStatus.REUSED.value


def _resolve_planned_spec_generation(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    asset_pack: AssetPack,
    item: AssetPackItem,
    spec: PlannedAssetSpec,
    body: ApprovedAssetPackGenerateRequest | AssetPackBatchRequest,
) -> dict[str, Any]:
    from content_lab_api.schemas.assets import AssetResolveRequest
    from content_lab_api.services.asset_registry import resolve_asset_request

    decision = resolve_asset_request(
        db,
        request,
        org_id=org_id,
        body=AssetResolveRequest(
            asset_class=body.asset_class,
            asset_kind=spec.asset_kind,
            media_type=spec.media_type,
            asset_source=AssetSource.GENERATED,
            provider=body.provider,
            model=body.model,
            prompt=spec.prompt_or_description,
            negative_prompt=body.negative_prompt,
            seed=body.seed,
            duration_seconds=body.duration_seconds,
            fps=body.fps,
            ratio=body.ratio,
            motion=body.motion,
            metadata={
                "asset_pack_id": str(asset_pack.id),
                "planned_asset_spec_id": str(spec.id),
                "asset_pack_item_id": str(item.id),
                "asset_pack_niche": asset_pack.niche,
                "pack_role": item.pack_role,
                "required_traits": spec.required_traits,
                "compatible_with": spec.compatible_with,
                "compatibility_metadata": spec.compatibility_metadata,
                "intended_reel_formats": spec.intended_reel_formats,
                "selection_source": "generated",
                "source_metadata": default_generated_source_metadata().model_dump(
                    mode="python",
                    exclude_none=True,
                ),
            },
        ),
    )
    return cast(dict[str, Any], decision.model_dump(mode="python"))


def _apply_resolution_to_item(
    db: Session,
    *,
    item: AssetPackItem,
    spec: PlannedAssetSpec,
    decision: dict[str, Any],
) -> None:
    decision_type = decision["decision"]
    acq = decision.get("acquisition_decision")
    if decision_type == "generate":
        generation_intent = decision["generation_intent"]
        item.asset_id = uuid.UUID(str(generation_intent["asset_id"]))
        item.status = AssetPackItemStatus.GENERATING.value
        spec.status = PlannedAssetSpecStatus.GENERATING.value
        item.metadata_json = jsonable_encoder(
            {
                **dict(item.metadata_json or {}),
                "selection_source": "generated",
                "asset_selection": {
                    "mode": "generated_missing_asset",
                    "asset_id": str(item.asset_id),
                    "task_id": generation_intent.get("task_id"),
                    "task_status": generation_intent.get("task_status"),
                },
                "resolver_provenance": decision.get("provenance", {}),
                **({"acquisition_decision": acq} if acq is not None else {}),
            }
        )
        item.compatibility_metadata = dict(spec.compatibility_metadata or {})
        db.flush()
        return

    if decision_type == "reuse_exact":
        item.asset_id = uuid.UUID(str(decision["asset_id"]))
        asset = db.get(Asset, item.asset_id)
        asset_source = (
            "generated" if asset is None else _asset_match_metadata(asset)["asset_source"]
        )
        match_metadata = {
            "mode": "exact_asset_key",
            "asset_id": str(item.asset_id),
            "asset_status": None if asset is None else asset.status,
            "asset_source": asset_source,
            "matched_on": ["asset_key_hash"],
            "score": 10,
        }
        item.status = _existing_asset_item_status(match_metadata)
        spec.status = PlannedAssetSpecStatus.REGISTERED.value
        reg_acq = acquisition_decision_for_compatible_registry_reuse(
            planned_asset_spec_id=spec.id,
            match_metadata=match_metadata,
        ).model_copy(
            update={
                "rationale": "Exact asset_key_hash memoisation reuse in org registry.",
                "confidence": 1.0,
            }
        )
        item.metadata_json = jsonable_encoder(
            {
                **dict(item.metadata_json or {}),
                "selection_source": item.status,
                "asset_selection": match_metadata,
                "resolver_provenance": decision.get("provenance", {}),
                "acquisition_decision": reg_acq.model_dump(mode="python"),
            }
        )
        item.compatibility_metadata = dict(spec.compatibility_metadata or {})
        db.flush()
        return

    item.status = AssetPackItemStatus.FAILED.value
    spec.status = PlannedAssetSpecStatus.FAILED.value
    item.metadata_json = jsonable_encoder(
        {
            **dict(item.metadata_json or {}),
            "selection_source": "failed",
            "resolver_decision": decision,
            **({"acquisition_decision": acq} if acq is not None else {}),
        }
    )
    db.flush()


def _record_plan_audit(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    asset_pack: AssetPack,
    plan: AssetPackPlan,
    action: str = "asset_pack.plan.created",
) -> None:
    actor = getattr(request.state, "actor", ANONYMOUS_ACTOR)
    actor_id = None if actor == ANONYMOUS_ACTOR else actor
    actor_type = "anonymous" if actor_id is None else "request_header"
    db.execute(
        insert(AuditLog).values(
            id=uuid.uuid4(),
            org_id=org_id,
            action=action,
            resource_type="asset_pack",
            actor_type=actor_type,
            actor_id=actor_id,
            resource_id=str(asset_pack.id),
            payload={
                "requested_asset_count": asset_pack.requested_asset_count,
                "asset_mix": plan.asset_mix,
                "expected_reel_formats": plan.expected_reel_formats,
                "strategy_summary": plan.strategy_summary,
                "pack_strategy": plan.asset_pack_plan.get("pack_strategy"),
            },
        )
    )


def _record_asset_pack_audit(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    asset_pack: AssetPack,
    action: str,
    payload: dict[str, Any],
) -> None:
    actor = getattr(request.state, "actor", ANONYMOUS_ACTOR)
    actor_id = None if actor == ANONYMOUS_ACTOR else actor
    actor_type = "anonymous" if actor_id is None else "request_header"
    db.execute(
        insert(AuditLog).values(
            id=uuid.uuid4(),
            org_id=org_id,
            action=action,
            resource_type="asset_pack",
            actor_type=actor_type,
            actor_id=actor_id,
            resource_id=str(asset_pack.id),
            payload=payload,
        )
    )


def _record_review_audit(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    asset_pack: AssetPack,
    action: str,
    body: AssetPackReviewDecisionRequest,
) -> None:
    actor = getattr(request.state, "actor", ANONYMOUS_ACTOR)
    actor_id = None if actor == ANONYMOUS_ACTOR else actor
    actor_type = "anonymous" if actor_id is None else "request_header"
    db.execute(
        insert(AuditLog).values(
            id=uuid.uuid4(),
            org_id=org_id,
            action=action,
            resource_type="asset_pack",
            actor_type=actor_type,
            actor_id=actor_id,
            resource_id=str(asset_pack.id),
            payload={
                "status": asset_pack.status,
                "note": body.note,
                "metadata": body.metadata,
            },
        )
    )


def _record_batch_audit(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    asset_pack: AssetPack,
    summary: dict[str, int],
) -> None:
    actor = getattr(request.state, "actor", ANONYMOUS_ACTOR)
    actor_id = None if actor == ANONYMOUS_ACTOR else actor
    actor_type = "anonymous" if actor_id is None else "request_header"
    db.execute(
        insert(AuditLog).values(
            id=uuid.uuid4(),
            org_id=org_id,
            action="asset_pack.batch.resolved",
            resource_type="asset_pack",
            actor_type=actor_type,
            actor_id=actor_id,
            resource_id=str(asset_pack.id),
            payload=summary,
        )
    )


def _plan_out(
    *,
    asset_pack: AssetPack,
    plan: AssetPackPlan,
    persisted_specs: list[PlannedAssetSpec],
    planning_resolution_summary: dict[str, int] | None = None,
) -> AssetPackPlanOut:
    by_priority = {spec.priority: spec for spec in persisted_specs}
    return AssetPackPlanOut(
        asset_pack=AssetPackOut.model_validate(asset_pack),
        asset_pack_plan=plan.asset_pack_plan,
        asset_mix=plan.asset_mix,
        planned_asset_specs=[
            PlannedAssetSpecPlanOut(
                id=by_priority[planned.priority].id,
                asset_pack_id=by_priority[planned.priority].asset_pack_id,
                asset_kind=planned.asset_kind.value,
                media_type=planned.media_type.value,
                category=planned.category,
                working_title=planned.working_title,
                purpose=planned.purpose,
                prompt_or_description=planned.prompt_or_description,
                rationale=planned.rationale,
                required_traits=planned.required_traits,
                compatible_with=planned.compatible_with,
                compatibility_metadata=planned.compatibility.model_dump(mode="python"),
                intended_reel_formats=planned.intended_reel_formats,
                priority=planned.priority,
                estimated_reuse_count=planned.estimated_reuse_count,
                output_potential_score=planned.output_potential_score,
                output_potential_scores=planned.output_potential_scores,
                output_potential_rationale=planned.output_potential_rationale,
                status=cast(
                    PlannedAssetSpecStatusValue,
                    by_priority[planned.priority].status,
                ),
                created_at=by_priority[planned.priority].created_at,
                updated_at=by_priority[planned.priority].updated_at,
            )
            for planned in plan.planned_asset_specs
        ],
        strategy_summary=plan.strategy_summary,
        reuse_rationale=plan.reuse_rationale,
        expected_reel_formats=plan.expected_reel_formats,
        planning_resolution_summary=planning_resolution_summary or {},
    )


def _plan_out_from_rows(
    *,
    asset_pack: AssetPack,
    persisted_specs: list[PlannedAssetSpec],
    items: list[AssetPackItem],
    planning_resolution_summary: dict[str, int] | None = None,
) -> AssetPackPlanOut:
    items_by_spec = {
        item.planned_asset_spec_id: item for item in items if item.planned_asset_spec_id is not None
    }
    expected_reel_formats = sorted(
        {str(format_name) for spec in persisted_specs for format_name in spec.intended_reel_formats}
    )
    return AssetPackPlanOut(
        asset_pack=AssetPackOut.model_validate(asset_pack),
        asset_pack_plan={
            "pack_strategy": {
                "niche": asset_pack.niche,
                "target_audience": asset_pack.target_audience,
                "review_state": asset_pack.status,
            }
        },
        asset_mix=cast(dict[str, int], asset_pack.asset_mix_final_json or {}),
        planned_asset_specs=[
            _planned_spec_out_from_row(spec, item=items_by_spec.get(spec.id))
            for spec in persisted_specs
        ],
        strategy_summary=asset_pack.strategy_summary or "",
        reuse_rationale="Reviewed asset pack plan.",
        expected_reel_formats=expected_reel_formats,
        planning_resolution_summary=planning_resolution_summary or {},
    )


def _planned_spec_out_from_row(
    spec: PlannedAssetSpec,
    *,
    item: AssetPackItem | None,
) -> PlannedAssetSpecPlanOut:
    item_metadata = dict({} if item is None else item.metadata_json or {})
    output_potential = spec.required_traits.get("output_potential")
    output_score = (
        output_potential.get("score")
        if isinstance(output_potential, dict)
        else item_metadata.get("output_potential_score", 0.0)
    )
    return PlannedAssetSpecPlanOut(
        id=spec.id,
        asset_pack_id=spec.asset_pack_id,
        asset_kind=spec.asset_kind,
        media_type=spec.media_type,
        category=str(
            item_metadata.get("category") or (None if item is None else item.pack_role) or ""
        ),
        working_title=spec.working_title,
        purpose=spec.purpose,
        prompt_or_description=spec.prompt_or_description,
        rationale=str(
            item_metadata.get("rationale") or (None if item is None else item.reuse_purpose) or ""
        ),
        required_traits=spec.required_traits,
        compatible_with=spec.compatible_with,
        compatibility_metadata=spec.compatibility_metadata,
        intended_reel_formats=spec.intended_reel_formats,
        priority=spec.priority,
        estimated_reuse_count=spec.estimated_reuse_count,
        output_potential_score=float(output_score or 0.0),
        output_potential_scores=cast(
            dict[str, float],
            item_metadata.get("output_potential_scores") or {},
        ),
        output_potential_rationale=[
            str(item) for item in item_metadata.get("output_potential_rationale") or []
        ],
        status=cast(PlannedAssetSpecStatusValue, spec.status),
        created_at=spec.created_at,
        updated_at=spec.updated_at,
    )


def _batch_out(
    db: Session,
    *,
    asset_pack_id: uuid.UUID,
    plan: AssetPackPlan,
    persisted_specs: list[PlannedAssetSpec],
    generation_decisions: list[dict[str, Any]],
) -> AssetPackBatchOut:
    asset_pack = db.get(AssetPack, asset_pack_id)
    if asset_pack is None:
        raise LookupError(f"Asset pack {asset_pack_id} was not found")
    db.refresh(asset_pack)
    for spec in persisted_specs:
        db.refresh(spec)
    items = (
        db.query(AssetPackItem)
        .filter(AssetPackItem.asset_pack_id == asset_pack_id)
        .order_by(AssetPackItem.priority)
        .all()
    )
    plan_out = _plan_out(
        asset_pack=asset_pack,
        plan=plan,
        persisted_specs=persisted_specs,
        planning_resolution_summary=_resolution_summary(db, asset_pack_id=asset_pack_id),
    )
    return AssetPackBatchOut(
        **plan_out.model_dump(mode="python"),
        items=[AssetPackItemOut.model_validate(item) for item in items],
        resolution_summary=_resolution_summary(db, asset_pack_id=asset_pack_id),
        generation_decisions=generation_decisions,
    )


def _batch_out_from_rows(
    db: Session,
    *,
    asset_pack_id: uuid.UUID,
    persisted_specs: list[PlannedAssetSpec],
    generation_decisions: list[dict[str, Any]],
) -> AssetPackBatchOut:
    asset_pack = db.get(AssetPack, asset_pack_id)
    if asset_pack is None:
        raise LookupError(f"Asset pack {asset_pack_id} was not found")
    db.refresh(asset_pack)
    for spec in persisted_specs:
        db.refresh(spec)
    items = (
        db.query(AssetPackItem)
        .filter(AssetPackItem.asset_pack_id == asset_pack_id)
        .order_by(AssetPackItem.priority)
        .all()
    )
    plan_out = _plan_out_from_rows(
        asset_pack=asset_pack,
        persisted_specs=persisted_specs,
        items=items,
        planning_resolution_summary=_resolution_summary(db, asset_pack_id=asset_pack_id),
    )
    return AssetPackBatchOut(
        **plan_out.model_dump(mode="python"),
        items=[AssetPackItemOut.model_validate(item) for item in items],
        resolution_summary=_resolution_summary(db, asset_pack_id=asset_pack_id),
        generation_decisions=generation_decisions,
    )


def _resolution_summary(db: Session, *, asset_pack_id: uuid.UUID) -> dict[str, int]:
    items = db.query(AssetPackItem).filter(AssetPackItem.asset_pack_id == asset_pack_id).all()
    summary = {
        "planned": 0,
        "generating": 0,
        "generated": 0,
        "uploaded": 0,
        "imported": 0,
        "reused": 0,
        "selected": 0,
        "failed": 0,
        "ready_assets": 0,
    }
    for item in items:
        summary[item.status] = summary.get(item.status, 0) + 1
        if item.asset_id is None or item.status not in _AVAILABLE_ITEM_STATUSES:
            continue
        asset = db.get(Asset, item.asset_id)
        if asset is not None and asset.status in _READY_ASSET_STATUSES:
            summary["ready_assets"] += 1
    return summary


def _mapping_or_empty(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())
