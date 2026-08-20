"""Editing worker actor definitions."""

from __future__ import annotations

import hashlib
import json
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, cast

import dramatiq
from pydantic import ValidationError
from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine, RowMapping
from sqlalchemy.orm import Session, sessionmaker

from content_lab_editing.composition_manifest import CompositionLayer, CompositionManifest
from content_lab_editing.composition_preflight import (
    CompositionPreflightError,
    SourceAssetInput,
    StorageObjectProbe,
    coerce_source_asset_reference,
    ensure_composition_preflight,
)
from content_lab_editing.cover import CoverFrameArtifact, extract_cover_frame
from content_lab_editing.ffmpeg import FFmpegError
from content_lab_editing.layered_ffmpeg import LayeredCompositionResult, compose_layered_reel
from content_lab_runs import RunStatus, TaskStatus
from content_lab_shared.settings import Settings
from content_lab_storage import (
    CanonicalStorageLayout,
    S3StorageClient,
    S3StorageConfig,
    StorageRef,
    StoredObject,
    checksum_bytes,
)
from content_lab_worker.actors._shared import ActorLike, build_queue_name, get_actor_logger

logger = get_actor_logger("editing")
QUEUE_NAME = build_queue_name("editing")

LAYERED_COMPOSITION_TASK_TYPE = "layered_composition.render"
LAYERED_COMPOSITION_METADATA_KEY = "layered_composition"
FINAL_RENDER_ASSET_CLASS = "final_render"
FINAL_RENDER_SOURCE = "layered_composition"
_WORKFLOW_PROCESS_REEL = "process_reel"
_DEFAULT_RENDER_TIMEOUT_SECONDS = 600.0
_DEFAULT_MAX_RETRIES = 3


class RetryableCompositionActorError(RuntimeError):
    """Raised when the actor persisted retry state and Dramatiq should retry later."""


class TerminalCompositionActorError(RuntimeError):
    """Raised when a composition request is invalid or cannot become renderable by retrying."""


class LayeredCompositionStorageClient(Protocol):
    """Storage surface needed by the composition renderer and packager."""

    def head_object(self, *, storage_uri: str) -> object: ...

    def get_object(self, *, storage_uri: str) -> object: ...

    def put_object(
        self,
        *,
        data: bytes,
        ref: StorageRef | None = None,
        storage_uri: str | None = None,
        key: str | None = None,
        bucket: str | None = None,
        content_type: str | None = None,
        metadata: Mapping[str, str] | None = None,
        checksum_sha256: str | None = None,
    ) -> StoredObject: ...


class LayeredCompositionRenderer(Protocol):
    """Callable boundary around the FFmpeg renderer."""

    def __call__(
        self,
        manifest: CompositionManifest,
        *,
        asset_sources: Mapping[str, SourceAssetInput],
        output_path: str | Path,
        storage_client: LayeredCompositionStorageClient | None = None,
        staging_dir: str | Path | None = None,
        timeout_seconds: float | None = None,
    ) -> LayeredCompositionResult: ...


class CoverExtractor(Protocol):
    """Callable boundary around cover frame extraction."""

    def __call__(
        self,
        *,
        video_path: str | Path,
        output_path: str | Path,
        timestamp_seconds: float | None = None,
        duration_seconds: float | None = None,
        ffmpeg_bin: str = "ffmpeg",
        ffprobe_bin: str = "ffprobe",
    ) -> CoverFrameArtifact: ...


@dataclass(frozen=True, slots=True)
class LayeredCompositionRequest:
    """Materialized run/task/reel state needed for one composition render."""

    run_id: uuid.UUID
    org_id: uuid.UUID
    reel_id: uuid.UUID
    workflow_key: str
    run_status: str
    run_input_params: dict[str, Any] = field(default_factory=dict)
    run_metadata: dict[str, Any] = field(default_factory=dict)
    run_output_payload: dict[str, Any] | None = None
    task_id: uuid.UUID | None = None
    task_type: str | None = None
    task_status: str | None = None
    task_payload: dict[str, Any] = field(default_factory=dict)
    task_result: dict[str, Any] | None = None
    reel_status: str | None = None
    reel_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_ready(self) -> bool:
        return (
            self.run_status == RunStatus.SUCCEEDED.value
            and self.task_status == TaskStatus.SUCCEEDED.value
            and isinstance(self.run_output_payload, Mapping)
            and self.run_output_payload.get("status") == "ready"
        )


@dataclass(frozen=True, slots=True)
class RenderAssetRecord:
    """Derived asset row created for the final rendered video."""

    asset_id: uuid.UUID
    storage_uri: str
    content_hash: str
    size_bytes: int | None
    content_type: str | None

    def as_payload(self) -> dict[str, Any]:
        return {
            "asset_id": str(self.asset_id),
            "asset_class": FINAL_RENDER_ASSET_CLASS,
            "source": FINAL_RENDER_SOURCE,
            "storage_uri": self.storage_uri,
            "content_hash": self.content_hash,
            "size_bytes": self.size_bytes,
            "content_type": self.content_type,
        }


@dataclass(frozen=True, slots=True)
class AssetUsageSpec:
    """Asset lineage row to persist for a rendered composition."""

    asset_id: uuid.UUID
    usage_role: str
    sort_order: int | None = None
    component_role: str | None = None
    layer_role: str | None = None
    sequence_index: int | None = None
    z_index: int | None = None
    start_time: float | None = None
    end_time: float | None = None
    transform_recipe: dict[str, Any] | None = None
    transform_version: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)


class LayeredCompositionStore(Protocol):
    """Persistence boundary consumed by the layered composition actor."""

    def load_request(
        self,
        *,
        run_id: uuid.UUID | str,
        task_id: uuid.UUID | str | None = None,
    ) -> LayeredCompositionRequest: ...

    def load_asset_sources(
        self,
        request: LayeredCompositionRequest,
        *,
        asset_ids: Sequence[str],
    ) -> dict[str, SourceAssetInput]: ...

    def mark_running(
        self,
        request: LayeredCompositionRequest,
        *,
        task_result: Mapping[str, Any],
    ) -> LayeredCompositionRequest: ...

    def mark_retryable(
        self,
        request: LayeredCompositionRequest,
        *,
        reason: str,
        task_result: Mapping[str, Any],
    ) -> LayeredCompositionRequest: ...

    def mark_failed(
        self,
        request: LayeredCompositionRequest,
        *,
        reason: str,
        task_result: Mapping[str, Any],
    ) -> LayeredCompositionRequest: ...

    def mark_ready(
        self,
        request: LayeredCompositionRequest,
        *,
        package_payload: Mapping[str, Any],
        render_asset: RenderAssetRecord,
        asset_usages: Sequence[AssetUsageSpec],
        task_result: Mapping[str, Any],
    ) -> LayeredCompositionRequest: ...


_UPDATE_RUN_STMT = text(
    """
    UPDATE runs
    SET status = :status,
        output_payload = :output_payload,
        run_metadata = :run_metadata,
        started_at = CASE
            WHEN :set_started_at THEN COALESCE(started_at, NOW())
            ELSE started_at
        END,
        finished_at = CASE
            WHEN :set_finished_at THEN NOW()
            ELSE finished_at
        END,
        updated_at = NOW()
    WHERE id = :run_id
    """
).bindparams(
    bindparam("output_payload", type_=JSONB()),
    bindparam("run_metadata", type_=JSONB()),
)

_UPDATE_TASK_STMT = text(
    """
    UPDATE tasks
    SET status = :status,
        result = :result,
        updated_at = NOW()
    WHERE id = :task_id
    """
).bindparams(bindparam("result", type_=JSONB()))

_UPDATE_REEL_STMT = text(
    """
    UPDATE reels
    SET status = :status,
        metadata = :metadata,
        updated_at = NOW()
    WHERE id = :reel_id
    """
).bindparams(bindparam("metadata", type_=JSONB()))

_UPSERT_RENDER_ASSET_STMT = text(
    """
    INSERT INTO assets (
        id,
        org_id,
        asset_class,
        storage_uri,
        metadata,
        source,
        asset_key,
        asset_key_hash,
        content_hash,
        status
    ) VALUES (
        :id,
        :org_id,
        :asset_class,
        :storage_uri,
        :metadata,
        :source,
        :asset_key,
        :asset_key_hash,
        :content_hash,
        :status
    )
    ON CONFLICT (id) DO UPDATE
    SET storage_uri = EXCLUDED.storage_uri,
        metadata = EXCLUDED.metadata,
        content_hash = EXCLUDED.content_hash,
        status = EXCLUDED.status
    """
).bindparams(bindparam("metadata", type_=JSONB()))

_UPSERT_ASSET_USAGE_STMT = text(
    """
    INSERT INTO asset_usage (
        id,
        org_id,
        reel_id,
        asset_id,
        usage_role,
        sort_order,
        component_role,
        layer_role,
        sequence_index,
        z_index,
        start_time,
        end_time,
        transform_recipe,
        transform_version,
        metadata_json
    ) VALUES (
        :id,
        :org_id,
        :reel_id,
        :asset_id,
        :usage_role,
        :sort_order,
        :component_role,
        :layer_role,
        :sequence_index,
        :z_index,
        :start_time,
        :end_time,
        :transform_recipe,
        :transform_version,
        :metadata_json
    )
    ON CONFLICT ON CONSTRAINT uq_asset_usage_reel_asset_role DO UPDATE
    SET sort_order = EXCLUDED.sort_order,
        component_role = EXCLUDED.component_role,
        layer_role = EXCLUDED.layer_role,
        sequence_index = EXCLUDED.sequence_index,
        z_index = EXCLUDED.z_index,
        start_time = EXCLUDED.start_time,
        end_time = EXCLUDED.end_time,
        transform_recipe = EXCLUDED.transform_recipe,
        transform_version = EXCLUDED.transform_version,
        metadata_json = EXCLUDED.metadata_json
    """
).bindparams(
    bindparam("transform_recipe", type_=JSONB()),
    bindparam("metadata_json", type_=JSONB()),
)


class SQLLayeredCompositionStore:
    """SQL-backed run/task/reel state for layered composition jobs."""

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

    def load_request(
        self,
        *,
        run_id: uuid.UUID | str,
        task_id: uuid.UUID | str | None = None,
    ) -> LayeredCompositionRequest:
        run_uuid = _parse_uuid(run_id, field_name="run_id")
        task_uuid = None if task_id is None else _parse_uuid(task_id, field_name="task_id")
        with self._session_factory() as session:
            run_row = (
                session.execute(
                    text(
                        """
                        SELECT
                            id,
                            org_id,
                            workflow_key,
                            status,
                            input_params,
                            output_payload,
                            run_metadata
                        FROM runs
                        WHERE id = :run_id
                        """
                    ),
                    {"run_id": run_uuid},
                )
                .mappings()
                .one_or_none()
            )
            if run_row is None:
                raise LookupError(f"Run {run_uuid} was not found")

            input_params = _mapping(run_row["input_params"])
            org_id = _row_uuid(run_row["org_id"], field_name="org_id")
            reel_id = _parse_uuid(
                _required_text(input_params.get("reel_id"), field_name="input_params.reel_id"),
                field_name="reel_id",
            )
            reel_row = (
                session.execute(
                    text(
                        """
                        SELECT id, status, metadata
                        FROM reels
                        WHERE org_id = :org_id AND id = :reel_id
                        """
                    ),
                    {"org_id": org_id, "reel_id": reel_id},
                )
                .mappings()
                .one_or_none()
            )
            if reel_row is None:
                raise LookupError(f"Reel {reel_id} was not found for run {run_uuid}")

            task_row = self._load_task_row(session, org_id=org_id, run_id=run_uuid, task_id=task_uuid)

        return LayeredCompositionRequest(
            run_id=_row_uuid(run_row["id"], field_name="run_id"),
            org_id=org_id,
            reel_id=_row_uuid(reel_row["id"], field_name="reel_id"),
            workflow_key=str(run_row["workflow_key"]),
            run_status=str(run_row["status"]),
            run_input_params=input_params,
            run_metadata=_mapping(run_row["run_metadata"]),
            run_output_payload=_optional_mapping(run_row["output_payload"]),
            task_id=None if task_row is None else _row_uuid(task_row["id"], field_name="task_id"),
            task_type=None if task_row is None else str(task_row["task_type"]),
            task_status=None if task_row is None else str(task_row["status"]),
            task_payload={} if task_row is None else _mapping(task_row["payload"]),
            task_result=None if task_row is None else _optional_mapping(task_row["result"]),
            reel_status=str(reel_row["status"]),
            reel_metadata=_mapping(reel_row["metadata"]),
        )

    def load_asset_sources(
        self,
        request: LayeredCompositionRequest,
        *,
        asset_ids: Sequence[str],
    ) -> dict[str, SourceAssetInput]:
        parsed_asset_ids: list[uuid.UUID] = []
        for asset_id in asset_ids:
            try:
                parsed_asset_ids.append(_parse_uuid(asset_id, field_name="asset_id"))
            except ValueError:
                continue
        if not parsed_asset_ids:
            return {}

        with self._session_factory() as session:
            rows = (
                session.execute(
                    text(
                        """
                        SELECT id, storage_uri, status, content_hash, metadata
                        FROM assets
                        WHERE org_id = :org_id AND id = ANY(:asset_ids)
                        """
                    ),
                    {"org_id": request.org_id, "asset_ids": parsed_asset_ids},
                )
                .mappings()
                .all()
            )

        sources: dict[str, SourceAssetInput] = {}
        for row in rows:
            metadata = _mapping(row["metadata"])
            media_type = _asset_media_type(metadata)
            sources[str(row["id"])] = {
                "source": str(row["storage_uri"] or ""),
                "status": str(row["status"]),
                "content_hash": None if row["content_hash"] is None else str(row["content_hash"]),
                "media_type": media_type,
            }
        return sources

    def mark_running(
        self,
        request: LayeredCompositionRequest,
        *,
        task_result: Mapping[str, Any],
    ) -> LayeredCompositionRequest:
        return self._apply_transition(
            request,
            run_status=RunStatus.RUNNING.value,
            task_status=TaskStatus.RUNNING.value,
            reel_status="editing",
            run_output_payload=None,
            task_result=task_result,
            metadata_patch={
                LAYERED_COMPOSITION_METADATA_KEY: {
                    "status": "running",
                    "last_run_id": str(request.run_id),
                    "last_task_id": None if request.task_id is None else str(request.task_id),
                }
            },
            set_started_at=True,
        )

    def mark_retryable(
        self,
        request: LayeredCompositionRequest,
        *,
        reason: str,
        task_result: Mapping[str, Any],
    ) -> LayeredCompositionRequest:
        retry_payload = {"reason": reason, "retryable": True, **dict(task_result)}
        return self._apply_transition(
            request,
            run_status=RunStatus.RUNNING.value,
            task_status=TaskStatus.RETRYING.value,
            reel_status="editing",
            run_output_payload=retry_payload,
            task_result=retry_payload,
            metadata_patch={
                LAYERED_COMPOSITION_METADATA_KEY: {
                    "status": "retrying",
                    "last_error": reason,
                    "last_run_id": str(request.run_id),
                    "last_task_id": None if request.task_id is None else str(request.task_id),
                }
            },
        )

    def mark_failed(
        self,
        request: LayeredCompositionRequest,
        *,
        reason: str,
        task_result: Mapping[str, Any],
    ) -> LayeredCompositionRequest:
        failed_payload = {"reason": reason, "retryable": False, **dict(task_result)}
        return self._apply_transition(
            request,
            run_status=RunStatus.FAILED.value,
            task_status=TaskStatus.FAILED.value,
            reel_status="qa_failed",
            run_output_payload=failed_payload,
            task_result=failed_payload,
            metadata_patch={
                LAYERED_COMPOSITION_METADATA_KEY: {
                    "status": "failed",
                    "last_error": reason,
                    "last_run_id": str(request.run_id),
                    "last_task_id": None if request.task_id is None else str(request.task_id),
                }
            },
            set_finished_at=True,
        )

    def mark_ready(
        self,
        request: LayeredCompositionRequest,
        *,
        package_payload: Mapping[str, Any],
        render_asset: RenderAssetRecord,
        asset_usages: Sequence[AssetUsageSpec],
        task_result: Mapping[str, Any],
    ) -> LayeredCompositionRequest:
        render_asset_payload = render_asset.as_payload()
        ready_payload = {
            **dict(task_result),
            "package": dict(package_payload),
            "render_asset": render_asset_payload,
        }
        with self._session_factory.begin() as session:
            self._update_run(
                session,
                request=request,
                status=RunStatus.SUCCEEDED.value,
                output_payload=ready_payload,
                metadata_patch={
                    LAYERED_COMPOSITION_METADATA_KEY: {
                        "status": "ready",
                        "last_run_id": str(request.run_id),
                        "last_task_id": None if request.task_id is None else str(request.task_id),
                        "render_asset_id": str(render_asset.asset_id),
                    }
                },
                set_finished_at=True,
            )
            if request.task_id is not None:
                self._update_task(
                    session,
                    request=request,
                    status=TaskStatus.SUCCEEDED.value,
                    result=ready_payload,
                )
            self._update_reel(
                session,
                request=request,
                status="ready",
                metadata_patch={
                    "package": dict(package_payload),
                    "package_artifact_uris": _package_artifact_uris(package_payload),
                    "render_asset": render_asset_payload,
                    LAYERED_COMPOSITION_METADATA_KEY: {
                        "status": "ready",
                        "last_run_id": str(request.run_id),
                        "last_task_id": None if request.task_id is None else str(request.task_id),
                        "render_asset_id": str(render_asset.asset_id),
                    },
                },
            )
            session.execute(
                _UPSERT_RENDER_ASSET_STMT,
                {
                    "id": render_asset.asset_id,
                    "org_id": request.org_id,
                    "asset_class": FINAL_RENDER_ASSET_CLASS,
                    "storage_uri": render_asset.storage_uri,
                    "metadata": {
                        "reel_id": str(request.reel_id),
                        "run_id": str(request.run_id),
                        "package_root_uri": package_payload.get("package_root_uri"),
                        "package": {
                            "manifest_uri": package_payload.get("manifest_uri"),
                            "artifact_uris": _package_artifact_uris(package_payload),
                        },
                    },
                    "source": FINAL_RENDER_SOURCE,
                    "asset_key": _asset_key(
                        request=request,
                        asset_class=FINAL_RENDER_ASSET_CLASS,
                    ),
                    "asset_key_hash": _asset_key_hash(
                        request=request,
                        asset_class=FINAL_RENDER_ASSET_CLASS,
                    ),
                    "content_hash": render_asset.content_hash,
                    "status": "ready",
                },
            )
            for usage in asset_usages:
                session.execute(
                    _UPSERT_ASSET_USAGE_STMT,
                    {
                        "id": uuid.uuid4(),
                        "org_id": request.org_id,
                        "reel_id": request.reel_id,
                        "asset_id": usage.asset_id,
                        "usage_role": usage.usage_role,
                        "sort_order": usage.sort_order,
                        "component_role": usage.component_role,
                        "layer_role": usage.layer_role,
                        "sequence_index": usage.sequence_index,
                        "z_index": usage.z_index,
                        "start_time": usage.start_time,
                        "end_time": usage.end_time,
                        "transform_recipe": usage.transform_recipe,
                        "transform_version": usage.transform_version,
                        "metadata_json": dict(usage.metadata_json),
                    },
                )
        return self.load_request(run_id=request.run_id, task_id=request.task_id)

    def _apply_transition(
        self,
        request: LayeredCompositionRequest,
        *,
        run_status: str,
        task_status: str,
        reel_status: str,
        run_output_payload: Mapping[str, Any] | None,
        task_result: Mapping[str, Any],
        metadata_patch: Mapping[str, Any],
        set_started_at: bool = False,
        set_finished_at: bool = False,
    ) -> LayeredCompositionRequest:
        with self._session_factory.begin() as session:
            self._update_run(
                session,
                request=request,
                status=run_status,
                output_payload=run_output_payload,
                metadata_patch=metadata_patch,
                set_started_at=set_started_at,
                set_finished_at=set_finished_at,
            )
            if request.task_id is not None:
                self._update_task(
                    session,
                    request=request,
                    status=task_status,
                    result=task_result,
                )
            self._update_reel(
                session,
                request=request,
                status=reel_status,
                metadata_patch=metadata_patch,
            )
        return self.load_request(run_id=request.run_id, task_id=request.task_id)

    def _update_run(
        self,
        session: Session,
        *,
        request: LayeredCompositionRequest,
        status: str,
        output_payload: Mapping[str, Any] | None,
        metadata_patch: Mapping[str, Any],
        set_started_at: bool = False,
        set_finished_at: bool = False,
    ) -> None:
        session.execute(
            _UPDATE_RUN_STMT,
            {
                "run_id": request.run_id,
                "status": status,
                "output_payload": None if output_payload is None else dict(output_payload),
                "run_metadata": _merge_dicts(request.run_metadata, metadata_patch),
                "set_started_at": set_started_at,
                "set_finished_at": set_finished_at,
            },
        )

    @staticmethod
    def _update_task(
        session: Session,
        *,
        request: LayeredCompositionRequest,
        status: str,
        result: Mapping[str, Any],
    ) -> None:
        if request.task_id is None:
            return
        session.execute(
            _UPDATE_TASK_STMT,
            {
                "task_id": request.task_id,
                "status": status,
                "result": dict(result),
            },
        )

    @staticmethod
    def _update_reel(
        session: Session,
        *,
        request: LayeredCompositionRequest,
        status: str,
        metadata_patch: Mapping[str, Any],
    ) -> None:
        session.execute(
            _UPDATE_REEL_STMT,
            {
                "reel_id": request.reel_id,
                "status": status,
                "metadata": _merge_dicts(request.reel_metadata, metadata_patch),
            },
        )

    @staticmethod
    def _load_task_row(
        session: Session,
        *,
        org_id: uuid.UUID,
        run_id: uuid.UUID,
        task_id: uuid.UUID | None,
    ) -> RowMapping | None:
        if task_id is not None:
            return (
                session.execute(
                    text(
                        """
                        SELECT id, task_type, status, payload, result
                        FROM tasks
                        WHERE org_id = :org_id AND run_id = :run_id AND id = :task_id
                        """
                    ),
                    {"org_id": org_id, "run_id": run_id, "task_id": task_id},
                )
                .mappings()
                .one_or_none()
            )
        return (
            session.execute(
                text(
                    """
                    SELECT id, task_type, status, payload, result
                    FROM tasks
                    WHERE org_id = :org_id AND run_id = :run_id
                    ORDER BY CASE
                        WHEN task_type = :layered_task_type THEN 0
                        WHEN task_type = :process_reel_task_type THEN 1
                        ELSE 2
                    END,
                    created_at,
                    id
                    LIMIT 1
                    """
                ),
                {
                    "org_id": org_id,
                    "run_id": run_id,
                    "layered_task_type": LAYERED_COMPOSITION_TASK_TYPE,
                    "process_reel_task_type": _WORKFLOW_PROCESS_REEL,
                },
            )
            .mappings()
            .one_or_none()
        )


def process_layered_composition(
    *,
    run_id: uuid.UUID | str,
    task_id: uuid.UUID | str | None = None,
    manifest_uri: str | None = None,
    manifest_payload: Mapping[str, Any] | None = None,
    store: LayeredCompositionStore | None = None,
    storage_client: LayeredCompositionStorageClient | None = None,
    renderer: LayeredCompositionRenderer | None = None,
    cover_extractor: CoverExtractor | None = None,
    settings: Settings | None = None,
    timeout_seconds: float = _DEFAULT_RENDER_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Render a layered composition manifest and persist visible run/task state."""

    resolved_settings = settings or Settings()
    resolved_store = store or SQLLayeredCompositionStore(settings=resolved_settings)
    resolved_storage = storage_client or _build_storage_client(resolved_settings)
    resolved_renderer = renderer or compose_layered_reel
    resolved_cover_extractor = cover_extractor or extract_cover_frame
    request = resolved_store.load_request(run_id=run_id, task_id=task_id)

    if request.is_ready and request.run_output_payload is not None:
        return dict(request.run_output_payload)

    try:
        raw_manifest = _resolve_manifest_payload(
            request=request,
            explicit_payload=manifest_payload,
            manifest_uri=manifest_uri,
            storage_client=resolved_storage,
        )
        manifest = CompositionManifest.model_validate(raw_manifest)
    except (ValidationError, ValueError, TypeError, KeyError) as exc:
        failure = _failure_payload(
            request,
            phase="manifest_validation",
            error=exc,
            retryable=False,
        )
        resolved_store.mark_failed(request, reason=str(exc), task_result=failure)
        raise TerminalCompositionActorError(str(exc)) from exc
    except Exception as exc:
        failure = _failure_payload(
            request,
            phase="manifest_load",
            error=exc,
            retryable=True,
        )
        resolved_store.mark_retryable(request, reason=str(exc), task_result=failure)
        raise RetryableCompositionActorError(str(exc)) from exc

    request = resolved_store.mark_running(
        request,
        task_result={
            "run_id": str(request.run_id),
            "task_id": None if request.task_id is None else str(request.task_id),
            "reel_id": str(request.reel_id),
            "phase": "rendering_started",
            "status": "running",
        },
    )

    try:
        asset_sources = resolved_store.load_asset_sources(request, asset_ids=manifest.asset_ids)
        ensure_composition_preflight(
            manifest,
            asset_sources=asset_sources,
            storage_client=cast(StorageObjectProbe, resolved_storage),
            require_content_hash=False,
        )
    except CompositionPreflightError as exc:
        failure = _failure_payload(
            request,
            phase="preflight",
            error=exc,
            retryable=False,
            details={
                "issues": [
                    {
                        "code": issue.code,
                        "message": issue.message,
                        "asset_id": issue.asset_id,
                        "layer_id": issue.layer_id,
                    }
                    for issue in exc.issues
                ]
            },
        )
        resolved_store.mark_failed(request, reason=str(exc), task_result=failure)
        raise TerminalCompositionActorError(str(exc)) from exc
    except Exception as exc:
        failure = _failure_payload(request, phase="preflight", error=exc, retryable=True)
        resolved_store.mark_retryable(request, reason=str(exc), task_result=failure)
        raise RetryableCompositionActorError(str(exc)) from exc

    try:
        package_payload, render_asset = _render_store_and_package(
            request=request,
            manifest=manifest,
            asset_sources=asset_sources,
            storage_client=resolved_storage,
            renderer=resolved_renderer,
            cover_extractor=resolved_cover_extractor,
            layout=CanonicalStorageLayout(bucket=resolved_settings.minio_bucket),
            timeout_seconds=timeout_seconds,
        )
    except (FFmpegError, OSError, RuntimeError, TypeError, ValueError) as exc:
        failure = _failure_payload(request, phase="render", error=exc, retryable=True)
        resolved_store.mark_retryable(request, reason=str(exc), task_result=failure)
        raise RetryableCompositionActorError(str(exc)) from exc

    asset_usages = _asset_usage_specs(
        request=request,
        manifest=manifest,
        render_asset=render_asset,
    )
    summary = {
        "run_id": str(request.run_id),
        "task_id": None if request.task_id is None else str(request.task_id),
        "org_id": str(request.org_id),
        "reel_id": str(request.reel_id),
        "phase": "ready",
        "status": "ready",
        "package_root_uri": package_payload["package_root_uri"],
        "manifest_uri": package_payload["manifest_uri"],
        "render_asset_id": str(render_asset.asset_id),
        "final_video_uri": render_asset.storage_uri,
    }
    resolved_store.mark_ready(
        request,
        package_payload=package_payload,
        render_asset=render_asset,
        asset_usages=asset_usages,
        task_result=summary,
    )
    return {
        **summary,
        "package": package_payload,
        "render_asset": render_asset.as_payload(),
    }


def _render_store_and_package(
    *,
    request: LayeredCompositionRequest,
    manifest: CompositionManifest,
    asset_sources: Mapping[str, SourceAssetInput],
    storage_client: LayeredCompositionStorageClient,
    renderer: LayeredCompositionRenderer,
    cover_extractor: CoverExtractor,
    layout: CanonicalStorageLayout,
    timeout_seconds: float,
) -> tuple[dict[str, Any], RenderAssetRecord]:
    package_refs = layout.reel_package(request.reel_id)
    render_asset_id = _render_asset_id(request)
    with tempfile.TemporaryDirectory(prefix="content-lab-layered-composition-") as tmp_dir:
        work_dir = Path(tmp_dir)
        render_result = renderer(
            manifest,
            asset_sources=asset_sources,
            output_path=work_dir / "final_video.mp4",
            storage_client=storage_client,
            staging_dir=work_dir / "source-assets",
            timeout_seconds=timeout_seconds,
        )
        final_video_bytes = render_result.output_path.read_bytes()
        final_video_checksum = checksum_bytes(final_video_bytes).content_hash
        final_video_object = storage_client.put_object(
            ref=package_refs.final_video,
            data=final_video_bytes,
            content_type="video/mp4",
            metadata=_artifact_metadata(request, "final_video"),
            checksum_sha256=final_video_checksum,
        )

        cover_artifact = cover_extractor(
            video_path=render_result.output_path,
            output_path=work_dir / "cover.png",
            duration_seconds=manifest.duration,
        )
        cover_bytes = cover_artifact.image_path.read_bytes()
        cover_checksum = checksum_bytes(cover_bytes).content_hash
        cover_object = storage_client.put_object(
            ref=package_refs.cover,
            data=cover_bytes,
            content_type="image/png",
            metadata=_artifact_metadata(request, "cover"),
            checksum_sha256=cover_checksum,
        )

        composition_manifest_body = _json_bytes(manifest.model_dump(mode="json"))
        composition_manifest_checksum = checksum_bytes(composition_manifest_body).content_hash
        composition_manifest_object = storage_client.put_object(
            ref=package_refs.composition_manifest,
            data=composition_manifest_body,
            content_type="application/json",
            metadata=_artifact_metadata(request, "composition_manifest"),
            checksum_sha256=composition_manifest_checksum,
        )

        render_trace = _render_trace_payload(
            manifest=manifest,
            render_result=render_result,
            cover_artifact=cover_artifact,
        )
        package_manifest = _package_manifest_payload(
            artifacts=[
                _artifact_payload(
                    name="final_video",
                    filename="final_video.mp4",
                    kind="video",
                    stored=final_video_object,
                    checksum_sha256=final_video_checksum,
                ),
                _artifact_payload(
                    name="cover",
                    filename="cover.png",
                    kind="image",
                    stored=cover_object,
                    checksum_sha256=cover_checksum,
                ),
                _artifact_payload(
                    name="composition_manifest",
                    filename="composition_manifest.json",
                    kind="json",
                    stored=composition_manifest_object,
                    checksum_sha256=composition_manifest_checksum,
                ),
            ],
        )
        package_manifest_body = _json_bytes(package_manifest)
        package_manifest_checksum = checksum_bytes(package_manifest_body).content_hash
        package_manifest_object = storage_client.put_object(
            ref=package_refs.manifest,
            data=package_manifest_body,
            content_type="application/json",
            metadata=_artifact_metadata(request, "package_manifest"),
            checksum_sha256=package_manifest_checksum,
        )

    render_asset = RenderAssetRecord(
        asset_id=render_asset_id,
        storage_uri=final_video_object.ref.uri,
        content_hash=final_video_checksum,
        size_bytes=final_video_object.size_bytes,
        content_type=final_video_object.content_type or "video/mp4",
    )
    package_payload = {
        "package_root_uri": package_refs.root.uri,
        "manifest_uri": package_manifest_object.ref.uri,
        "ready_for_publish": True,
        "manifest": package_manifest,
        "composition_manifest_uri": composition_manifest_object.ref.uri,
        "composition_manifest": manifest.model_dump(mode="json"),
        "render_trace": render_trace,
        "provenance": _provenance_payload(
            request=request,
            manifest=manifest,
            asset_sources=asset_sources,
            render_asset=render_asset,
        ),
        "artifacts": [
            *package_manifest["artifacts"],
            _artifact_payload(
                name="package_manifest",
                filename="package_manifest.json",
                kind="json",
                stored=package_manifest_object,
                checksum_sha256=package_manifest_checksum,
            ),
        ],
    }
    return package_payload, render_asset


def _resolve_manifest_payload(
    *,
    request: LayeredCompositionRequest,
    explicit_payload: Mapping[str, Any] | None,
    manifest_uri: str | None,
    storage_client: LayeredCompositionStorageClient,
) -> Mapping[str, Any]:
    if explicit_payload is not None:
        return dict(explicit_payload)
    if manifest_uri is not None:
        return _load_manifest_payload_from_uri(manifest_uri, storage_client=storage_client)

    for candidate in (
        request.run_input_params.get("layered_composition_manifest"),
        request.run_input_params.get("composition_manifest"),
        request.task_payload.get("layered_composition_manifest"),
        request.task_payload.get("composition_manifest"),
        request.reel_metadata.get("layered_composition_manifest"),
        request.reel_metadata.get("composition_manifest"),
    ):
        payload = _nested_manifest_payload(candidate)
        if payload is not None:
            return payload

    raise ValueError(
        "No layered composition manifest was provided. Expected "
        "layered_composition_manifest or composition_manifest in run/task/reel metadata."
    )


def _load_manifest_payload_from_uri(
    manifest_uri: str,
    *,
    storage_client: LayeredCompositionStorageClient,
) -> Mapping[str, Any]:
    normalized = manifest_uri.strip()
    if not normalized:
        raise ValueError("manifest_uri must not be blank")
    if normalized.startswith("s3://"):
        downloaded = storage_client.get_object(storage_uri=normalized)
        body = getattr(downloaded, "body", None)
        if not isinstance(body, bytes):
            raise TypeError("storage_client.get_object must return an object with bytes body")
        decoded = json.loads(body.decode("utf-8"))
    else:
        decoded = json.loads(Path(normalized).read_text(encoding="utf-8"))
    if not isinstance(decoded, Mapping):
        raise ValueError("composition manifest URI must resolve to a JSON object")
    return dict(decoded)


def _nested_manifest_payload(candidate: Any) -> Mapping[str, Any] | None:
    if not isinstance(candidate, Mapping):
        return None
    if "background_layer" in candidate:
        return dict(candidate)
    nested = candidate.get("layered_composition_manifest") or candidate.get("composition_manifest")
    if isinstance(nested, Mapping) and "background_layer" in nested:
        return dict(nested)
    return None


def _package_manifest_payload(*, artifacts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "version": 1,
        "artifact_count": len(artifacts),
        "complete": True,
        "artifacts": [dict(artifact) for artifact in artifacts],
    }


def _artifact_payload(
    *,
    name: str,
    filename: str,
    kind: str,
    stored: StoredObject,
    checksum_sha256: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "filename": filename,
        "storage_uri": stored.ref.uri,
        "kind": kind,
        "content_type": stored.content_type,
        "checksum_sha256": stored.checksum_sha256 or checksum_sha256,
    }
    if stored.size_bytes is not None:
        payload["size_bytes"] = stored.size_bytes
    if stored.metadata:
        payload["metadata"] = dict(stored.metadata)
    return payload


def _render_trace_payload(
    *,
    manifest: CompositionManifest,
    render_result: LayeredCompositionResult,
    cover_artifact: CoverFrameArtifact,
) -> dict[str, Any]:
    return {
        "schema_version": "layered_composition_render_trace.v1",
        "canvas_width": manifest.canvas_width,
        "canvas_height": manifest.canvas_height,
        "duration_seconds": manifest.duration,
        "fps": manifest.fps,
        "layer_count": 1 + len(manifest.layers) + len(manifest.audio_layers),
        "command": list(render_result.command),
        "filter_complex": render_result.filter_complex,
        "harmonisation_trace": list(render_result.harmonisation_trace),
        "cover_timestamp_seconds": cover_artifact.timestamp_seconds,
        "ffmpeg": {
            "returncode": render_result.ffmpeg_result.returncode,
            "duration_seconds": render_result.ffmpeg_result.duration_seconds,
            "stderr": render_result.ffmpeg_result.stderr,
        },
    }


def _provenance_payload(
    *,
    request: LayeredCompositionRequest,
    manifest: CompositionManifest,
    asset_sources: Mapping[str, SourceAssetInput],
    render_asset: RenderAssetRecord,
) -> dict[str, Any]:
    assets: list[dict[str, Any]] = []
    for index, layer in enumerate(_manifest_layers(manifest)):
        source = asset_sources.get(layer.asset_id)
        source_ref = None if source is None else coerce_source_asset_reference(source)
        assets.append(
            {
                "asset_id": layer.asset_id,
                "asset_kind": layer.asset_kind,
                "media_type": layer.media_type,
                "layer_id": layer.layer_id,
                "component_role": layer.asset_kind,
                "layer_role": _layer_role(manifest, layer),
                "sequence_index": index,
                "z_index": layer.z_index,
                "start_time": layer.start_time,
                "end_time": layer.end_time,
                "storage_uri": None if source_ref is None else str(source_ref.source),
                "stored_content_hash": None if source_ref is None else source_ref.content_hash,
            }
        )
    return {
        "renderer_version": "layered_ffmpeg_v1",
        "source_run_id": str(request.run_id),
        "reel_id": str(request.reel_id),
        "asset_ids": sorted({layer.asset_id for layer in _manifest_layers(manifest)}),
        "assets": assets,
        "render_asset": render_asset.as_payload(),
    }


def _asset_usage_specs(
    *,
    request: LayeredCompositionRequest,
    manifest: CompositionManifest,
    render_asset: RenderAssetRecord,
) -> list[AssetUsageSpec]:
    usages: list[AssetUsageSpec] = []
    for index, layer in enumerate(_manifest_layers(manifest)):
        try:
            asset_id = _parse_uuid(layer.asset_id, field_name="asset_id")
        except ValueError:
            continue
        usages.append(
            AssetUsageSpec(
                asset_id=asset_id,
                usage_role=_usage_role(manifest, layer),
                sort_order=index,
                component_role=layer.asset_kind,
                layer_role=_layer_role(manifest, layer),
                sequence_index=index,
                z_index=layer.z_index,
                start_time=layer.start_time,
                end_time=layer.end_time,
                transform_recipe=None
                if layer.motion_transform is None
                else layer.motion_transform.model_dump(mode="json"),
                transform_version="motion_transform.v1"
                if layer.motion_transform is not None
                else None,
                metadata_json={
                    "layer_id": layer.layer_id,
                    "media_type": layer.media_type,
                    "render_run_id": str(request.run_id),
                },
            )
        )
    usages.append(
        AssetUsageSpec(
            asset_id=render_asset.asset_id,
            usage_role="final_render",
            component_role=FINAL_RENDER_ASSET_CLASS,
            layer_role="final_render",
            metadata_json={
                "render_run_id": str(request.run_id),
                "storage_uri": render_asset.storage_uri,
            },
        )
    )
    return usages


def _manifest_layers(manifest: CompositionManifest) -> tuple[CompositionLayer, ...]:
    return (manifest.background_layer, *manifest.layers, *manifest.audio_layers)


def _usage_role(manifest: CompositionManifest, layer: CompositionLayer) -> str:
    if layer == manifest.background_layer:
        return "background"
    if layer.media_type == "audio":
        return "audio"
    return str(layer.asset_kind)[:64]


def _layer_role(manifest: CompositionManifest, layer: CompositionLayer) -> str:
    if layer == manifest.background_layer:
        return "background"
    if layer.media_type == "audio":
        return "audio"
    return "visual"


def _failure_payload(
    request: LayeredCompositionRequest,
    *,
    phase: str,
    error: BaseException,
    retryable: bool,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "run_id": str(request.run_id),
        "task_id": None if request.task_id is None else str(request.task_id),
        "org_id": str(request.org_id),
        "reel_id": str(request.reel_id),
        "phase": phase,
        "status": "retrying" if retryable else "failed",
        "retryable": retryable,
        "error": str(error),
        "error_type": type(error).__name__,
    }
    if details:
        payload["details"] = dict(details)
    return payload


def _artifact_metadata(request: LayeredCompositionRequest, artifact_name: str) -> dict[str, str]:
    return {
        "artifact-name": artifact_name,
        "org-id": str(request.org_id),
        "reel-id": str(request.reel_id),
        "run-id": str(request.run_id),
    }


def _render_asset_id(request: LayeredCompositionRequest) -> uuid.UUID:
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"content-lab:layered-render:{request.org_id}:{request.run_id}:{request.reel_id}",
    )


def _asset_key(*, request: LayeredCompositionRequest, asset_class: str) -> str:
    return json.dumps(
        {
            "asset_class": asset_class,
            "org_id": str(request.org_id),
            "reel_id": str(request.reel_id),
            "run_id": str(request.run_id),
            "source": FINAL_RENDER_SOURCE,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _asset_key_hash(*, request: LayeredCompositionRequest, asset_class: str) -> str:
    return hashlib.sha256(
        _asset_key(request=request, asset_class=asset_class).encode("utf-8")
    ).hexdigest()


def _package_artifact_uris(package_payload: Mapping[str, Any]) -> dict[str, str]:
    artifacts = package_payload.get("artifacts")
    if not isinstance(artifacts, list):
        return {}
    artifact_uris: dict[str, str] = {}
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            continue
        name = artifact.get("name")
        storage_uri = artifact.get("storage_uri")
        if name is not None and storage_uri is not None:
            artifact_uris[str(name)] = str(storage_uri)
    return artifact_uris


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _build_storage_client(settings: Settings) -> S3StorageClient:
    return S3StorageClient(
        S3StorageConfig(
            endpoint=settings.minio_endpoint,
            access_key_id=settings.minio_root_user,
            secret_access_key=settings.minio_root_password.get_secret_value(),
            default_bucket=settings.minio_bucket,
        )
    )


def _asset_media_type(metadata: Mapping[str, Any]) -> str | None:
    for value in (
        metadata.get("media_type"),
        metadata.get("content_type"),
        _mapping(metadata.get("storage")).get("content_type"),
    ):
        normalized = _optional_text(value)
        if normalized is not None:
            return normalized
    return None


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _optional_mapping(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return _mapping(value)


def _required_text(value: Any, *, field_name: str) -> str:
    text_value = _optional_text(value)
    if text_value is None:
        raise ValueError(f"{field_name} must not be blank")
    return text_value


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


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


def _merge_dicts(
    left: Mapping[str, Any] | None,
    right: Mapping[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(left or {})
    if right is not None:
        for key, value in right.items():
            if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
                merged[key] = _merge_dicts(cast(Mapping[str, Any], merged[key]), value)
            else:
                merged[key] = value
    return merged


@dramatiq.actor(queue_name=QUEUE_NAME, max_retries=_DEFAULT_MAX_RETRIES)
def render_layered_composition(
    run_id: str,
    task_id: str | None = None,
    manifest_uri: str | None = None,
) -> dict[str, Any]:
    """Render a persisted layered composition request."""

    logger.info("rendering layered composition run_id=%s task_id=%s", run_id, task_id)
    return process_layered_composition(
        run_id=run_id,
        task_id=task_id,
        manifest_uri=manifest_uri,
    )


ACTORS: tuple[ActorLike, ...] = (render_layered_composition,)

__all__ = [
    "ACTORS",
    "FINAL_RENDER_ASSET_CLASS",
    "FINAL_RENDER_SOURCE",
    "LAYERED_COMPOSITION_METADATA_KEY",
    "LAYERED_COMPOSITION_TASK_TYPE",
    "LayeredCompositionRequest",
    "LayeredCompositionStore",
    "QUEUE_NAME",
    "RenderAssetRecord",
    "RetryableCompositionActorError",
    "SQLLayeredCompositionStore",
    "TerminalCompositionActorError",
    "logger",
    "process_layered_composition",
    "render_layered_composition",
]
