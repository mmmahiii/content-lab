"""Org-scoped asset pack planning endpoints."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.models import (
    Asset,
    AssetGenParam,
    AssetPack,
    AssetPackItem,
    AuditLog,
    GeneratedReelStatus,
    Org,
    OutboxEvent,
    Page,
    Reel,
    ReelFamily,
    ReelOrigin,
    Run,
    Task,
)
from content_lab_api.routes._storage import build_signed_download
from content_lab_api.schemas.asset import AssetDetailOut
from content_lab_api.schemas.asset_packs import (
    ApprovedAssetPackGenerateRequest,
    AssetLedIdeasOut,
    AssetLedIdeasRequest,
    AssetPackBatchOut,
    AssetPackBatchRequest,
    AssetPackCombinationsOut,
    AssetPackCombinationsRequest,
    AssetPackCompositionSubmitOut,
    AssetPackCompositionSubmitRequest,
    AssetPackCreate,
    AssetPackItemOut,
    AssetPackOut,
    AssetPackPlanOut,
    AssetPackPlanRequest,
    AssetPackRegeneratePlanRequest,
    AssetPackReviewDecisionRequest,
    CandidateCompositionAssetOut,
    CandidateCompositionOut,
    CinematicPlanPromptOut,
    CinematicPlanPromptRequest,
    CinematicPlanValidateOut,
    CinematicPlanValidateRequest,
    SourceAssetRegisterOut,
    SourceAssetRegisterRequest,
)
from content_lab_api.schemas.runs import FlowTrigger, WorkflowKey
from content_lab_api.services import (
    approve_asset_pack_plan,
    build_asset_led_reel_ideas,
    build_asset_pack_compositions,
    create_asset_pack,
    create_asset_pack_batch,
    create_asset_pack_plan,
    generate_approved_asset_pack,
    plan_existing_asset_pack,
    regenerate_asset_pack_plan,
    register_source_asset_for_pack,
    reject_asset_pack_plan,
)
from content_lab_assets.combinator import CandidateComposition, PackAsset
from content_lab_assets.role_assignment import normalize_asset_for_cinematic_planning
from content_lab_creative.single_prompt_reel_planner import (
    SinglePromptPlannerInput,
    build_master_planning_prompt,
    build_plan_artifacts,
    validate_pasted_cinematic_plan,
)
from content_lab_qa.plan_realism import validate_cinematic_plan_realism
from content_lab_runs import RunStatus, TaskStatus
from content_lab_shared.logging import ANONYMOUS_ACTOR

router = APIRouter(prefix="/orgs/{org_id}/asset-packs", tags=["asset-packs"])


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


def _get_page_or_404(db: Session, *, org_id: uuid.UUID, page_id: uuid.UUID) -> Page:
    page = db.query(Page).filter(Page.org_id == org_id, Page.id == page_id).one_or_none()
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    return page


def _actor_info(request: Request) -> tuple[str | None, str]:
    actor = getattr(request.state, "actor", ANONYMOUS_ACTOR)
    actor_id = None if actor == ANONYMOUS_ACTOR else actor
    actor_type = "anonymous" if actor_id is None else "request_header"
    return actor_id, actor_type


def _record_audit(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    action: str,
    resource_type: str,
    resource_id: str,
    payload: dict[str, Any],
) -> None:
    actor_id, actor_type = _actor_info(request)
    db.execute(
        insert(AuditLog).values(
            id=uuid.uuid4(),
            org_id=org_id,
            action=action,
            resource_type=resource_type,
            actor_type=actor_type,
            actor_id=actor_id,
            resource_id=resource_id,
            payload=payload,
        )
    )


def _candidate_asset_out(asset: PackAsset) -> CandidateCompositionAssetOut:
    return CandidateCompositionAssetOut(
        asset_id=uuid.UUID(asset.asset_id),
        asset_kind=asset.asset_kind.value,
        pack_role=asset.pack_role,
        title=asset.title,
        compatibility=asset.compatibility.model_dump(mode="json"),
        metadata=asset.metadata,
        performance_score=asset.performance_score,
        usage_count=asset.usage_count,
    )


def _composition_manifest(
    *,
    asset_pack: AssetPack,
    candidate: CandidateComposition,
) -> dict[str, Any]:
    roles = {
        role: {
            "asset_id": asset.asset_id,
            "asset_kind": asset.asset_kind.value,
            "pack_role": asset.pack_role,
            "title": asset.title,
            "metadata": asset.metadata,
            "compatibility": asset.compatibility.model_dump(mode="json"),
        }
        for role, asset in sorted(candidate.roles.items())
    }
    return {
        "schema_version": "asset_composition_manifest.v1",
        "asset_pack_id": str(asset_pack.id),
        "composition_id": candidate.composition_id,
        "roles": roles,
        "scores": {
            "compatibility": candidate.compatibility_score,
            "diversity": candidate.diversity_score,
            "performance": candidate.performance_score,
            "selection": candidate.selection_score,
        },
        "reasons": candidate.reasons,
    }


def _candidate_out(
    *,
    asset_pack: AssetPack,
    candidate: CandidateComposition,
) -> CandidateCompositionOut:
    return CandidateCompositionOut(
        composition_id=candidate.composition_id,
        roles={role: _candidate_asset_out(asset) for role, asset in candidate.roles.items()},
        compatibility_score=candidate.compatibility_score,
        diversity_score=candidate.diversity_score,
        performance_score=candidate.performance_score,
        selection_score=candidate.selection_score,
        reasons=candidate.reasons,
        composition_manifest=_composition_manifest(asset_pack=asset_pack, candidate=candidate),
    )


def _composition_title(body: AssetPackCompositionSubmitRequest, asset_pack: AssetPack) -> str:
    raw_title = body.composition_manifest.get("title") or body.composition_manifest.get(
        "composition_id"
    )
    if raw_title:
        return f"{asset_pack.name}: {raw_title}"
    return f"{asset_pack.name} composition preview"


def _composition_source_plan(
    *,
    asset_pack: AssetPack,
    manifest: dict[str, Any],
    render_mode: str,
) -> dict[str, Any]:
    roles_raw = manifest.get("roles")
    roles = cast(dict[str, Any], roles_raw) if isinstance(roles_raw, dict) else {}
    role_titles = {
        str(role): _role_title(asset)
        for role, asset in roles.items()
        if isinstance(asset, dict)
    }
    hook = role_titles.get("hook") or str(manifest.get("title") or asset_pack.name)
    visual_roles = [
        title
        for role, title in role_titles.items()
        if role in {"background", "foreground", "format", "effect"}
    ]
    angle = f"Use {asset_pack.name} to turn reusable assets into a ready reel preview."
    if visual_roles:
        angle = f"Combine {', '.join(visual_roles[:3])} into a ready reel preview."
    return {
        "title": str(manifest.get("title") or f"{asset_pack.name} composition"),
        "hook": hook,
        "angle": angle,
        "content_pillar": asset_pack.niche,
        "duration_seconds": 12,
        "caption_angles": [
            f"Save this {asset_pack.niche} reel structure.",
            "Reuse the strongest asset pairing in your next post.",
        ],
        "beats": [
            {
                "text": hook,
                "shot_direction": "Open with the chosen hook asset and keep it legible in the safe area.",
            },
            {
                "text": angle,
                "shot_direction": "Show the selected background and foreground assets together.",
            },
            {
                "text": "Turn the composition into one clear next step.",
                "shot_direction": "Finish on a clean CTA frame.",
            },
        ],
        "asset_pack_id": str(asset_pack.id),
        "composition_manifest": manifest,
        "render_mode": render_mode,
    }


def _role_title(asset: dict[str, Any]) -> str:
    title = asset.get("title") or asset.get("asset_kind") or asset.get("asset_id")
    return " ".join(str(title).strip().split())


def _page_context_for_cinematic_planner(*, page: Page, asset_pack: AssetPack) -> dict[str, Any]:
    return {
        "page_id": str(page.id),
        "platform": page.platform,
        "display_name": page.display_name,
        "handle": page.handle,
        "kind": page.kind,
        "page_metadata": dict(page.metadata_ or {}),
        "asset_pack_id": str(asset_pack.id),
        "asset_pack_name": asset_pack.name,
        "asset_pack_niche": asset_pack.niche,
        "asset_pack_purpose": asset_pack.purpose,
        "asset_pack_target_audience": asset_pack.target_audience,
        "asset_pack_strategy_summary": asset_pack.strategy_summary,
    }


def _cinematic_planner_input(
    db: Session,
    *,
    org_id: uuid.UUID,
    asset_pack: AssetPack,
    body: CinematicPlanPromptRequest,
) -> SinglePromptPlannerInput:
    page = _get_page_or_404(db, org_id=org_id, page_id=body.page_id)
    selected_assets = _selected_cinematic_asset_descriptors(
        db,
        asset_pack=asset_pack,
        selected_asset_ids=body.selected_asset_ids,
    )
    return SinglePromptPlannerInput(
        page_context=_page_context_for_cinematic_planner(page=page, asset_pack=asset_pack),
        selected_assets=selected_assets,
        content_goal=body.content_goal,
        brand_persona_constraints=body.brand_persona_constraints,
        platform_constraints=body.platform_constraints,
        duration_target_seconds=body.duration_target_seconds,
        pinned_prompt_paths=body.pinned_prompt_paths,
        banned_prompt_paths=body.banned_prompt_paths,
    )


def _actual_asset_count_for_pack(db: Session, asset_pack_id: uuid.UUID) -> int:
    return int(
        db.query(func.count(AssetPackItem.id))
        .filter(
            AssetPackItem.asset_pack_id == asset_pack_id,
            AssetPackItem.asset_id.isnot(None),
        )
        .scalar()
        or 0
    )


def _asset_pack_out(db: Session, asset_pack: AssetPack) -> AssetPackOut:
    payload = AssetPackOut.model_validate(asset_pack)
    return payload.model_copy(
        update={"actual_asset_count": _actual_asset_count_for_pack(db, asset_pack.id)}
    )


def _selected_cinematic_asset_descriptors(
    db: Session,
    *,
    asset_pack: AssetPack,
    selected_asset_ids: list[uuid.UUID],
) -> list[dict[str, Any]]:
    selected_set = set(selected_asset_ids)
    items = (
        db.query(AssetPackItem)
        .filter(
            AssetPackItem.asset_pack_id == asset_pack.id,
            AssetPackItem.asset_id.in_(selected_asset_ids),
        )
        .order_by(AssetPackItem.priority, AssetPackItem.created_at, AssetPackItem.id)
        .all()
    )
    found_ids = {item.asset_id for item in items if item.asset_id is not None}
    missing = sorted(str(asset_id) for asset_id in selected_set - found_ids)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"selected assets are not members of this pack: {', '.join(missing)}",
        )
    assets_by_id = {
        asset.id: asset
        for asset in db.query(Asset).filter(Asset.id.in_(selected_asset_ids)).all()
    }
    descriptors: list[dict[str, Any]] = []
    for item in items:
        if item.asset_id is None:
            continue
        asset = assets_by_id.get(item.asset_id)
        if asset is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"selected asset is missing from registry: {item.asset_id}",
            )
        if asset.status not in {"active", "ready"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"selected asset is not ready: {item.asset_id}",
            )
        metadata = {
            **dict(asset.metadata_ or {}),
            **dict(item.metadata_json or {}),
            "storage_uri": asset.storage_uri,
            "content_hash": asset.content_hash,
            "asset_pack_niche": asset_pack.niche,
        }
        descriptor = normalize_asset_for_cinematic_planning(
            {
                "asset_id": str(item.asset_id),
                "asset_kind": item.asset_kind,
                "pack_role": item.pack_role,
                "reuse_purpose": item.reuse_purpose,
                "metadata": metadata,
                "compatibility_metadata": dict(item.compatibility_metadata or {}),
            }
        )
        descriptors.append(descriptor.model_dump(mode="json"))
    return descriptors


def _intentional_hook_layout(
    *,
    seed: str,
    hook_text: str,
    foreground_asset: dict[str, Any],
) -> dict[str, Any]:
    digest = hashlib.sha256(f"{seed}:{hook_text}:{foreground_asset.get('asset_id')}".encode()).hexdigest()
    variant = int(digest[:8], 16) % 4
    hook_size = 58 if len(hook_text) > 42 else 54 if len(hook_text) > 26 else 48
    layouts = [
        {
            "foreground": {"x": 66, "y": 64, "size": 56},
            "hook": {"x": 42, "y": 24, "size": hook_size},
            "intent": "subject-low-right_hook-upper-left",
        },
        {
            "foreground": {"x": 36, "y": 66, "size": 58},
            "hook": {"x": 58, "y": 25, "size": hook_size},
            "intent": "subject-low-left_hook-upper-right",
        },
        {
            "foreground": {"x": 68, "y": 42, "size": 52},
            "hook": {"x": 42, "y": 74, "size": hook_size},
            "intent": "subject-mid-right_hook-lower-left",
        },
        {
            "foreground": {"x": 50, "y": 67, "size": 62},
            "hook": {"x": 50, "y": 22, "size": hook_size},
            "intent": "subject-bottom-center_hook-top-center",
        },
    ]
    return layouts[variant]


def _composition_hook_cover_payload(
    *,
    asset_pack: AssetPack,
    run: Run,
    reel: Reel,
    task: Task,
    manifest: dict[str, Any],
    source_plan: dict[str, Any],
    render_mode: str,
) -> dict[str, Any]:
    roles_raw = manifest.get("roles")
    roles = cast(dict[str, Any], roles_raw) if isinstance(roles_raw, dict) else {}
    hook_raw = roles.get("hook")
    background_raw = roles.get("background")
    foreground_raw = roles.get("foreground")
    hook_asset = cast(dict[str, Any], hook_raw) if isinstance(hook_raw, dict) else {}
    background_asset = (
        cast(dict[str, Any], background_raw) if isinstance(background_raw, dict) else {}
    )
    foreground_asset = (
        cast(dict[str, Any], foreground_raw) if isinstance(foreground_raw, dict) else {}
    )
    hook_text = _role_title(hook_asset) if hook_asset else source_plan["hook"]
    manifest_editor_state = (
        manifest.get("editor_state") if isinstance(manifest.get("editor_state"), dict) else None
    )
    layout = manifest.get("layout") if isinstance(manifest.get("layout"), dict) else None
    if layout is None:
        generated_layout = _intentional_hook_layout(
            seed=str(manifest.get("composition_id") or run.id),
            hook_text=hook_text,
            foreground_asset=foreground_asset,
        )
        layout = {
            "intent": generated_layout["intent"],
            "background": {"treatment": "full_bleed", "safe_crop": "center_weighted"},
            "foreground": generated_layout["foreground"],
            "hook": generated_layout["hook"],
            "rationale": (
                "Combinator places the visual subject away from hook text and reserves "
                "a readable copy zone."
            ),
        }
    hook_cover = {
        "schema_version": "asset_hook_cover.v1",
        "title": str(manifest.get("title") or f"{asset_pack.name} hook cover"),
        "hook": hook_text,
        "asset_pack_id": str(asset_pack.id),
        "composition_id": str(manifest.get("composition_id") or run.id),
        "render_mode": render_mode,
        "canvas": {"aspect_ratio": "9:16", "width": 1080, "height": 1920},
        "roles": {
            "background": background_asset,
            "foreground": foreground_asset,
            "hook": hook_asset,
        },
        "layout": layout,
        "editor_state": manifest_editor_state,
        "source_plan": source_plan,
    }
    return {
        "workflow_stage": "asset_composition_render",
        "output_type": "hook_cover_image",
        "ready_for_publish": True,
        "reel_id": str(reel.id),
        "run_id": str(run.id),
        "package": {
            "reel_id": str(reel.id),
            "manifest": {
                "version": 1,
                "complete": True,
                "artifact_count": 1,
                "artifacts": [
                    {
                        "name": "hook_cover",
                        "filename": "hook_cover.local",
                        "kind": "image",
                        "content_type": "text/x-local-preview",
                    }
                ],
            },
            "caption_variants": source_plan.get("caption_angles", []),
            "composition_manifest": manifest,
            "hook_cover": hook_cover,
            "artifacts": [],
        },
        "step_outputs": {
            "planning": {"status": "succeeded", "hook_cover": hook_cover},
            "asset": {"status": "succeeded", "roles": hook_cover["roles"]},
            "editing": {"status": "succeeded", "hook_cover": hook_cover},
            "qa": {"status": "succeeded", "message": "Local hook/cover preview created."},
            "packaging": {"status": "succeeded", "hook_cover": hook_cover},
        },
        "task_statuses": {
            "asset_resolution": "succeeded",
            "creative_planning": "succeeded",
            "editing": "succeeded",
            "packaging": "succeeded",
            "process_reel": "succeeded",
            "qa": "succeeded",
        },
        "task_id": str(task.id),
    }


@router.post("", response_model=AssetPackOut, status_code=status.HTTP_201_CREATED)
def create_asset_pack_route(
    org_id: uuid.UUID,
    body: AssetPackCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> AssetPackOut:
    created = create_asset_pack(db, request, org_id=org_id, body=body)
    return _asset_pack_out(
        db,
        _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=created.id),
    )


@router.get("", response_model=list[AssetPackOut])
def list_asset_packs(
    org_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    niche: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[AssetPackOut]:
    _get_org_or_404(db, org_id)
    query = db.query(AssetPack).filter(AssetPack.org_id == org_id)
    if status_filter is not None:
        query = query.filter(AssetPack.status == status_filter)
    if niche is not None:
        query = query.filter(AssetPack.niche == niche)
    rows = (
        query.order_by(AssetPack.created_at.desc(), AssetPack.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    counts: dict[uuid.UUID, int] = {}
    if rows:
        counts = {
            asset_pack_id: int(count)
            for asset_pack_id, count in db.query(AssetPackItem.asset_pack_id, func.count(AssetPackItem.id))
            .filter(
                AssetPackItem.asset_pack_id.in_([row.id for row in rows]),
                AssetPackItem.asset_id.isnot(None),
            )
            .group_by(AssetPackItem.asset_pack_id)
            .all()
        }
    return [
        AssetPackOut.model_validate(row).model_copy(
            update={"actual_asset_count": int(counts.get(row.id, 0))}
        )
        for row in rows
    ]


@router.post("/plan", response_model=AssetPackPlanOut, status_code=status.HTTP_201_CREATED)
def plan_asset_pack(
    org_id: uuid.UUID,
    body: AssetPackPlanRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AssetPackPlanOut:
    planned = create_asset_pack_plan(db, request, org_id=org_id, body=body)
    return planned.model_copy(
        update={
            "asset_pack": _asset_pack_out(
                db,
                _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=planned.asset_pack.id),
            )
        }
    )


@router.get("/{asset_pack_id}", response_model=AssetPackOut)
def get_asset_pack(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> AssetPackOut:
    _get_org_or_404(db, org_id)
    return _asset_pack_out(
        db,
        _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=asset_pack_id),
    )


@router.post("/{asset_pack_id}/plan", response_model=AssetPackPlanOut)
def plan_existing_pack(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: AssetPackPlanRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AssetPackPlanOut:
    planned = plan_existing_asset_pack(
        db,
        request,
        org_id=org_id,
        asset_pack_id=asset_pack_id,
        body=body,
    )
    return planned.model_copy(
        update={
            "asset_pack": _asset_pack_out(
                db,
                _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=planned.asset_pack.id),
            )
        }
    )


@router.get("/{asset_pack_id}/items", response_model=list[AssetPackItemOut])
def list_asset_pack_items(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[AssetPackItemOut]:
    _get_org_or_404(db, org_id)
    _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=asset_pack_id)
    rows = (
        db.query(AssetPackItem)
        .filter(AssetPackItem.asset_pack_id == asset_pack_id)
        .order_by(AssetPackItem.priority, AssetPackItem.created_at, AssetPackItem.id)
        .all()
    )
    return [AssetPackItemOut.model_validate(row) for row in rows]


@router.post("/{asset_pack_id}/combinations", response_model=AssetPackCombinationsOut)
def generate_asset_pack_combinations(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: AssetPackCombinationsRequest,
    db: Session = Depends(get_db),
) -> AssetPackCombinationsOut:
    _get_org_or_404(db, org_id)
    asset_pack = _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=asset_pack_id)
    try:
        candidates = build_asset_pack_compositions(
            db,
            org_id=org_id,
            asset_pack_id=asset_pack_id,
            target_reel_count=body.target_reel_count,
            format_filters=body.format_filters(),
            style_filters=body.style_filters(),
            selection_mode=body.mode,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return AssetPackCombinationsOut(
        asset_pack=_asset_pack_out(db, asset_pack),
        candidate_compositions=[
            _candidate_out(asset_pack=asset_pack, candidate=candidate) for candidate in candidates
        ],
    )


@router.post("/{asset_pack_id}/cinematic-plan-prompt", response_model=CinematicPlanPromptOut)
def generate_cinematic_plan_prompt(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: CinematicPlanPromptRequest,
    db: Session = Depends(get_db),
) -> CinematicPlanPromptOut:
    _get_org_or_404(db, org_id)
    asset_pack = _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=asset_pack_id)
    try:
        planner_input = _cinematic_planner_input(
            db,
            org_id=org_id,
            asset_pack=asset_pack,
            body=body,
        )
        prompt_package = build_master_planning_prompt(planner_input)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return CinematicPlanPromptOut(
        recommended_model=prompt_package.recommended_model,
        planning_prompt_version=prompt_package.planning_prompt_version,
        input_page_context_hash=prompt_package.input_page_context_hash,
        selected_asset_ids=[uuid.UUID(asset_id) for asset_id in prompt_package.selected_asset_ids],
        suggested_prompt_paths=prompt_package.suggested_prompt_paths,
        master_prompt=prompt_package.master_prompt,
        planner_input=planner_input.model_dump(mode="json"),
    )


@router.post("/{asset_pack_id}/cinematic-plan-validate", response_model=CinematicPlanValidateOut)
def validate_cinematic_plan(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: CinematicPlanValidateRequest,
    db: Session = Depends(get_db),
) -> CinematicPlanValidateOut:
    _get_org_or_404(db, org_id)
    asset_pack = _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=asset_pack_id)
    try:
        planner_input = _cinematic_planner_input(
            db,
            org_id=org_id,
            asset_pack=asset_pack,
            body=body,
        )
        plan_payload: str | dict[str, Any] = (
            body.raw_plan_json if body.raw_plan_json is not None else dict(body.plan or {})
        )
        validated = validate_pasted_cinematic_plan(plan_payload, planner_input=planner_input)
        realism_report = validate_cinematic_plan_realism(validated.plan)
        if not realism_report.passed:
            raise ValueError(
                "realism QA failed: "
                + ", ".join(
                    finding.code for finding in realism_report.findings if finding.severity == "fail"
                )
            )
        validation_report = {
            **validated.validation_report,
            "plan_realism": realism_report.as_dict(),
        }
        artifacts = build_plan_artifacts(
            validated.plan,
            realism_qa={
                "scene_regulation": validated.validation_report.get("scene_regulation"),
                "plan_realism": realism_report.as_dict(),
            },
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return CinematicPlanValidateOut(
        plan=validated.plan.model_dump(mode="json"),
        validation_report=validation_report,
        plan_hash=validated.plan_hash,
        artifacts=artifacts,
    )


@router.post(
    "/{asset_pack_id}/composition-renders",
    response_model=AssetPackCompositionSubmitOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_asset_pack_composition_render(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: AssetPackCompositionSubmitRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AssetPackCompositionSubmitOut:
    _get_org_or_404(db, org_id)
    asset_pack = _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=asset_pack_id)
    page = _get_page_or_404(db, org_id=org_id, page_id=body.page_id)
    manifest = dict(body.composition_manifest or {})
    manifest_pack_id = manifest.get("asset_pack_id")
    if manifest_pack_id is not None and str(manifest_pack_id) != str(asset_pack_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="composition_manifest.asset_pack_id must match the route asset_pack_id",
        )
    manifest["asset_pack_id"] = str(asset_pack_id)

    idempotency_key = body.idempotency_key or (
        f"asset-composition-render:{asset_pack_id}:"
        f"{body.render_mode}:{manifest.get('composition_id') or uuid.uuid4()}"
    )
    source_plan = _composition_source_plan(
        asset_pack=asset_pack,
        manifest=manifest,
        render_mode=body.render_mode,
    )
    family = ReelFamily(
        org_id=org_id,
        page_id=page.id,
        name=_composition_title(body, asset_pack),
        metadata_={
            "mode": "asset_composition",
            "asset_pack_id": str(asset_pack_id),
            "render_mode": body.render_mode,
            "composition_manifest": manifest,
            "idea_plan": source_plan,
            "submission_metadata": dict(body.metadata),
        },
    )
    db.add(family)
    db.flush()
    reel = Reel(
        org_id=org_id,
        reel_family_id=family.id,
        origin=ReelOrigin.GENERATED.value,
        status=GeneratedReelStatus.PLANNING.value,
        variant_label="Preview" if body.render_mode == "preview" else "Final",
        metadata_={
            "asset_pack_id": str(asset_pack_id),
            "composition_manifest": manifest,
            "idea_plan": source_plan,
            "render_mode": body.render_mode,
            "dry_run": body.dry_run,
        },
    )
    db.add(reel)
    db.flush()
    run = Run(
        org_id=org_id,
        workflow_key=WorkflowKey.PROCESS_REEL.value,
        flow_trigger=FlowTrigger.MANUAL.value,
        status=RunStatus.QUEUED.value,
        idempotency_key=idempotency_key,
        input_params={
            "org_id": str(org_id),
            "page_id": str(page.id),
            "reel_id": str(reel.id),
            "reel_family_id": str(family.id),
            "workflow_stage": "asset_composition_render",
            "asset_pack_id": str(asset_pack_id),
            "composition_manifest": manifest,
            "render_mode": body.render_mode,
            "dry_run": body.dry_run,
        },
        run_metadata={
            "submitted_via": "api",
            "flow_trigger": FlowTrigger.MANUAL.value,
            "client": {
                "workflow_stage": "asset_composition_render",
                "render_mode": body.render_mode,
                **dict(body.metadata),
            },
            "target": {
                "org_id": str(org_id),
                "page_id": str(page.id),
                "asset_pack_id": str(asset_pack_id),
                "reel_id": str(reel.id),
                "reel_family_id": str(family.id),
            },
            "request": {
                "request_id": getattr(request.state, "request_id", None),
                "method": request.method,
                "path": request.url.path,
            },
        },
    )
    db.add(run)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A matching composition render run already exists for the org",
        ) from exc

    task = Task(
        org_id=org_id,
        task_type=WorkflowKey.PROCESS_REEL.value,
        idempotency_key=idempotency_key,
        status=TaskStatus.QUEUED.value,
        run_id=run.id,
        payload=dict(run.input_params or {}),
    )
    db.add(task)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A matching composition render task already exists for the org",
        ) from exc
    event = OutboxEvent(
        org_id=org_id,
        aggregate_type="run",
        aggregate_id=str(run.id),
        event_type="orchestration.flow.requested",
        payload={
            "run_id": str(run.id),
            "task_id": str(task.id),
            "org_id": str(org_id),
            "workflow_key": run.workflow_key,
            "flow_trigger": run.flow_trigger,
            "status": run.status,
            "idempotency_key": run.idempotency_key,
            "input_params": dict(run.input_params or {}),
            "run_metadata": dict(run.run_metadata or {}),
            "request_id": getattr(request.state, "request_id", None),
        },
    )
    db.add(event)
    db.flush()
    run.external_ref = f"outbox:{event.id}"
    run_metadata = dict(run.run_metadata or {})
    run_metadata["orchestration"] = {
        "backend": "local_hook_cover",
        "event_type": event.event_type,
        "outbox_event_id": str(event.id),
    }
    run.run_metadata = run_metadata
    _record_audit(
        db,
        request,
        org_id=org_id,
        action="asset_pack.composition_render.submitted",
        resource_type="run",
        resource_id=str(run.id),
        payload={
            "asset_pack_id": str(asset_pack_id),
            "page_id": str(page.id),
            "reel_id": str(reel.id),
            "reel_family_id": str(family.id),
            "render_mode": body.render_mode,
            "dry_run": body.dry_run,
        },
    )
    run.status = RunStatus.SUCCEEDED.value
    task.status = TaskStatus.SUCCEEDED.value
    reel.status = GeneratedReelStatus.READY.value
    output_payload = _composition_hook_cover_payload(
        asset_pack=asset_pack,
        run=run,
        reel=reel,
        task=task,
        manifest=manifest,
        source_plan=source_plan,
        render_mode=body.render_mode,
    )
    run.output_payload = output_payload
    task.result = output_payload
    db.commit()
    db.refresh(run)
    db.refresh(task)
    return AssetPackCompositionSubmitOut(
        run_id=run.id,
        task_id=task.id,
        reel_id=reel.id,
        reel_family_id=family.id,
        status=run.status,
        external_ref=run.external_ref,
    )


@router.post("/generate", response_model=AssetPackBatchOut, status_code=status.HTTP_201_CREATED)
def generate_asset_pack(
    org_id: uuid.UUID,
    body: AssetPackBatchRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AssetPackBatchOut:
    return create_asset_pack_batch(db, request, org_id=org_id, body=body)


@router.post("/{asset_pack_id}/approve", response_model=AssetPackOut)
def approve_asset_pack(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: AssetPackReviewDecisionRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AssetPackOut:
    approved = approve_asset_pack_plan(
        db,
        request,
        org_id=org_id,
        asset_pack_id=asset_pack_id,
        body=body,
    )
    return _asset_pack_out(
        db,
        _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=approved.id),
    )


@router.post("/{asset_pack_id}/reject", response_model=AssetPackOut)
def reject_asset_pack(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: AssetPackReviewDecisionRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AssetPackOut:
    rejected = reject_asset_pack_plan(
        db,
        request,
        org_id=org_id,
        asset_pack_id=asset_pack_id,
        body=body,
    )
    return _asset_pack_out(
        db,
        _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=rejected.id),
    )


@router.post("/{asset_pack_id}/regenerate-plan", response_model=AssetPackPlanOut)
def regenerate_asset_pack(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: AssetPackRegeneratePlanRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AssetPackPlanOut:
    regenerated = regenerate_asset_pack_plan(
        db,
        request,
        org_id=org_id,
        asset_pack_id=asset_pack_id,
        body=body,
    )
    return regenerated.model_copy(
        update={
            "asset_pack": _asset_pack_out(
                db,
                _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=regenerated.asset_pack.id),
            )
        }
    )


@router.post(
    "/{asset_pack_id}/generate",
    response_model=AssetPackBatchOut,
    status_code=status.HTTP_201_CREATED,
)
def generate_approved_pack(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: ApprovedAssetPackGenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AssetPackBatchOut:
    generated = generate_approved_asset_pack(
        db,
        request,
        org_id=org_id,
        asset_pack_id=asset_pack_id,
        body=body,
    )
    return generated.model_copy(
        update={
            "asset_pack": _asset_pack_out(
                db,
                _get_asset_pack_or_404(db, org_id=org_id, asset_pack_id=generated.asset_pack.id),
            )
        }
    )


@router.post("/{asset_pack_id}/ideas", response_model=AssetLedIdeasOut)
def generate_asset_led_ideas(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: AssetLedIdeasRequest,
    db: Session = Depends(get_db),
) -> AssetLedIdeasOut:
    return build_asset_led_reel_ideas(
        db,
        org_id=org_id,
        asset_pack_id=asset_pack_id,
        target_concept_count=body.target_concept_count,
        selected_asset_ids=body.selected_asset_ids,
        format_filters=body.format_filters,
        style_filters=body.style_filters,
        selection_mode=body.selection_mode,
    )


@router.post(
    "/{asset_pack_id}/source-assets",
    response_model=SourceAssetRegisterOut,
    status_code=status.HTTP_201_CREATED,
)
def register_source_asset(
    org_id: uuid.UUID,
    asset_pack_id: uuid.UUID,
    body: SourceAssetRegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> SourceAssetRegisterOut:
    asset, item, reused_existing = register_source_asset_for_pack(
        db,
        request,
        org_id=org_id,
        asset_pack_id=asset_pack_id,
        body=body,
    )
    return SourceAssetRegisterOut(
        asset=_asset_detail_out(db, asset=asset),
        item=AssetPackItemOut.model_validate(item),
        reused_existing_asset=reused_existing,
    )


def _latest_gen_params(db: Session, *, asset_id: uuid.UUID) -> AssetGenParam | None:
    return (
        db.query(AssetGenParam)
        .filter(AssetGenParam.asset_id == asset_id)
        .order_by(AssetGenParam.seq.desc())
        .one_or_none()
    )


def _asset_detail_out(db: Session, *, asset: Asset) -> AssetDetailOut:
    gen_params = _latest_gen_params(db, asset_id=asset.id)
    provenance: dict[str, Any] = {
        "source": asset.source,
        "storage_uri": asset.storage_uri,
    }
    if asset.asset_key is not None:
        provenance["asset_key"] = asset.asset_key
    if asset.asset_key_hash is not None:
        provenance["asset_key_hash"] = asset.asset_key_hash
    if gen_params is not None:
        provenance["asset_gen_param_seq"] = gen_params.seq

    return AssetDetailOut(
        id=asset.id,
        org_id=asset.org_id,
        asset_class=asset.asset_class,
        status=asset.status,
        source=asset.source,
        storage_uri=asset.storage_uri,
        asset_key=asset.asset_key,
        asset_key_hash=asset.asset_key_hash,
        content_hash=asset.content_hash,
        metadata=asset.metadata_,
        canonical_params=None
        if gen_params is None
        else jsonable_encoder(gen_params.canonical_params),
        provenance=provenance,
        download=build_signed_download(storage_uri=asset.storage_uri),
        created_at=asset.created_at,
    )
