"""Phase-1 asset registry service backed by the API's SQLAlchemy models."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from content_lab_api.models import Asset, AssetGenParam, AuditLog, Org, Task
from content_lab_api.schemas.assets import AssetResolveDecision, AssetResolveRequest
from content_lab_api.services.provider_jobs import record_provider_job_submission
from content_lab_api.services.run_tasks import ensure_task_row
from content_lab_assets.registry import (
    AssetKey,
    GenerateDecision,
    Phase1ProviderLockError,
    RegistryAsset,
    RegistryAssetGenParams,
    RegistryGenerationIntentRecord,
    build_generation_idempotency_key,
    resolve_phase1_asset,
)
from content_lab_runs import TaskRowSpec, TaskStatus
from content_lab_shared.logging import ANONYMOUS_ACTOR
from content_lab_shared.settings import Settings
from content_lab_storage import build_key

_STAGED_ASSET_STATUS = "staged"


def _get_org_or_404(db: Session, org_id: uuid.UUID) -> Org:
    org = db.get(Org, org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Org not found")
    return org


def _actor_info(request: Request) -> tuple[str | None, str]:
    actor = getattr(request.state, "actor", ANONYMOUS_ACTOR)
    actor_id = None if actor == ANONYMOUS_ACTOR else actor
    actor_type = "anonymous" if actor_id is None else "request_header"
    return actor_id, actor_type


def _record_generation_audit(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    task: Task,
    decision: GenerateDecision,
) -> None:
    actor_id, actor_type = _actor_info(request)
    db.execute(
        insert(AuditLog).values(
            id=uuid.uuid4(),
            org_id=org_id,
            action="asset.generate.requested",
            resource_type="task",
            actor_type=actor_type,
            actor_id=actor_id,
            resource_id=str(task.id),
            payload={
                "task_type": task.task_type,
                "task_status": task.status,
                "asset_id": str(decision.generation_intent.asset_id),
                "asset_key_hash": decision.asset_key_hash,
                "provider": decision.provider,
                "model": decision.model,
            },
        )
    )


class SQLAlchemyPhase1AssetRegistryStore:
    """SQLAlchemy adapter for the shared phase-1 asset registry resolver."""

    def __init__(self, db: Session, *, settings: Settings | None = None) -> None:
        self._db = db
        self._settings = settings or Settings()

    def get_asset_by_key_hash(
        self,
        *,
        org_id: uuid.UUID,
        asset_key_hash: str,
    ) -> RegistryAsset | None:
        asset = (
            self._db.query(Asset)
            .filter(Asset.org_id == org_id, Asset.asset_key_hash == asset_key_hash)
            .one_or_none()
        )
        return None if asset is None else self._to_registry_asset(asset)

    def get_generation_params(
        self,
        *,
        asset_id: uuid.UUID,
        asset_key_hash: str,
    ) -> RegistryAssetGenParams | None:
        row = (
            self._db.query(AssetGenParam)
            .filter(
                AssetGenParam.asset_id == asset_id,
                AssetGenParam.asset_key_hash == asset_key_hash,
            )
            .order_by(AssetGenParam.seq.desc())
            .one_or_none()
        )
        return None if row is None else self._to_registry_gen_params(row)

    def ensure_generation_intent(
        self,
        *,
        org_id: uuid.UUID,
        asset_key: AssetKey,
        payload: Mapping[str, Any],
    ) -> RegistryGenerationIntentRecord:
        existing_asset = (
            self._db.query(Asset)
            .filter(Asset.org_id == org_id, Asset.asset_key_hash == asset_key.asset_key_hash)
            .one_or_none()
        )
        if existing_asset is not None:
            return self._hydrate_existing_intent(
                asset=existing_asset,
                org_id=org_id,
                asset_key=asset_key,
                payload=payload,
            )

        created = False
        asset = Asset(
            org_id=org_id,
            asset_class=asset_key.canonical_params["asset_class"],
            storage_uri="s3://content-lab/assets/pending",
            source=asset_key.canonical_params["provider"],
            status=_STAGED_ASSET_STATUS,
            asset_key=asset_key.asset_key,
            asset_key_hash=asset_key.asset_key_hash,
            metadata_=self._intent_metadata(payload),
        )

        try:
            with self._db.begin_nested():
                self._db.add(asset)
                self._db.flush()
                asset.storage_uri = self._staged_storage_uri(asset.id)
                self._db.flush()
                self._db.add(
                    AssetGenParam(
                        org_id=org_id,
                        asset_id=asset.id,
                        seq=0,
                        asset_key_hash=asset_key.asset_key_hash,
                        canonical_params=dict(asset_key.canonical_params),
                    )
                )
                self._db.flush()
                created = True
        except IntegrityError:
            existing_asset = (
                self._db.query(Asset)
                .filter(Asset.org_id == org_id, Asset.asset_key_hash == asset_key.asset_key_hash)
                .one_or_none()
            )
            if existing_asset is None:
                raise
            asset = existing_asset

        return self._hydrate_existing_intent(
            asset=asset,
            org_id=org_id,
            asset_key=asset_key,
            payload=payload,
            created=created,
        )

    def _hydrate_existing_intent(
        self,
        *,
        asset: Asset,
        org_id: uuid.UUID,
        asset_key: AssetKey,
        payload: Mapping[str, Any],
        created: bool = False,
    ) -> RegistryGenerationIntentRecord:
        gen_params = self.get_generation_params(
            asset_id=asset.id,
            asset_key_hash=asset_key.asset_key_hash,
        )
        if gen_params is None:
            gen_params = self._create_missing_gen_params(
                asset=asset,
                org_id=org_id,
                asset_key=asset_key,
            )

        stored_payload = self._intent_payload(asset)
        if stored_payload is None:
            asset.metadata_ = self._intent_metadata(payload)
            self._db.flush()
            stored_payload = dict(payload)

        return RegistryGenerationIntentRecord(
            asset_id=asset.id,
            org_id=asset.org_id,
            asset_class=asset.asset_class,
            status=asset.status,
            source=asset.source,
            storage_uri=asset.storage_uri,
            asset_key=asset_key.asset_key,
            asset_key_hash=asset_key.asset_key_hash,
            idempotency_key=build_generation_idempotency_key(
                asset_key_hash=asset_key.asset_key_hash
            ),
            payload=dict(stored_payload),
            canonical_params=dict(gen_params.canonical_params),
            created=created,
        )

    def _create_missing_gen_params(
        self,
        *,
        asset: Asset,
        org_id: uuid.UUID,
        asset_key: AssetKey,
    ) -> RegistryAssetGenParams:
        latest = (
            self._db.query(AssetGenParam)
            .filter(AssetGenParam.asset_id == asset.id)
            .order_by(AssetGenParam.seq.desc())
            .one_or_none()
        )
        next_seq = 0 if latest is None else latest.seq + 1
        row = AssetGenParam(
            org_id=org_id,
            asset_id=asset.id,
            seq=next_seq,
            asset_key_hash=asset_key.asset_key_hash,
            canonical_params=dict(asset_key.canonical_params),
        )
        with self._db.begin_nested():
            self._db.add(row)
            self._db.flush()
        return self._to_registry_gen_params(row)

    def _staged_storage_uri(self, asset_id: uuid.UUID) -> str:
        key = build_key(
            self._settings.asset_storage_prefix,
            "raw",
            str(asset_id),
            "source.bin",
        )
        return f"s3://{self._settings.minio_bucket}/{key}"

    @staticmethod
    def _intent_metadata(payload: Mapping[str, Any]) -> dict[str, Any]:
        return {"intent": dict(payload)}

    @staticmethod
    def _intent_payload(asset: Asset) -> dict[str, Any] | None:
        metadata = dict(asset.metadata_ or {})
        intent = metadata.get("intent")
        if not isinstance(intent, Mapping):
            return None
        return dict(intent)

    @staticmethod
    def _to_registry_asset(asset: Asset) -> RegistryAsset:
        return RegistryAsset(
            asset_id=asset.id,
            org_id=asset.org_id,
            asset_class=asset.asset_class,
            status=asset.status,
            source=asset.source,
            storage_uri=asset.storage_uri,
            asset_key=asset.asset_key,
            asset_key_hash=asset.asset_key_hash,
            metadata=dict(asset.metadata_ or {}),
        )

    @staticmethod
    def _to_registry_gen_params(row: AssetGenParam) -> RegistryAssetGenParams:
        return RegistryAssetGenParams(
            asset_id=row.asset_id,
            seq=row.seq,
            asset_key_hash=row.asset_key_hash,
            canonical_params=dict(row.canonical_params or {}),
        )


def resolve_asset_request(
    db: Session,
    request: Request,
    *,
    org_id: uuid.UUID,
    body: AssetResolveRequest,
) -> AssetResolveDecision:
    """Resolve an asset request through the shared phase-1 registry path."""

    _get_org_or_404(db, org_id)
    store = SQLAlchemyPhase1AssetRegistryStore(db)
    try:
        decision = resolve_phase1_asset(
            store,
            org_id=org_id,
            asset_class=body.asset_class,
            provider=body.provider,
            model=body.model,
            prompt=body.prompt,
            negative_prompt=body.negative_prompt,
            seed=body.seed,
            duration_seconds=body.duration_seconds,
            fps=body.fps,
            ratio=body.ratio,
            motion=body.motion,
            init_image_hash=body.init_image_hash,
            reference_asset_ids=body.reference_asset_ids,
            request_payload=jsonable_encoder(body.model_dump(mode="python")),
        )
    except Phase1ProviderLockError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    if not isinstance(decision, GenerateDecision):
        return decision

    task_result = ensure_task_row(
        db,
        spec=TaskRowSpec(
            org_id=org_id,
            task_type=decision.generation_intent.task_type,
            idempotency_key=decision.generation_intent.idempotency_key,
            status=TaskStatus.QUEUED,
            payload=dict(decision.generation_intent.payload),
        ),
    )
    task: Task = task_result.record
    decision.generation_intent.task_id = task.id
    decision.generation_intent.task_status = task.status
    decision.generation_intent.task_type = task.task_type
    decision.provenance["task_id"] = str(task.id)
    provider_job = record_provider_job_submission(
        db,
        org_id=org_id,
        task_id=task.id,
        asset_id=decision.generation_intent.asset_id,
        asset_key=decision.generation_intent.asset_key,
        asset_key_hash=decision.generation_intent.asset_key_hash,
        request_payload=decision.generation_intent.payload.get("request"),
        provider_payload=decision.generation_intent.payload["provider_submission"],
        task_status=task.status,
        asset_status=decision.generation_intent.asset_status,
    )
    decision.provenance["provider_job_id"] = str(provider_job.id)
    decision.provenance["provider_external_ref"] = provider_job.external_ref

    if task_result.created:
        _record_generation_audit(
            db,
            request,
            org_id=org_id,
            task=task,
            decision=decision,
        )

    db.commit()
    db.refresh(task)
    return decision
