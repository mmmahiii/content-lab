"""Prefect orchestration for turning reusable asset packs into reel candidates."""

# mypy: disable-error-code="no-any-return,untyped-decorator"

from __future__ import annotations

import uuid
from argparse import Namespace
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol, cast

from content_lab_assets.combinator import CandidateComposition, PackAsset
from fastapi import Request
from fastapi.encoders import jsonable_encoder
from prefect.flows import flow
from prefect.tasks import task
from sqlalchemy.orm import Session, sessionmaker

from content_lab_api.db import SessionLocal
from content_lab_api.models import AssetPack, OutboxEvent, Run, Task
from content_lab_api.routes.asset_packs import submit_asset_pack_composition_render
from content_lab_api.schemas.asset_packs import AssetPackCompositionSubmitRequest, AssetPackOut
from content_lab_api.schemas.runs import FlowTrigger
from content_lab_api.services import build_asset_pack_compositions, create_run_row, ensure_task_row
from content_lab_orchestrator.correlation import orchestrator_service_context
from content_lab_runs import RunRowSpec, RunStatus, TaskRowSpec, TaskStatus

from .registry import FlowDefinition

_WORKFLOW_KEY = "asset_pack_to_reels"
_EVENT_TYPE = "asset_pack.reel_candidates.packaged"


class AssetPackToReelsRuntime(Protocol):
    """Persistence boundary for the asset-pack to reels flow."""

    def start_run(self, request_payload: Mapping[str, Any]) -> dict[str, Any]: ...

    def load_pack(self, request_payload: Mapping[str, Any]) -> dict[str, Any]: ...

    def generate_candidate_combinations(
        self,
        request_payload: Mapping[str, Any],
        pack_payload: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def create_composition_manifests(
        self,
        request_payload: Mapping[str, Any],
        candidates_payload: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def render_selected_candidates(
        self,
        request_payload: Mapping[str, Any],
        manifests_payload: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def package_outputs(
        self,
        request_payload: Mapping[str, Any],
        manifests_payload: Mapping[str, Any],
        render_payload: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def emit_notification(self, summary: Mapping[str, Any]) -> dict[str, Any]: ...

    def mark_failed(
        self,
        request_payload: Mapping[str, Any],
        *,
        failed_step: str,
        error_message: str,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class _RequestState:
    actor: str = "orchestrator"
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class _RequestUrl:
    path: str


@dataclass(frozen=True, slots=True)
class _OrchestratorRequest:
    state: _RequestState
    method: str
    url: _RequestUrl


def _request(path: str) -> Request:
    return cast(
        Request,
        _OrchestratorRequest(
            state=_RequestState(request_id=f"orchestrator:{uuid.uuid4()}"),
            method="ORCHESTRATOR",
            url=_RequestUrl(path=path),
        ),
    )


class SQLAssetPackToReelsRuntime:
    """SQL-backed implementation used by real orchestrator runs."""

    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self._session_factory = session_factory or SessionLocal

    def start_run(self, request_payload: Mapping[str, Any]) -> dict[str, Any]:
        org_id = _as_uuid(request_payload["org_id"], field_name="org_id")
        idempotency_key = _optional_text(request_payload.get("idempotency_key")) or (
            f"{_WORKFLOW_KEY}:{request_payload['asset_pack_id']}:"
            f"{request_payload.get('target_reel_count')}"
        )
        with self._session_factory() as session:
            run_id = _optional_text(request_payload.get("run_id"))
            if run_id is not None:
                run = session.get(Run, _as_uuid(run_id, field_name="run_id"))
                if run is None:
                    raise LookupError(f"Run {run_id} was not found")
                run.status = RunStatus.RUNNING.value
            else:
                run = create_run_row(
                    session,
                    spec=RunRowSpec(
                        org_id=org_id,
                        workflow_key=_WORKFLOW_KEY,
                        flow_trigger=FlowTrigger.MANUAL.value,
                        idempotency_key=idempotency_key,
                        status=RunStatus.RUNNING,
                        input_params=dict(request_payload),
                        run_metadata={"orchestrator_flow": _WORKFLOW_KEY},
                    ),
                )
            run.started_at = run.started_at or datetime.now(UTC)
            session.commit()
            session.refresh(run)
            return {"run_id": str(run.id), "workflow_key": run.workflow_key, "status": run.status}

    def load_pack(self, request_payload: Mapping[str, Any]) -> dict[str, Any]:
        with self._step(request_payload, "load_pack") as (session, task_row):
            pack = _load_pack(session, request_payload=request_payload)
            result = AssetPackOut.model_validate(pack).model_dump(mode="json")
            task_row.result = result
            return result

    def generate_candidate_combinations(
        self,
        request_payload: Mapping[str, Any],
        pack_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        _ = pack_payload
        with self._step(request_payload, "generate_candidate_combinations") as (
            session,
            task_row,
        ):
            candidates = build_asset_pack_compositions(
                session,
                org_id=_as_uuid(request_payload["org_id"], field_name="org_id"),
                asset_pack_id=_as_uuid(
                    request_payload["asset_pack_id"],
                    field_name="asset_pack_id",
                ),
                target_reel_count=int(request_payload["target_reel_count"]),
                format_filters=_list_or_none(request_payload.get("format_filters")),
                style_filters=_list_or_none(request_payload.get("style_filters")),
                selection_mode=cast(
                    Literal["balanced", "exploit", "explore", "mutation", "chaos"],
                    request_payload.get("selection_mode") or "balanced",
                ),
            )
            result = {
                "candidate_compositions": [
                    _candidate_payload(candidate) for candidate in candidates
                ],
                "candidate_count": len(candidates),
            }
            task_row.result = {"candidate_count": len(candidates)}
            return result

    def create_composition_manifests(
        self,
        request_payload: Mapping[str, Any],
        candidates_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        asset_pack_id = str(request_payload["asset_pack_id"])
        candidates = _list_of_mappings(candidates_payload.get("candidate_compositions"))
        manifests = [
            _composition_manifest(asset_pack_id=asset_pack_id, candidate=candidate)
            for candidate in candidates
        ]
        result = {"asset_pack_id": asset_pack_id, "composition_manifests": manifests}
        self._record_instant_step(request_payload, "create_composition_manifests", result)
        return result

    def render_selected_candidates(
        self,
        request_payload: Mapping[str, Any],
        manifests_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not bool(request_payload.get("render_selected", False)):
            result = {"rendered": False, "render_submissions": [], "reason": "render_not_requested"}
            self._record_instant_step(request_payload, "render_selected_candidates", result)
            return result
        page_id = _required_text(request_payload.get("page_id"), "page_id")
        render_limit = int(request_payload.get("render_limit") or 1)
        manifests = _list_of_mappings(manifests_payload.get("composition_manifests"))[
            :render_limit
        ]
        submissions: list[dict[str, Any]] = []
        with self._step(request_payload, "render_selected_candidates") as (session, task_row):
            for manifest in manifests:
                submission = submit_asset_pack_composition_render(
                    _as_uuid(request_payload["org_id"], field_name="org_id"),
                    _as_uuid(request_payload["asset_pack_id"], field_name="asset_pack_id"),
                    AssetPackCompositionSubmitRequest(
                        page_id=_as_uuid(page_id, field_name="page_id"),
                        composition_manifest=dict(manifest),
                        render_mode=cast(
                            Literal["preview", "final"],
                            request_payload.get("render_mode") or "preview",
                        ),
                        dry_run=bool(request_payload.get("dry_run", True)),
                        metadata={"submitted_by_flow": _WORKFLOW_KEY},
                    ),
                    _request(
                        f"/orchestrator/asset-packs/{request_payload['asset_pack_id']}"
                        "/composition-renders"
                    ),
                    session,
                )
                submissions.append(submission.model_dump(mode="json"))
            result = {
                "rendered": True,
                "render_submissions": submissions,
                "render_submission_count": len(submissions),
            }
            task_row.result = result
            return result

    def package_outputs(
        self,
        request_payload: Mapping[str, Any],
        manifests_payload: Mapping[str, Any],
        render_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        with self._session_factory() as session:
            run = _load_run(session, request_payload)
            manifests = _list_of_mappings(manifests_payload.get("composition_manifests"))
            summary = {
                "run_id": str(run.id),
                "workflow_key": _WORKFLOW_KEY,
                "run_status": RunStatus.SUCCEEDED.value,
                "asset_pack_id": str(request_payload["asset_pack_id"]),
                "candidate_count": len(manifests),
                "composition_manifests": manifests,
                "render_submissions": list(render_payload.get("render_submissions") or []),
                "rendered": bool(render_payload.get("rendered", False)),
            }
            run.status = RunStatus.SUCCEEDED.value
            run.finished_at = datetime.now(UTC)
            run.output_payload = summary
            session.commit()
            return summary

    def emit_notification(self, summary: Mapping[str, Any]) -> dict[str, Any]:
        with self._session_factory() as session:
            run = session.get(Run, _as_uuid(summary["run_id"], field_name="run_id"))
            if run is None:
                raise LookupError(f"Run {summary['run_id']} was not found")
            event = OutboxEvent(
                org_id=run.org_id,
                aggregate_type="asset_pack",
                aggregate_id=str(summary["asset_pack_id"]),
                event_type=_EVENT_TYPE,
                payload=dict(summary),
            )
            session.add(event)
            session.commit()
            session.refresh(event)
            return {"event_id": str(event.id), "event_type": event.event_type, "emitted": True}

    def mark_failed(
        self,
        request_payload: Mapping[str, Any],
        *,
        failed_step: str,
        error_message: str,
    ) -> dict[str, Any]:
        with self._session_factory() as session:
            run = _load_run(session, request_payload)
            summary = {
                "run_id": str(run.id),
                "workflow_key": _WORKFLOW_KEY,
                "run_status": RunStatus.FAILED.value,
                "failed_step": failed_step,
                "error_message": error_message,
            }
            run.status = RunStatus.FAILED.value
            run.finished_at = datetime.now(UTC)
            run.output_payload = summary
            session.commit()
            return summary

    def _record_instant_step(
        self,
        request_payload: Mapping[str, Any],
        task_type: str,
        result: dict[str, Any],
    ) -> None:
        with self._step(request_payload, task_type) as (_session, task_row):
            task_row.result = result

    def _step(self, request_payload: Mapping[str, Any], task_type: str) -> _TaskStep:
        return _TaskStep(self._session_factory, request_payload=request_payload, task_type=task_type)


class _TaskStep:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        request_payload: Mapping[str, Any],
        task_type: str,
    ) -> None:
        self._session_factory = session_factory
        self._request_payload = request_payload
        self._task_type = task_type
        self._session: Session | None = None
        self._task: Task | None = None

    def __enter__(self) -> tuple[Session, Task]:
        session = self._session_factory()
        run = _load_run(session, self._request_payload)
        task_result = ensure_task_row(
            session,
            spec=TaskRowSpec(
                org_id=run.org_id,
                task_type=f"{_WORKFLOW_KEY}.{self._task_type}",
                idempotency_key=f"{_WORKFLOW_KEY}:{run.id}:{self._task_type}",
                status=TaskStatus.RUNNING,
                run_id=run.id,
                payload=dict(self._request_payload),
            ),
        )
        task_row = task_result.record
        task_row.status = TaskStatus.RUNNING.value
        session.commit()
        self._session = session
        self._task = task_row
        return session, task_row

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._session is None or self._task is None:
            return
        if exc is None:
            self._task.status = TaskStatus.SUCCEEDED.value
        else:
            self._task.status = TaskStatus.FAILED.value
            self._task.result = {"error": str(exc)}
        self._session.commit()
        self._session.close()


def build_asset_pack_to_reels_runtime() -> AssetPackToReelsRuntime:
    return SQLAssetPackToReelsRuntime()


@task
def validate_asset_pack_to_reels_request(request_payload: dict[str, Any]) -> dict[str, Any]:
    _as_uuid(request_payload["org_id"], field_name="org_id")
    _as_uuid(request_payload["asset_pack_id"], field_name="asset_pack_id")
    if int(request_payload["target_reel_count"]) <= 0:
        raise ValueError("target_reel_count must be positive")
    if bool(request_payload.get("render_selected", False)):
        _as_uuid(request_payload.get("page_id"), field_name="page_id")
    return jsonable_encoder(request_payload)


@task
def start_asset_pack_to_reels_run(request_payload: dict[str, Any]) -> dict[str, Any]:
    run_payload = build_asset_pack_to_reels_runtime().start_run(request_payload)
    return {**request_payload, **run_payload}


@task
def load_asset_pack_step(request_payload: dict[str, Any]) -> dict[str, Any]:
    return build_asset_pack_to_reels_runtime().load_pack(request_payload)


@task
def generate_candidate_combinations_step(
    request_payload: dict[str, Any],
    pack_payload: dict[str, Any],
) -> dict[str, Any]:
    return build_asset_pack_to_reels_runtime().generate_candidate_combinations(
        request_payload,
        pack_payload,
    )


@task
def create_composition_manifests_step(
    request_payload: dict[str, Any],
    candidates_payload: dict[str, Any],
) -> dict[str, Any]:
    return build_asset_pack_to_reels_runtime().create_composition_manifests(
        request_payload,
        candidates_payload,
    )


@task
def render_selected_candidates_step(
    request_payload: dict[str, Any],
    manifests_payload: dict[str, Any],
) -> dict[str, Any]:
    return build_asset_pack_to_reels_runtime().render_selected_candidates(
        request_payload,
        manifests_payload,
    )


@task
def package_asset_pack_reel_outputs_step(
    request_payload: dict[str, Any],
    manifests_payload: dict[str, Any],
    render_payload: dict[str, Any],
) -> dict[str, Any]:
    return build_asset_pack_to_reels_runtime().package_outputs(
        request_payload,
        manifests_payload,
        render_payload,
    )


@task
def emit_asset_pack_to_reels_notification_step(summary: dict[str, Any]) -> dict[str, Any]:
    return build_asset_pack_to_reels_runtime().emit_notification(summary)


@task
def mark_asset_pack_to_reels_failed_step(
    request_payload: dict[str, Any],
    failed_step: str,
    error_message: str,
) -> dict[str, Any]:
    return build_asset_pack_to_reels_runtime().mark_failed(
        request_payload,
        failed_step=failed_step,
        error_message=error_message,
    )


@flow(name="asset_pack_to_reels")
def asset_pack_to_reels(
    *,
    org_id: str,
    asset_pack_id: str,
    target_reel_count: int = 5,
    format_filters: list[str] | None = None,
    style_filters: list[str] | None = None,
    selection_mode: Literal["balanced", "exploit", "explore", "mutation", "chaos"] = "balanced",
    render_selected: bool = False,
    render_limit: int = 1,
    page_id: str | None = None,
    render_mode: Literal["preview", "final"] = "preview",
    dry_run: bool = True,
    run_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Create reel candidates from one asset pack, with optional process_reel renders."""

    _ = orchestrator_service_context()
    request_payload = validate_asset_pack_to_reels_request(
        {
            "org_id": org_id,
            "asset_pack_id": asset_pack_id,
            "target_reel_count": target_reel_count,
            "format_filters": format_filters,
            "style_filters": style_filters,
            "selection_mode": selection_mode,
            "render_selected": render_selected,
            "render_limit": render_limit,
            "page_id": page_id,
            "render_mode": render_mode,
            "dry_run": dry_run,
            "run_id": run_id,
            "idempotency_key": idempotency_key,
        }
    )
    request_payload = start_asset_pack_to_reels_run(request_payload)
    failed_step = "load_pack"
    try:
        pack_payload = load_asset_pack_step(request_payload)
        failed_step = "generate_candidate_combinations"
        candidates_payload = generate_candidate_combinations_step(request_payload, pack_payload)
        failed_step = "create_composition_manifests"
        manifests_payload = create_composition_manifests_step(
            request_payload,
            candidates_payload,
        )
        failed_step = "render_selected_candidates"
        render_payload = render_selected_candidates_step(request_payload, manifests_payload)
        failed_step = "package_outputs"
        summary = package_asset_pack_reel_outputs_step(
            request_payload,
            manifests_payload,
            render_payload,
        )
        emit_asset_pack_to_reels_notification_step(summary)
        return summary
    except Exception as exc:
        mark_asset_pack_to_reels_failed_step(request_payload, failed_step, str(exc))
        raise


def build_asset_pack_to_reels_kwargs(args: Namespace) -> dict[str, object]:
    """Map CLI args onto the flow signature."""

    return {
        "org_id": args.org_id,
        "asset_pack_id": args.asset_pack_id,
        "target_reel_count": args.target_reel_count,
        "render_selected": args.render_selected,
        "render_limit": args.render_limit,
        "page_id": args.page_id,
        "run_id": args.run_id,
    }


FLOW_DEFINITION = FlowDefinition(
    name="asset_pack_to_reels",
    description="Load an asset pack, create composition manifests, optionally render, and package outputs.",
    entrypoint=asset_pack_to_reels,
    build_kwargs=build_asset_pack_to_reels_kwargs,
)


def _candidate_payload(candidate: CandidateComposition) -> dict[str, Any]:
    return {
        "composition_id": candidate.composition_id,
        "roles": {
            role: _pack_asset_payload(asset) for role, asset in sorted(candidate.roles.items())
        },
        "compatibility_score": candidate.compatibility_score,
        "diversity_score": candidate.diversity_score,
        "performance_score": candidate.performance_score,
        "selection_score": candidate.selection_score,
        "reasons": list(candidate.reasons),
    }


def _pack_asset_payload(asset: PackAsset) -> dict[str, Any]:
    return {
        "asset_id": asset.asset_id,
        "asset_kind": asset.asset_kind.value,
        "pack_role": asset.pack_role,
        "title": asset.title,
        "metadata": dict(asset.metadata),
        "compatibility": asset.compatibility.model_dump(mode="json"),
        "performance_score": asset.performance_score,
        "usage_count": asset.usage_count,
    }


def _composition_manifest(
    *,
    asset_pack_id: str,
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    roles = _mapping(candidate.get("roles"))
    return {
        "schema_version": "asset_composition_manifest.v1",
        "asset_pack_id": asset_pack_id,
        "composition_id": _required_text(candidate.get("composition_id"), "composition_id"),
        "roles": roles,
        "scores": {
            "compatibility": float(candidate.get("compatibility_score") or 0.0),
            "diversity": float(candidate.get("diversity_score") or 0.0),
            "performance": float(candidate.get("performance_score") or 0.0),
            "selection": float(candidate.get("selection_score") or 0.0),
        },
        "reasons": list(candidate.get("reasons") or []),
    }


def _load_run(session: Session, request_payload: Mapping[str, Any]) -> Run:
    run_id = _required_text(request_payload.get("run_id"), "run_id")
    run = session.get(Run, _as_uuid(run_id, field_name="run_id"))
    if run is None:
        raise LookupError(f"Run {run_id} was not found")
    return run


def _load_pack(session: Session, *, request_payload: Mapping[str, Any]) -> AssetPack:
    pack = (
        session.query(AssetPack)
        .filter(
            AssetPack.org_id == _as_uuid(request_payload["org_id"], field_name="org_id"),
            AssetPack.id == _as_uuid(request_payload["asset_pack_id"], field_name="asset_pack_id"),
        )
        .one_or_none()
    )
    if pack is None:
        raise LookupError(f"Asset pack {request_payload['asset_pack_id']} was not found")
    return pack


def _as_uuid(value: Any, *, field_name: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    normalized = _required_text(value, field_name)
    return uuid.UUID(normalized)


def _required_text(value: Any, field_name: str) -> str:
    normalized = _optional_text(value)
    if normalized is None:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list_or_none(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return None


def _list_of_mappings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


__all__ = [
    "AssetPackToReelsRuntime",
    "FLOW_DEFINITION",
    "SQLAssetPackToReelsRuntime",
    "asset_pack_to_reels",
    "build_asset_pack_to_reels_kwargs",
    "build_asset_pack_to_reels_runtime",
]
