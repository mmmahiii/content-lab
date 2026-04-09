"""Persistence helpers for asset storage and staged Runway generation."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine, RowMapping
from sqlalchemy.orm import Session, sessionmaker

from content_lab_assets.registry import (
    PHASE1_READY_ASSET_STATUSES,
    build_generation_idempotency_key,
)
from content_lab_shared.settings import Settings

PERSISTENCE_METADATA_KEY = "storage"

_ASSET_STATUS_FAILED = "failed"
_ASSET_STATUS_READY = "ready"
_PROVIDER_NAME = "runway"
_TASK_STATUS_FAILED = "failed"
_TASK_STATUS_RETRYING = "retrying"
_TASK_STATUS_RUNNING = "running"
_TASK_STATUS_SUCCEEDED = "succeeded"

_UPDATE_TASK_RESULT_STMT = text(
    """
    UPDATE tasks
    SET status = :status,
        result = :result,
        updated_at = NOW()
    WHERE id = :task_id
    """
).bindparams(bindparam("result", type_=JSONB()))

_UPDATE_ASSET_FULL_STMT = text(
    """
    UPDATE assets
    SET status = :status,
        storage_uri = :storage_uri,
        content_hash = :content_hash,
        metadata = :metadata
    WHERE id = :asset_id
    """
).bindparams(bindparam("metadata", type_=JSONB()))

_UPDATE_ASSET_METADATA_STMT = text(
    """
    UPDATE assets
    SET metadata = :metadata
    WHERE id = :asset_id
    """
).bindparams(bindparam("metadata", type_=JSONB()))

_INSERT_PROVIDER_JOB_STMT = text(
    """
    INSERT INTO provider_jobs (
        id,
        org_id,
        provider,
        external_ref,
        task_id,
        status,
        metadata
    ) VALUES (
        :id,
        :org_id,
        :provider,
        :external_ref,
        :task_id,
        :status,
        :metadata
    )
    """
).bindparams(bindparam("metadata", type_=JSONB()))

_UPDATE_PROVIDER_JOB_STMT = text(
    """
    UPDATE provider_jobs
    SET external_ref = :external_ref,
        task_id = :task_id,
        status = :status,
        metadata = :metadata,
        updated_at = NOW()
    WHERE id = :provider_job_id
    """
).bindparams(bindparam("metadata", type_=JSONB()))


@dataclass(frozen=True, slots=True)
class AssetMediaMetadata:
    """Optional media metadata captured alongside persisted asset bytes."""

    width: int | None = None
    height: int | None = None
    fps: int | None = None
    duration_seconds: float | int | None = None

    def as_metadata(self) -> dict[str, int | float]:
        metadata: dict[str, int | float] = {}
        if self.width is not None:
            metadata["width"] = self.width
        if self.height is not None:
            metadata["height"] = self.height
        if self.fps is not None:
            metadata["fps"] = self.fps
        if self.duration_seconds is not None:
            metadata["duration_seconds"] = self.duration_seconds
        return metadata


@dataclass(frozen=True, slots=True)
class AssetPersistenceFailure:
    """Failure details retained for later asset-storage reconciliation."""

    stage: str
    message: str
    error_type: str

    def as_metadata(self) -> dict[str, str]:
        return {
            "stage": self.stage,
            "message": self.message,
            "error_type": self.error_type,
        }


@dataclass(frozen=True, slots=True)
class AssetPersistenceRecord:
    """Database-facing persistence outcome for a stored asset object."""

    storage_uri: str
    content_hash: str
    size_bytes: int | None = None
    content_type: str | None = None
    media_metadata: AssetMediaMetadata = field(default_factory=AssetMediaMetadata)


def merge_asset_metadata(
    existing: Mapping[str, Any] | None = None,
    *,
    media_metadata: AssetMediaMetadata | None = None,
    state: str | None = None,
    storage_uri: str | None = None,
    content_hash: str | None = None,
    size_bytes: int | None = None,
    content_type: str | None = None,
    failure: AssetPersistenceFailure | None = None,
) -> dict[str, Any]:
    """Merge persistence state into asset metadata without dropping prior fields."""

    metadata = dict(existing or {})
    if media_metadata is not None:
        metadata.update(media_metadata.as_metadata())

    storage_metadata = _storage_metadata(metadata)
    if state is not None:
        storage_metadata["state"] = state
    if storage_uri is not None:
        storage_metadata["storage_uri"] = storage_uri
    if content_hash is not None:
        storage_metadata["content_hash"] = content_hash
    if size_bytes is not None:
        storage_metadata["size_bytes"] = size_bytes
    if content_type is not None:
        storage_metadata["content_type"] = content_type
    if failure is not None:
        storage_metadata["failure"] = failure.as_metadata()
    elif state == "ready":
        storage_metadata.pop("failure", None)

    if storage_metadata:
        metadata[PERSISTENCE_METADATA_KEY] = storage_metadata
    return metadata


@dataclass(frozen=True, slots=True)
class ProviderJobSnapshot:
    """Provider job fields mirrored into Postgres."""

    id: uuid.UUID
    org_id: uuid.UUID
    provider: str
    external_ref: str
    task_id: uuid.UUID | None
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StoredRunwayGeneration:
    """Materialized staged-asset generation state used by the worker actor."""

    asset_id: uuid.UUID
    org_id: uuid.UUID
    asset_class: str
    asset_status: str
    asset_source: str
    storage_uri: str
    asset_key: str | None
    asset_key_hash: str
    asset_metadata: dict[str, Any] = field(default_factory=dict)
    canonical_params: dict[str, Any] = field(default_factory=dict)
    task_id: uuid.UUID | None = None
    task_type: str | None = None
    task_status: str | None = None
    task_idempotency_key: str | None = None
    task_payload: dict[str, Any] = field(default_factory=dict)
    task_result: dict[str, Any] | None = None
    provider_job: ProviderJobSnapshot | None = None

    @property
    def is_ready(self) -> bool:
        return (
            self.asset_status in PHASE1_READY_ASSET_STATUSES
            and self.task_status == _TASK_STATUS_SUCCEEDED
        )

    @property
    def is_terminal_failure(self) -> bool:
        return self.asset_status == _ASSET_STATUS_FAILED and self.task_status == _TASK_STATUS_FAILED


class RunwayAssetStore(Protocol):
    """Persistence boundary consumed by the Runway worker actor."""

    def load_generation(self, *, asset_id: uuid.UUID | str) -> StoredRunwayGeneration: ...

    def mark_running(
        self,
        generation: StoredRunwayGeneration,
        *,
        external_ref: str | None,
        provider_status: str,
        provider_metadata: Mapping[str, Any] | None = None,
        task_result: Mapping[str, Any] | None = None,
    ) -> StoredRunwayGeneration: ...

    def mark_retryable(
        self,
        generation: StoredRunwayGeneration,
        *,
        reason: str,
        provider_status: str,
        provider_metadata: Mapping[str, Any] | None = None,
        task_result: Mapping[str, Any] | None = None,
        external_ref: str | None = None,
    ) -> StoredRunwayGeneration: ...

    def mark_failed(
        self,
        generation: StoredRunwayGeneration,
        *,
        reason: str,
        provider_status: str,
        provider_metadata: Mapping[str, Any] | None = None,
        task_result: Mapping[str, Any] | None = None,
        asset_metadata: Mapping[str, Any] | None = None,
        external_ref: str | None = None,
    ) -> StoredRunwayGeneration: ...

    def mark_ready(
        self,
        generation: StoredRunwayGeneration,
        *,
        storage_uri: str,
        content_hash: str,
        provider_status: str,
        provider_metadata: Mapping[str, Any] | None = None,
        task_result: Mapping[str, Any] | None = None,
        asset_metadata: Mapping[str, Any] | None = None,
        external_ref: str | None = None,
    ) -> StoredRunwayGeneration: ...


class SQLRunwayAssetStore:
    """SQL-backed phase-1 generation store shared by worker actors."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        engine: Engine | None = None,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        if session_factory is None:
            resolved_settings = settings or Settings()
            resolved_engine = engine or create_engine(
                resolved_settings.database_url,
                pool_pre_ping=True,
            )
            session_factory = sessionmaker(
                bind=resolved_engine,
                class_=Session,
                expire_on_commit=False,
            )
        self._session_factory = session_factory

    def load_generation(self, *, asset_id: uuid.UUID | str) -> StoredRunwayGeneration:
        asset_uuid = _parse_uuid(asset_id, field_name="asset_id")
        with self._session_factory() as session:
            asset_row = (
                session.execute(
                    text(
                        """
                    SELECT
                        id,
                        org_id,
                        asset_class,
                        status,
                        source,
                        storage_uri,
                        asset_key,
                        asset_key_hash,
                        metadata
                    FROM assets
                    WHERE id = :asset_id
                    """
                    ),
                    {"asset_id": asset_uuid},
                )
                .mappings()
                .one_or_none()
            )
            if asset_row is None:
                raise LookupError(f"Asset {asset_uuid} was not found")

            asset_key_hash = str(asset_row["asset_key_hash"] or "").strip()
            if not asset_key_hash:
                raise LookupError(f"Asset {asset_uuid} is missing asset_key_hash")

            gen_params_row = (
                session.execute(
                    text(
                        """
                    SELECT asset_id, seq, asset_key_hash, canonical_params
                    FROM asset_gen_params
                    WHERE asset_id = :asset_id
                    ORDER BY seq DESC
                    LIMIT 1
                    """
                    ),
                    {"asset_id": asset_uuid},
                )
                .mappings()
                .one_or_none()
            )
            if gen_params_row is None:
                raise LookupError(f"Asset {asset_uuid} is missing generation parameters")

            task_row = (
                session.execute(
                    text(
                        """
                    SELECT id, task_type, status, idempotency_key, payload, result
                    FROM tasks
                    WHERE org_id = :org_id AND idempotency_key = :idempotency_key
                    LIMIT 1
                    """
                    ),
                    {
                        "org_id": asset_row["org_id"],
                        "idempotency_key": build_generation_idempotency_key(
                            asset_key_hash=asset_key_hash
                        ),
                    },
                )
                .mappings()
                .one_or_none()
            )

            provider_job_row = None
            if task_row is not None:
                provider_job_row = (
                    session.execute(
                        text(
                            """
                        SELECT id, org_id, provider, external_ref, task_id, status, metadata
                        FROM provider_jobs
                        WHERE task_id = :task_id AND provider = :provider
                        ORDER BY updated_at DESC NULLS LAST, created_at DESC
                        LIMIT 1
                        """
                        ),
                        {"task_id": task_row["id"], "provider": _PROVIDER_NAME},
                    )
                    .mappings()
                    .one_or_none()
                )

        return StoredRunwayGeneration(
            asset_id=_row_uuid(asset_row["id"], field_name="asset_id"),
            org_id=_row_uuid(asset_row["org_id"], field_name="org_id"),
            asset_class=str(asset_row["asset_class"]),
            asset_status=str(asset_row["status"]),
            asset_source=str(asset_row["source"]),
            storage_uri=str(asset_row["storage_uri"]),
            asset_key=None if asset_row["asset_key"] is None else str(asset_row["asset_key"]),
            asset_key_hash=asset_key_hash,
            asset_metadata=_mapping(asset_row["metadata"]),
            canonical_params=_mapping(gen_params_row["canonical_params"]),
            task_id=None if task_row is None else _row_uuid(task_row["id"], field_name="task_id"),
            task_type=None if task_row is None else str(task_row["task_type"]),
            task_status=None if task_row is None else str(task_row["status"]),
            task_idempotency_key=None if task_row is None else str(task_row["idempotency_key"]),
            task_payload={} if task_row is None else _mapping(task_row["payload"]),
            task_result=None if task_row is None else _optional_mapping(task_row["result"]),
            provider_job=None if provider_job_row is None else self._provider_job(provider_job_row),
        )

    def mark_running(
        self,
        generation: StoredRunwayGeneration,
        *,
        external_ref: str | None,
        provider_status: str,
        provider_metadata: Mapping[str, Any] | None = None,
        task_result: Mapping[str, Any] | None = None,
    ) -> StoredRunwayGeneration:
        return self._apply_transition(
            generation,
            task_status=_TASK_STATUS_RUNNING,
            provider_status=provider_status,
            external_ref=external_ref,
            provider_metadata=provider_metadata,
            task_result=task_result,
        )

    def mark_retryable(
        self,
        generation: StoredRunwayGeneration,
        *,
        reason: str,
        provider_status: str,
        provider_metadata: Mapping[str, Any] | None = None,
        task_result: Mapping[str, Any] | None = None,
        external_ref: str | None = None,
    ) -> StoredRunwayGeneration:
        result = {
            "reason": reason,
            "retryable": True,
            **({} if task_result is None else dict(task_result)),
        }
        return self._apply_transition(
            generation,
            task_status=_TASK_STATUS_RETRYING,
            provider_status=provider_status,
            external_ref=external_ref,
            provider_metadata=provider_metadata,
            task_result=result,
        )

    def mark_failed(
        self,
        generation: StoredRunwayGeneration,
        *,
        reason: str,
        provider_status: str,
        provider_metadata: Mapping[str, Any] | None = None,
        task_result: Mapping[str, Any] | None = None,
        asset_metadata: Mapping[str, Any] | None = None,
        external_ref: str | None = None,
    ) -> StoredRunwayGeneration:
        result = {
            "reason": reason,
            "retryable": False,
            **({} if task_result is None else dict(task_result)),
        }
        return self._apply_transition(
            generation,
            task_status=_TASK_STATUS_FAILED,
            provider_status=provider_status,
            external_ref=external_ref,
            provider_metadata=provider_metadata,
            task_result=result,
            asset_status=_ASSET_STATUS_FAILED,
            asset_metadata=asset_metadata,
        )

    def mark_ready(
        self,
        generation: StoredRunwayGeneration,
        *,
        storage_uri: str,
        content_hash: str,
        provider_status: str,
        provider_metadata: Mapping[str, Any] | None = None,
        task_result: Mapping[str, Any] | None = None,
        asset_metadata: Mapping[str, Any] | None = None,
        external_ref: str | None = None,
    ) -> StoredRunwayGeneration:
        return self._apply_transition(
            generation,
            task_status=_TASK_STATUS_SUCCEEDED,
            provider_status=provider_status,
            external_ref=external_ref,
            provider_metadata=provider_metadata,
            task_result=task_result,
            asset_status=_ASSET_STATUS_READY,
            storage_uri=storage_uri,
            content_hash=content_hash,
            asset_metadata=asset_metadata,
        )

    def _apply_transition(
        self,
        generation: StoredRunwayGeneration,
        *,
        task_status: str,
        provider_status: str,
        external_ref: str | None,
        provider_metadata: Mapping[str, Any] | None = None,
        task_result: Mapping[str, Any] | None = None,
        asset_status: str | None = None,
        storage_uri: str | None = None,
        content_hash: str | None = None,
        asset_metadata: Mapping[str, Any] | None = None,
    ) -> StoredRunwayGeneration:
        with self._session_factory.begin() as session:
            if generation.task_id is not None:
                session.execute(
                    _UPDATE_TASK_RESULT_STMT,
                    {
                        "status": task_status,
                        "result": None if task_result is None else dict(task_result),
                        "task_id": generation.task_id,
                    },
                )

            if asset_status is not None or storage_uri is not None or content_hash is not None:
                metadata = _merge_dicts(generation.asset_metadata, asset_metadata)
                session.execute(
                    _UPDATE_ASSET_FULL_STMT,
                    {
                        "status": asset_status or generation.asset_status,
                        "storage_uri": storage_uri or generation.storage_uri,
                        "content_hash": content_hash,
                        "metadata": metadata,
                        "asset_id": generation.asset_id,
                    },
                )
            elif asset_metadata:
                session.execute(
                    _UPDATE_ASSET_METADATA_STMT,
                    {
                        "metadata": _merge_dicts(generation.asset_metadata, asset_metadata),
                        "asset_id": generation.asset_id,
                    },
                )

            if external_ref is not None:
                self._upsert_provider_job(
                    session,
                    generation=generation,
                    external_ref=external_ref,
                    provider_status=provider_status,
                    provider_metadata=provider_metadata,
                )

        return self.load_generation(asset_id=generation.asset_id)

    def _upsert_provider_job(
        self,
        session: Session,
        *,
        generation: StoredRunwayGeneration,
        external_ref: str,
        provider_status: str,
        provider_metadata: Mapping[str, Any] | None,
    ) -> None:
        existing = (
            session.execute(
                text(
                    """
                SELECT id, metadata
                FROM provider_jobs
                WHERE provider = :provider AND external_ref = :external_ref
                LIMIT 1
                """
                ),
                {"provider": _PROVIDER_NAME, "external_ref": external_ref},
            )
            .mappings()
            .one_or_none()
        )

        existing_provider_job_id: uuid.UUID | None = None
        if existing is not None:
            existing_provider_job_id = _row_uuid(existing["id"], field_name="provider_job_id")
        elif generation.provider_job is not None:
            existing_provider_job_id = generation.provider_job.id

        metadata = _merge_dicts(
            generation.provider_job.metadata if generation.provider_job is not None else {},
            provider_metadata,
        )

        if existing_provider_job_id is None:
            session.execute(
                _INSERT_PROVIDER_JOB_STMT,
                {
                    "id": uuid.uuid4(),
                    "org_id": generation.org_id,
                    "provider": _PROVIDER_NAME,
                    "external_ref": external_ref,
                    "task_id": generation.task_id,
                    "status": provider_status,
                    "metadata": metadata,
                },
            )
            return

        session.execute(
            _UPDATE_PROVIDER_JOB_STMT,
            {
                "external_ref": external_ref,
                "task_id": generation.task_id,
                "status": provider_status,
                "metadata": metadata,
                "provider_job_id": existing_provider_job_id,
            },
        )

    @staticmethod
    def _provider_job(row: RowMapping) -> ProviderJobSnapshot:
        return ProviderJobSnapshot(
            id=_row_uuid(row["id"], field_name="provider_job_id"),
            org_id=_row_uuid(row["org_id"], field_name="provider_job_org_id"),
            provider=str(row["provider"]),
            external_ref=str(row["external_ref"]),
            task_id=None
            if row["task_id"] is None
            else _row_uuid(row["task_id"], field_name="provider_job_task_id"),
            status=str(row["status"]),
            metadata=_mapping(row["metadata"]),
        )


def _storage_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    current = metadata.get(PERSISTENCE_METADATA_KEY)
    if isinstance(current, Mapping):
        return dict(current)
    return {}


def _parse_uuid(value: uuid.UUID | str, *, field_name: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return uuid.UUID(normalized)


def _row_uuid(value: Any, *, field_name: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    if value is None:
        raise ValueError(f"{field_name} must not be null")
    return uuid.UUID(str(value))


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _optional_mapping(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return _mapping(value)


def _merge_dicts(
    left: Mapping[str, Any] | None,
    right: Mapping[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(left or {})
    if right is not None:
        merged.update(dict(right))
    return merged


__all__ = [
    "AssetMediaMetadata",
    "AssetPersistenceFailure",
    "AssetPersistenceRecord",
    "PERSISTENCE_METADATA_KEY",
    "ProviderJobSnapshot",
    "RunwayAssetStore",
    "SQLRunwayAssetStore",
    "StoredRunwayGeneration",
    "merge_asset_metadata",
]
