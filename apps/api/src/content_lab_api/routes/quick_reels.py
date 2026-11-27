"""Quick Reel "Send to Review": save a finished Quick Reel into the page's review flow.

The review flow already exists: generated reels in ``ready`` status are listed by
``GET /orgs/{org}/pages/{page}/reels?status=ready`` and approved / archived / marked posted
by the reels routes. This endpoint only adds the write side for Quick Reel:

- the reel is re-composed here from the hook, branch set and selection (``compose_reel``
  is deterministic and makes no LLM call), so what is stored is what the API itself would
  compose for those choices, not whatever the client sent;
- every Quick Reel for a page goes into one reel family ("Quick Reel", tagged
  ``source=quick_reel``), created on first use;
- the reel is created as a generated reel in ``ready`` so it can be approved, or in
  ``qa_failed`` when the uploaded render failed a blocking QA gate.

Media (see ``services/quick_reel_media.py``): ``POST …/quick-reel/soundtrack`` voices the
composed reel and mixes it over a music bed (the web render attaches the WAV);
``PUT …/quick-reel/renders/{render_id}/video`` stores the exported MP4 in object storage and
``POST …/quick-reel/renders/{render_id}/qa`` runs pipeline QA on it. Send to Review attaches
that QA report to the reel instead of the old ``qa.status = not_run``.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Literal

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import insert
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.models.asset import Asset
from content_lab_api.models.audit_log import AuditLog
from content_lab_api.models.org import Org
from content_lab_api.models.page import Page
from content_lab_api.models.reel import GeneratedReelStatus, Reel, ReelOrigin
from content_lab_api.models.reel_family import ReelFamily
from content_lab_api.routes._storage import build_signed_download
from content_lab_api.schemas.asset import SignedDownloadOut
from content_lab_api.schemas.reel_families import ReelFamilyMode, dump_reel_family_metadata
from content_lab_api.schemas.reels import ReelOut, reel_to_out
from content_lab_api.services.asset_representations import is_image_uri, representation_uri
from content_lab_api.services.quick_reel_export import export_quick_reel
from content_lab_api.services.quick_reel_media import (
    MAX_RENDER_BYTES,
    build_quick_reel_soundtrack,
    read_quick_reel_qa,
    read_soundtrack_manifest,
    run_quick_reel_qa,
    soundtrack_uri,
    store_quick_reel_video,
)
from content_lab_creative.generation import (
    BranchSelection,
    BranchSet,
    ComposedReel,
    CreativePageContext,
    HookCandidate,
    compose_reel,
)
from content_lab_shared.logging import ANONYMOUS_ACTOR
from content_lab_shared.settings import Settings
from content_lab_storage import S3StorageClient, S3StorageConfig

router = APIRouter(tags=["quick-reel"])

QUICK_REEL_SOURCE = "quick_reel"
QUICK_REEL_FAMILY_NAME = "Quick Reel"
QUICK_REEL_METADATA_KEY = "quick_reel"


class QuickReelVisualIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: uuid.UUID
    fit: Literal["cutout", "cover"] = "cutout"


class QuickReelRenderIn(BaseModel):
    """The local Remotion render the operator exported, if any."""

    model_config = ConfigDict(extra="forbid")

    render_id: str = Field(min_length=8, max_length=64, pattern=r"^[0-9a-f]+$")
    duration_seconds: float = Field(gt=0, le=90)
    width: int = Field(ge=16, le=4096)
    height: int = Field(ge=16, le=4096)
    fps: int = Field(ge=1, le=60)
    overlay_trace_status: Literal["pass", "fail"]


_RENDER_ID_PATTERN = r"^[0-9a-f]{8,64}$"


class QuickReelComposeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hook: HookCandidate
    branches: BranchSet
    selection: BranchSelection
    duration_seconds: int | None = Field(default=None, ge=8, le=60)


class QuickReelSoundtrackOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    soundtrack_id: str
    duration_seconds: float
    storage_uri: str | None
    download_path: str | None
    voiceover: dict[str, Any] | None
    music: dict[str, Any] | None
    expect_voiceover: bool


class QuickReelExportIn(QuickReelComposeIn):
    visuals: list[QuickReelVisualIn] = Field(default_factory=list, max_length=12)


class QuickReelQaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overlay_render_trace: dict[str, Any]
    soundtrack_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{8,64}$")


class QuickReelSaveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hook: HookCandidate
    branches: BranchSet
    selection: BranchSelection
    duration_seconds: int | None = Field(default=None, ge=8, le=60)
    topic: str | None = Field(default=None, max_length=200)
    caption: str = Field(min_length=1, max_length=2_200)
    visuals: list[QuickReelVisualIn] = Field(default_factory=list, max_length=12)
    render: QuickReelRenderIn | None = None
    generation_source: Literal["llm", "fallback"] | None = None
    # Lets the UI retry a send without creating a second reel.
    client_request_id: uuid.UUID | None = None


def _actor(request: Request) -> tuple[str | None, str]:
    actor = getattr(request.state, "actor", ANONYMOUS_ACTOR)
    actor_id = None if actor == ANONYMOUS_ACTOR else actor
    return actor_id, ("anonymous" if actor_id is None else "request_header")


def _audit(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    actor_id, actor_type = _actor(request)
    db.execute(
        insert(AuditLog).values(
            id=uuid.uuid4(),
            org_id=org_id,
            action=action,
            resource_type=resource_type,
            actor_type=actor_type,
            actor_id=actor_id,
            resource_id=str(resource_id),
            payload=payload,
        )
    )


def _quick_reel_family(
    db: Session, request: Request, *, org_id: uuid.UUID, page_id: uuid.UUID
) -> ReelFamily:
    family = (
        db.query(ReelFamily)
        .filter(
            ReelFamily.org_id == org_id,
            ReelFamily.page_id == page_id,
            ReelFamily.metadata_["source"].astext == QUICK_REEL_SOURCE,
        )
        .order_by(ReelFamily.created_at, ReelFamily.id)
        .first()
    )
    if family is not None:
        return family
    family = ReelFamily(
        org_id=org_id,
        page_id=page_id,
        name=QUICK_REEL_FAMILY_NAME,
        metadata_=dump_reel_family_metadata(ReelFamilyMode.EXPLORE, {"source": QUICK_REEL_SOURCE}),
    )
    db.add(family)
    db.flush()
    _audit(
        db,
        request,
        org_id=org_id,
        action="reel_family.created",
        resource_type="reel_family",
        resource_id=family.id,
        payload={"page_id": str(page_id), "name": family.name, "source": QUICK_REEL_SOURCE},
    )
    return family


def _variant_label(selection: BranchSelection) -> str:
    return f"quick:{selection.structure}/{selection.energy}/{selection.ending}"[:64]


def _quick_reel_storage() -> S3StorageClient:
    settings = Settings()
    return S3StorageClient(
        S3StorageConfig(
            endpoint=settings.minio_endpoint,
            access_key_id=settings.minio_root_user,
            secret_access_key=settings.minio_root_password.get_secret_value(),
            default_bucket=settings.minio_bucket,
        )
    )


def _page_or_404(db: Session, org_id: uuid.UUID, page_id: uuid.UUID) -> Page:
    if db.get(Org, org_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Org not found")
    page = db.query(Page).filter(Page.org_id == org_id, Page.id == page_id).one_or_none()
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    return page


def _compose(page: Page, body: QuickReelComposeIn | QuickReelSaveIn) -> ComposedReel:
    context = CreativePageContext.from_page(
        display_name=page.display_name, handle=page.handle, metadata=page.metadata_
    )
    try:
        return compose_reel(
            hook=body.hook,
            branches=body.branches,
            selection=body.selection,
            duration_seconds=body.duration_seconds,
            constraints=context.constraints,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _soundtrack_out(org_id: uuid.UUID, manifest: dict[str, Any]) -> QuickReelSoundtrackOut:
    soundtrack_id = str(manifest["soundtrack_id"])
    return QuickReelSoundtrackOut(
        soundtrack_id=soundtrack_id,
        duration_seconds=float(manifest["duration_seconds"]),
        storage_uri=manifest.get("storage_uri"),
        download_path=(
            f"/orgs/{org_id}/quick-reel/soundtracks/{soundtrack_id}/download"
            if manifest.get("storage_uri")
            else None
        ),
        voiceover=manifest.get("voiceover"),
        music=manifest.get("music"),
        expect_voiceover=bool(manifest.get("expect_voiceover")),
    )


@router.post(
    "/orgs/{org_id}/pages/{page_id}/quick-reel/soundtrack",
    response_model=QuickReelSoundtrackOut,
)
async def build_soundtrack(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    body: QuickReelComposeIn,
    db: Session = Depends(get_db),
) -> QuickReelSoundtrackOut:
    """Voice + music bed for the composed reel (cached; the web render attaches it)."""

    page = _page_or_404(db, org_id, page_id)
    composed = _compose(page, body)
    manifest = await run_in_threadpool(
        build_quick_reel_soundtrack,
        composed,
        org_id=str(org_id),
        settings=Settings(),
        storage=_quick_reel_storage(),
    )
    return _soundtrack_out(org_id, manifest)


@router.get(
    "/orgs/{org_id}/quick-reel/soundtracks/{soundtrack_id}/download",
    response_model=SignedDownloadOut,
)
def download_soundtrack(
    org_id: uuid.UUID,
    soundtrack_id: str,
    db: Session = Depends(get_db),
) -> SignedDownloadOut:
    if db.get(Org, org_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Org not found")
    settings = Settings()
    manifest = read_soundtrack_manifest(
        org_id=str(org_id),
        soundtrack_id=soundtrack_id,
        settings=settings,
        storage=_quick_reel_storage(),
    )
    if manifest is None or not manifest.get("storage_uri"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Soundtrack not found")
    return build_signed_download(
        storage_uri=soundtrack_uri(settings, org_id=str(org_id), soundtrack_id=soundtrack_id)
    )


@router.put("/orgs/{org_id}/pages/{page_id}/quick-reel/renders/{render_id}/video")
async def upload_render_video(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    render_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Store the exported MP4 (raw request body) next to its QA report."""

    _page_or_404(db, org_id, page_id)
    _require_render_id(render_id)
    declared = int(request.headers.get("content-length") or 0)
    if declared > MAX_RENDER_BYTES:
        raise HTTPException(status_code=413, detail="Render upload is too large")
    data = await request.body()
    try:
        uri = await run_in_threadpool(
            store_quick_reel_video,
            data,
            org_id=str(org_id),
            render_id=render_id,
            settings=Settings(),
            storage=_quick_reel_storage(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"render_id": render_id, "video_storage_uri": uri}


@router.post("/orgs/{org_id}/pages/{page_id}/quick-reel/renders/{render_id}/qa")
async def run_render_qa(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    render_id: str,
    body: QuickReelQaIn,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run pipeline QA on the uploaded MP4 (format, blank/static, silence, overlays)."""

    _page_or_404(db, org_id, page_id)
    _require_render_id(render_id)
    settings = Settings()
    storage = _quick_reel_storage()
    soundtrack = None
    if body.soundtrack_id is not None:
        soundtrack = read_soundtrack_manifest(
            org_id=str(org_id), soundtrack_id=body.soundtrack_id, settings=settings, storage=storage
        )
        if soundtrack is None:
            raise HTTPException(status_code=422, detail="Unknown soundtrack_id")
    try:
        return await run_in_threadpool(
            run_quick_reel_qa,
            org_id=str(org_id),
            render_id=render_id,
            overlay_render_trace=body.overlay_render_trace,
            soundtrack=soundtrack,
            settings=settings,
            storage=storage,
        )
    except ClientError as exc:
        raise HTTPException(
            status_code=409, detail="Upload the render video before running QA"
        ) from exc


@router.post("/orgs/{org_id}/pages/{page_id}/quick-reel/exports")
async def export_reel(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    body: QuickReelExportIn,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Build the MP4 with FFmpeg (seconds, not Chrome screenshots), store it and QA it.

    The result's ``export_id`` is a render id: Send to Review with ``render.render_id`` set to
    it attaches this export's QA report.
    """

    page = _page_or_404(db, org_id, page_id)
    composed = _compose(page, body)
    by_id = {visual.asset_id: visual for visual in body.visuals}
    rows = (
        db.query(Asset.id, Asset.storage_uri)
        .filter(Asset.org_id == org_id, Asset.id.in_(list(by_id)))
        .all()
        if by_id
        else []
    )
    if len(rows) != len(by_id):
        raise HTTPException(status_code=422, detail="Unknown asset(s) for this org")
    storage = _quick_reel_storage()
    uris = {row[0]: row[1] for row in rows}
    visuals = []
    for visual in body.visuals:
        uri = uris[visual.asset_id]
        if is_image_uri(uri):
            uri = await run_in_threadpool(
                representation_uri, storage_uri=uri, max_px=1080, storage=storage
            )
        visuals.append({"asset_id": str(visual.asset_id), "storage_uri": uri, "fit": visual.fit})
    report = await run_in_threadpool(
        export_quick_reel,
        composed,
        org_id=str(org_id),
        visuals=visuals,
        settings=Settings(),
        storage=storage,
    )
    report["download_path"] = f"/orgs/{org_id}/quick-reel/renders/{report['export_id']}/download"
    report["duration_seconds"] = composed.duration_seconds
    return report


@router.get(
    "/orgs/{org_id}/quick-reel/renders/{render_id}/download",
    response_model=SignedDownloadOut,
)
def download_render(
    org_id: uuid.UUID, render_id: str, db: Session = Depends(get_db)
) -> SignedDownloadOut:
    if db.get(Org, org_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Org not found")
    _require_render_id(render_id)
    settings = Settings()
    report = read_quick_reel_qa(
        org_id=str(org_id), render_id=render_id, settings=settings, storage=_quick_reel_storage()
    )
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Render not found")
    return build_signed_download(storage_uri=str(report["video_storage_uri"]))


def _require_render_id(render_id: str) -> None:
    if not re.fullmatch(_RENDER_ID_PATTERN, render_id):
        raise HTTPException(
            status_code=422, detail="render_id must be 8-64 lowercase hex characters"
        )


@router.post(
    "/orgs/{org_id}/pages/{page_id}/quick-reel/reels",
    response_model=ReelOut,
    status_code=status.HTTP_201_CREATED,
)
def send_quick_reel_to_review(
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    body: QuickReelSaveIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> ReelOut:
    page = _page_or_404(db, org_id, page_id)
    composed = _compose(page, body)

    asset_ids = {visual.asset_id for visual in body.visuals}
    if asset_ids:
        found = {
            row[0]
            for row in db.query(Asset.id).filter(Asset.org_id == org_id, Asset.id.in_(asset_ids))
        }
        missing = sorted(str(asset_id) for asset_id in asset_ids - found)
        if missing:
            raise HTTPException(
                status_code=422, detail=f"Unknown asset(s) for this org: {', '.join(missing)}"
            )

    family = _quick_reel_family(db, request, org_id=org_id, page_id=page_id)

    if body.client_request_id is not None:
        existing = (
            db.query(Reel)
            .filter(
                Reel.reel_family_id == family.id,
                Reel.metadata_[QUICK_REEL_METADATA_KEY]["client_request_id"].astext
                == str(body.client_request_id),
            )
            .first()
        )
        if existing is not None:
            db.commit()
            response.status_code = status.HTTP_200_OK
            return reel_to_out(existing, page_id=page_id)

    actor_id, _ = _actor(request)
    qa_report = (
        None
        if body.render is None
        else read_quick_reel_qa(
            org_id=str(org_id),
            render_id=body.render.render_id,
            settings=Settings(),
            storage=_quick_reel_storage(),
        )
    )
    metadata: dict[str, Any] = {
        "source": QUICK_REEL_SOURCE,
        QUICK_REEL_METADATA_KEY: {
            "schema_version": 1,
            "topic": body.topic,
            "hook": body.hook.model_dump(mode="json"),
            "selection": body.selection.model_dump(mode="json"),
            "branches": body.branches.model_dump(mode="json"),
            "composed": composed.model_dump(mode="json"),
            "caption": body.caption.strip(),
            "visuals": [visual.model_dump(mode="json") for visual in body.visuals],
            "render": None if body.render is None else body.render.model_dump(mode="json"),
            "generation_source": body.generation_source,
            "client_request_id": (
                None if body.client_request_id is None else str(body.client_request_id)
            ),
            "sent_by": actor_id,
            "qa": _qa_summary(body, qa_report),
        },
    }
    qa_failed = qa_report is not None and qa_report.get("status") == "fail"
    reel = Reel(
        org_id=org_id,
        reel_family_id=family.id,
        origin=ReelOrigin.GENERATED.value,
        status=(
            GeneratedReelStatus.QA_FAILED.value if qa_failed else GeneratedReelStatus.READY.value
        ),
        variant_label=_variant_label(body.selection),
        metadata_=metadata,
    )
    db.add(reel)
    try:
        db.flush()
        _audit(
            db,
            request,
            org_id=org_id,
            action="reel.created",
            resource_type="reel",
            resource_id=reel.id,
            payload={
                "page_id": str(page_id),
                "family_id": str(family.id),
                "origin": reel.origin,
                "status": reel.status,
                "variant_label": reel.variant_label,
                "source": QUICK_REEL_SOURCE,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(reel)
    return reel_to_out(reel, page_id=page_id)


def _qa_summary(body: QuickReelSaveIn, report: dict[str, Any] | None) -> dict[str, Any]:
    overlay_trace_status = None if body.render is None else body.render.overlay_trace_status
    if report is None:
        return {
            "status": "not_run",
            "reason": (
                "No render was exported."
                if body.render is None
                else "The render was not uploaded for QA (PUT …/renders/{id}/video, POST …/qa)."
            ),
            "overlay_trace_status": overlay_trace_status,
        }
    return {
        "status": report.get("status"),
        "video_storage_uri": report.get("video_storage_uri"),
        "trace_storage_uri": report.get("trace_storage_uri"),
        "soundtrack_id": report.get("soundtrack_id"),
        "blocking_gates": [item.get("gate_name") for item in report.get("blocking_failures", [])],
        "warnings": report.get("warnings", []),
        "overlay_trace_status": overlay_trace_status,
    }


__all__ = ["router"]
