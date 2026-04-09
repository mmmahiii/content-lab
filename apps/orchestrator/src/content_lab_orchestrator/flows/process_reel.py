"""Primary phase-1 orchestration flow for processing an individual reel."""

# mypy: disable-error-code="no-any-return,untyped-decorator"

from __future__ import annotations

import json
import tempfile
import uuid
from argparse import Namespace
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from content_lab_assets import GenerateDecision, ReuseExactDecision, resolve_phase1_asset
from content_lab_assets.providers.runway import (
    RUNWAY_GEN45_MAX_DURATION_SECONDS,
    HTTPRunwayClient,
    RunwayClient,
)
from content_lab_creative import (
    DirectorPlanInput,
    PageMetadata,
    PolicyStateDocument,
    PostingPlanFamilyContext,
    PostingPlanPageContext,
    PostingPlanVariantContext,
    build_posting_plan,
    generate_script_output,
    plan_creative_brief,
)
from content_lab_editing import build_ready_to_post_package, render_basic_vertical_edit
from content_lab_outbox import (
    build_process_reel_event_payload,
    process_reel_event_type,
)
from content_lab_storage import CanonicalStorageLayout, S3StorageClient, S3StorageConfig
from prefect.flows import flow
from prefect.tasks import task
from sqlalchemy.orm import Session, sessionmaker

from content_lab_api.db import SessionLocal
from content_lab_api.models import OutboxEvent, Page, ProviderJob, Reel, ReelFamily
from content_lab_api.schemas.pages import parse_page_metadata
from content_lab_api.services import (
    SQLAlchemyPhase1AssetRegistryStore,
    build_process_reel_service,
    ensure_task_row,
    get_provider_job_by_external_ref,
    load_policy_bundle,
    record_provider_job_submission,
)
from content_lab_api.services.process_reel import ProcessReelExecution, ProcessReelQAResult
from content_lab_core.types import Platform
from content_lab_orchestrator.correlation import orchestrator_service_context
from content_lab_qa import (
    RepetitionGateRequest,
    RepetitionHistoryStore,
    RepetitionPolicy,
    evaluate_format_qa,
    evaluate_repetition,
)
from content_lab_runs import TaskRowSpec, TaskStatus
from content_lab_shared.settings import Settings
from content_lab_worker.actors.runway import process_runway_asset

from .registry import FlowDefinition

_DEFAULT_TEMP_ROOT_NAME = "content-lab-process-reel"
_DEFAULT_REEL_DURATION_SECONDS = 12
_PRIMARY_ASSET_CLASS = "clip"
_PRIMARY_ASSET_MODEL = "gen4.5"
_PRIMARY_ASSET_PROVIDER = "runway"
_PRIMARY_ASSET_RATIO = "9:16"
# Orchestrator calls Runway in-process; allow long-running Gen4 jobs (~10 min at 5s cadence).
_RUNWAY_SYNC_MAX_POLLS = 120
_RUNWAY_SYNC_POLL_INTERVAL_SECONDS = 5.0


class ProcessReelExecutionLike(Protocol):
    """Minimal execution payload contract used inside the orchestrator app."""

    def to_payload(self) -> dict[str, Any]: ...


class ProcessReelRuntime(Protocol):
    """Typed runtime boundary for the API-backed process-reel service."""

    def start_execution(
        self,
        *,
        reel_id: str,
        dry_run: bool = False,
        run_id: str | None = None,
    ) -> ProcessReelExecutionLike: ...

    def run_creative_planning(
        self, execution: ProcessReelExecutionLike
    ) -> ProcessReelExecutionLike: ...

    def run_asset_resolution(
        self, execution: ProcessReelExecutionLike
    ) -> ProcessReelExecutionLike: ...

    def run_editing(self, execution: ProcessReelExecutionLike) -> ProcessReelExecutionLike: ...

    def run_qa(self, execution: ProcessReelExecutionLike) -> ProcessReelExecutionLike: ...

    def run_packaging(self, execution: ProcessReelExecutionLike) -> ProcessReelExecutionLike: ...

    def mark_ready(self, execution: ProcessReelExecutionLike) -> dict[str, Any]: ...

    def mark_qa_failed(self, execution: ProcessReelExecutionLike) -> dict[str, Any]: ...

    def mark_failed(
        self,
        execution: ProcessReelExecutionLike,
        *,
        failed_step: str,
        error_message: str,
    ) -> dict[str, Any]: ...


class ProcessReelEventSink(Protocol):
    """Persistence boundary for terminal process-reel outbox events."""

    def emit_terminal_event(self, summary: Mapping[str, Any]) -> dict[str, Any]: ...


class ProcessReelPlanningContextLoader(Protocol):
    """Load the page/family context needed to plan a reel."""

    def load(self, execution: ProcessReelExecution) -> PhaseOnePlanningContext: ...


class ProcessReelAssetResolver(Protocol):
    """Resolve or generate the primary source asset for a reel."""

    def resolve_primary_asset(
        self,
        execution: ProcessReelExecution,
        *,
        creative_output: Mapping[str, Any],
    ) -> dict[str, Any]: ...


class RetrievedObjectLike(Protocol):
    """Minimal retrieved-object shape needed by the editor."""

    body: bytes
    content_type: str | None


class ProcessReelStorageClient(Protocol):
    """Shared storage client boundary used for editing and packaging."""

    def get_object(self, *, storage_uri: str) -> RetrievedObjectLike: ...

    def put_object(
        self,
        *,
        data: bytes,
        key: str,
        content_type: str | None = None,
        checksum_sha256: str | None = None,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class PhaseOnePlanningContext:
    """Reel, family, and page context used by the phase-1 planner."""

    page_name: str
    page_metadata: PageMetadata
    family_name: str
    family_mode: str
    variant_label: str
    brief_index: int
    target_platforms: tuple[Platform, ...]
    timezone: str
    locale: str
    policy: PolicyStateDocument
    duration_seconds: int = _DEFAULT_REEL_DURATION_SECONDS


class SQLProcessReelPlanningContextLoader:
    """Load page, family, and policy context directly from the API schema."""

    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self._session_factory = session_factory or SessionLocal

    def load(self, execution: ProcessReelExecution) -> PhaseOnePlanningContext:
        reel_uuid = _as_uuid(execution.reel_id, field_name="reel_id")
        with self._session_factory() as session:
            reel = session.get(Reel, reel_uuid)
            if reel is None:
                raise LookupError(f"Reel {execution.reel_id} was not found")
            family = session.get(ReelFamily, reel.reel_family_id)
            if family is None:
                raise LookupError(f"Reel family {reel.reel_family_id} was not found")
            page = session.get(Page, family.page_id)
            if page is None:
                raise LookupError(f"Page {family.page_id} was not found")

            bundle = load_policy_bundle(
                session,
                org_id=reel.org_id,
                page_id=page.id,
            )
            effective_policy = PolicyStateDocument.model_validate(
                bundle.effective_policy.model_dump(mode="json")
            )
            family_mode = _optional_text(family.metadata_.get("mode")) or "explore"
            policy = _policy_with_family_mode(effective_policy, family_mode=family_mode)
            page_metadata = parse_page_metadata(cast(dict[str, Any], page.metadata_ or {}))

            return PhaseOnePlanningContext(
                page_name=page.display_name,
                page_metadata=page_metadata,
                family_name=family.name,
                family_mode=family_mode,
                variant_label=_optional_text(reel.variant_label) or "A",
                brief_index=_variant_brief_index(reel.variant_label),
                target_platforms=(_coerce_platform(page.platform),),
                timezone=_optional_text(cast(dict[str, Any], page.metadata_ or {}).get("timezone"))
                or "UTC",
                locale=_optional_text(cast(dict[str, Any], page.metadata_ or {}).get("locale"))
                or "en",
                policy=policy,
                duration_seconds=_coerce_positive_int(
                    cast(dict[str, Any], reel.metadata_ or {}).get("duration_seconds"),
                    default=_DEFAULT_REEL_DURATION_SECONDS,
                ),
            )


class SQLProcessReelAssetResolver:
    """Resolve the source clip through the registry and Runway worker path."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        session_factory: sessionmaker[Session] | None = None,
        provider_client: RunwayClient | None = None,
        storage_client: ProcessReelStorageClient | None = None,
        max_polls: int = _RUNWAY_SYNC_MAX_POLLS,
        poll_interval_seconds: float = _RUNWAY_SYNC_POLL_INTERVAL_SECONDS,
    ) -> None:
        self._settings = settings or Settings()
        self._session_factory = session_factory or SessionLocal
        self._provider_client = provider_client or HTTPRunwayClient.from_settings(self._settings)
        self._storage_client = storage_client or _build_storage_client(self._settings)
        self._max_polls = max_polls
        self._poll_interval_seconds = poll_interval_seconds

    def resolve_primary_asset(
        self,
        execution: ProcessReelExecution,
        *,
        creative_output: Mapping[str, Any],
    ) -> dict[str, Any]:
        request_payload = _mapping(creative_output.get("primary_asset_request"))
        if not request_payload:
            raise ValueError("Creative planning did not provide a primary_asset_request payload")

        with self._session_factory() as session:
            store = SQLAlchemyPhase1AssetRegistryStore(session, settings=self._settings)
            decision = resolve_phase1_asset(
                store,
                org_id=_as_uuid(execution.org_id, field_name="org_id"),
                asset_class=_required_text(
                    request_payload.get("asset_class"),
                    field_name="primary_asset_request.asset_class",
                ),
                provider=_required_text(
                    request_payload.get("provider"),
                    field_name="primary_asset_request.provider",
                ),
                model=_required_text(
                    request_payload.get("model"),
                    field_name="primary_asset_request.model",
                ),
                prompt=_required_text(
                    request_payload.get("prompt"),
                    field_name="primary_asset_request.prompt",
                ),
                negative_prompt=_optional_text(request_payload.get("negative_prompt")),
                seed=_optional_int(request_payload.get("seed")),
                duration_seconds=_optional_float(request_payload.get("duration_seconds")),
                fps=_optional_int(request_payload.get("fps")),
                ratio=_optional_text(request_payload.get("ratio")),
                motion=_mapping(request_payload.get("motion")) or None,
                init_image_hash=_optional_text(request_payload.get("init_image_hash")),
                reference_asset_ids=_sequence_of_text(request_payload.get("reference_asset_ids")),
                request_payload=request_payload,
            )
            if isinstance(decision, ReuseExactDecision):
                return {
                    **decision.model_dump(mode="json"),
                    "provider_job": {
                        "provider": decision.provider,
                        "status": "succeeded",
                    },
                    "resolution_source": "asset_registry",
                }

            if not isinstance(decision, GenerateDecision):
                raise ValueError(f"Unsupported asset resolution decision: {decision.decision}")

            task_result = ensure_task_row(
                session,
                spec=TaskRowSpec(
                    org_id=execution.org_id,
                    task_type=decision.generation_intent.task_type,
                    idempotency_key=decision.generation_intent.idempotency_key,
                    status=TaskStatus.QUEUED,
                    run_id=execution.run_id,
                    payload=dict(decision.generation_intent.payload),
                ),
            )
            task = task_result.record
            decision.generation_intent.task_id = task.id
            decision.generation_intent.task_status = task.status
            provider_job = record_provider_job_submission(
                session,
                org_id=execution.org_id,
                task_id=task.id,
                asset_id=decision.generation_intent.asset_id,
                asset_key=decision.generation_intent.asset_key,
                asset_key_hash=decision.generation_intent.asset_key_hash,
                request_payload=decision.generation_intent.payload.get("request"),
                provider_payload=decision.generation_intent.payload["provider_submission"],
                task_status=task.status,
                asset_status=decision.generation_intent.asset_status,
            )
            session.commit()

        generation_summary = process_runway_asset(
            asset_id=decision.generation_intent.asset_id,
            provider_client=self._provider_client,
            storage_client=cast(Any, self._storage_client),
            settings=self._settings,
            max_polls=self._max_polls,
            poll_interval_seconds=self._poll_interval_seconds,
        )

        provider_job_id = str(provider_job.id)
        provider_job_row = self._provider_job(
            provider=decision.provider,
            external_ref=_required_text(
                _mapping(generation_summary.get("provider_job")).get("external_ref"),
                field_name="provider_job.external_ref",
            ),
        )
        if provider_job_row is not None:
            provider_job_id = str(provider_job_row.id)

        return {
            **decision.model_dump(mode="json"),
            "asset_id": str(decision.generation_intent.asset_id),
            "provider_job_id": provider_job_id,
            "provider_job": {
                "provider": decision.provider,
                **_mapping(generation_summary.get("provider_job")),
            },
            "resolution_source": "runway_worker",
            "storage_uri": _required_text(
                generation_summary.get("storage_uri"),
                field_name="generation_summary.storage_uri",
            ),
            "generation": generation_summary,
        }

    def _provider_job(self, *, provider: str, external_ref: str) -> ProviderJob | None:
        with self._session_factory() as session:
            return get_provider_job_by_external_ref(
                session,
                provider=provider,
                external_ref=external_ref,
            )


class SQLProcessReelEventSink:
    """Persist terminal process-reel outbox events idempotently per run/event type."""

    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self._session_factory = session_factory or SessionLocal

    def emit_terminal_event(self, summary: Mapping[str, Any]) -> dict[str, Any]:
        event_type = process_reel_event_type(summary)
        payload = build_process_reel_event_payload(summary)
        aggregate_id = _required_text(payload.get("run_id"), field_name="payload.run_id")
        org_id = _optional_text(payload.get("org_id"))
        if org_id is None:
            raise ValueError("payload.org_id must not be blank")
        try:
            org_uuid = _as_uuid(org_id, field_name="org_id")
        except ValueError:
            return {
                "event_type": event_type,
                "aggregate_id": aggregate_id,
                "emitted": False,
                "reason": "org_id_not_uuid",
            }

        with self._session_factory.begin() as session:
            existing = (
                session.query(OutboxEvent)
                .filter(
                    OutboxEvent.aggregate_type == "run",
                    OutboxEvent.aggregate_id == aggregate_id,
                    OutboxEvent.event_type == event_type,
                )
                .one_or_none()
            )
            if existing is not None:
                return {
                    "event_id": str(existing.id),
                    "event_type": event_type,
                    "aggregate_id": aggregate_id,
                    "emitted": False,
                }

            event = OutboxEvent(
                org_id=org_uuid,
                aggregate_type="run",
                aggregate_id=aggregate_id,
                event_type=event_type,
                payload=payload,
            )
            session.add(event)
            session.flush()
            return {
                "event_id": str(event.id),
                "event_type": event_type,
                "aggregate_id": aggregate_id,
                "emitted": True,
            }


class PhaseOneProcessReelExecutor:
    """Concrete phase-1 executor that keeps orchestration boundaries narrow."""

    def __init__(
        self,
        *,
        planning_context_loader: ProcessReelPlanningContextLoader,
        asset_resolver: ProcessReelAssetResolver,
        storage_client: ProcessReelStorageClient,
        package_layout: CanonicalStorageLayout,
        temp_root: str | Path | None = None,
        repetition_history_store: RepetitionHistoryStore | None = None,
        ffmpeg_bin: str = "ffmpeg",
        ffprobe_bin: str = "ffprobe",
    ) -> None:
        self._planning_context_loader = planning_context_loader
        self._asset_resolver = asset_resolver
        self._storage_client = storage_client
        self._package_layout = package_layout
        self._temp_root = (
            Path(temp_root)
            if temp_root is not None
            else Path(tempfile.gettempdir()) / _DEFAULT_TEMP_ROOT_NAME
        )
        self._repetition_history_store = repetition_history_store
        self._ffmpeg_bin = ffmpeg_bin
        self._ffprobe_bin = ffprobe_bin

    def create_creative_plan(self, execution: ProcessReelExecution) -> dict[str, Any]:
        context = self._planning_context_loader.load(execution)
        brief = plan_creative_brief(
            DirectorPlanInput(
                page_name=context.page_name,
                page_metadata=context.page_metadata,
                global_policy=context.policy,
                brief_index=context.brief_index,
                target_platforms=list(context.target_platforms),
                duration_seconds=context.duration_seconds,
            )
        )
        script = generate_script_output(brief)
        posting_plan = build_posting_plan(
            policy=brief.policy,
            page=PostingPlanPageContext(
                page_id=execution.page_id,
                page_name=context.page_name,
                page_metadata=context.page_metadata,
                target_platforms=list(context.target_platforms),
                timezone=context.timezone,
                locale=context.locale,
            ),
            family=PostingPlanFamilyContext(
                family_id=execution.reel_family_id,
                family_name=context.family_name,
                content_pillar=brief.content_pillar,
                metadata={"mode": context.family_mode},
            ),
            mode=brief.selected_mode,
            variant=PostingPlanVariantContext(
                variant_id=execution.reel_id,
                variant_label=context.variant_label,
                variant_index=context.brief_index,
                duration_seconds=brief.duration_seconds,
            ),
        )
        prompt = _build_primary_asset_prompt(
            brief_payload=brief.model_dump(mode="json"), script=script
        )
        duration_seconds = min(
            max(brief.duration_seconds, 5),
            RUNWAY_GEN45_MAX_DURATION_SECONDS,
        )
        return {
            "brief": brief.model_dump(mode="json"),
            "script": script.model_dump(mode="json"),
            "posting_plan": posting_plan.model_dump(mode="json"),
            "primary_asset_request": {
                "asset_class": _PRIMARY_ASSET_CLASS,
                "provider": _PRIMARY_ASSET_PROVIDER,
                "model": _PRIMARY_ASSET_MODEL,
                "prompt": prompt,
                "negative_prompt": "text overlays, captions, watermarks",
                "seed": context.brief_index + 1,
                "duration_seconds": duration_seconds,
                "fps": 24,
                "ratio": _PRIMARY_ASSET_RATIO,
                "motion": {"camera": "dynamic", "pace": "medium"},
                "reference_asset_ids": [],
                "request_context": {
                    "page_name": context.page_name,
                    "family_name": context.family_name,
                    "reel_id": execution.reel_id,
                },
            },
        }

    def resolve_assets(self, execution: ProcessReelExecution) -> dict[str, Any]:
        creative_output = _step_output(execution, "creative_planning")
        return self._asset_resolver.resolve_primary_asset(
            execution,
            creative_output=creative_output,
        )

    def edit_reel(self, execution: ProcessReelExecution) -> dict[str, Any]:
        creative_output = _step_output(execution, "creative_planning")
        asset_output = _step_output(execution, "asset_resolution")
        source_uri = _required_text(asset_output.get("storage_uri"), field_name="asset_resolution")
        overlay_timeline = _mapping(creative_output.get("script")).get("overlay_timeline")
        workdir = self._run_workdir(execution, "editing")
        workdir.mkdir(parents=True, exist_ok=True)
        artifact = render_basic_vertical_edit(
            source_uri=source_uri,
            workdir=workdir,
            storage_client=self._storage_client,
            overlay_timeline=cast(Any, overlay_timeline),
            ffmpeg_bin=self._ffmpeg_bin,
            ffprobe_bin=self._ffprobe_bin,
        )
        timeline_path = workdir / "timeline.json"
        timeline_path.write_text(
            json.dumps(
                {
                    "overlay_timeline": overlay_timeline,
                    "spoken_script": _mapping(creative_output.get("script")).get(
                        "spoken_script", []
                    ),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return {
            "edit_id": f"edit-{execution.reel_id}",
            "template_version": artifact.template_version,
            "source_uri": artifact.source_uri,
            "staged_source_path": str(artifact.staged_source_path),
            "final_video_path": str(artifact.final_video_path),
            "final_video_uri": artifact.final_video_path.as_uri(),
            "cover_path": str(artifact.cover_image_path),
            "cover_uri": artifact.cover_image_path.as_uri(),
            "timeline_uri": timeline_path.as_uri(),
            "duration_seconds": artifact.duration_seconds,
            "width": artifact.width,
            "height": artifact.height,
            "has_audio_track": artifact.has_audio_track,
        }

    def run_qa(self, execution: ProcessReelExecution) -> ProcessReelQAResult:
        editing_output = _step_output(execution, "editing")
        asset_output = _step_output(execution, "asset_resolution")
        format_report = evaluate_format_qa(
            final_video_path=_required_text(
                editing_output.get("final_video_path"),
                field_name="editing.final_video_path",
            ),
            cover_path=_required_text(
                editing_output.get("cover_path"),
                field_name="editing.cover_path",
            ),
            ffprobe_bin=self._ffprobe_bin,
        )
        repetition_result = evaluate_repetition(
            RepetitionGateRequest(
                candidate_key=_required_text(
                    asset_output.get("asset_key_hash", execution.reel_id),
                    field_name="asset_resolution.asset_key_hash",
                ),
                family_id=execution.reel_family_id,
                policy=_repetition_policy(asset_output),
            ),
            history_store=self._repetition_history_store,
        )
        repetition_failed = repetition_result.verdict.value == "fail"
        passed = format_report.passed and not repetition_failed
        verdict = "pass"
        if not passed:
            verdict = "fail"
        elif repetition_result.verdict.value == "warn":
            verdict = "warn"

        return ProcessReelQAResult(
            passed=passed,
            details={
                "verdict": verdict,
                "checks": [
                    *[check.as_payload() for check in format_report.checks],
                    repetition_result.as_payload(),
                ],
                "format": {
                    "verdict": format_report.verdict.value,
                    "message": format_report.message,
                    "failure_reasons": list(format_report.failure_reasons),
                },
                "repetition": repetition_result.as_payload(),
            },
        )

    def package_reel(self, execution: ProcessReelExecution) -> dict[str, Any]:
        creative_output = _step_output(execution, "creative_planning")
        asset_output = _step_output(execution, "asset_resolution")
        editing_output = _step_output(execution, "editing")
        workdir = self._run_workdir(execution, "package")
        workdir.mkdir(parents=True, exist_ok=True)
        built = build_ready_to_post_package(
            client=cast(Any, self._storage_client),
            layout=self._package_layout,
            reel_id=execution.reel_id,
            final_video_path=_required_text(
                editing_output.get("final_video_path"),
                field_name="editing.final_video_path",
            ),
            cover_path=_required_text(
                editing_output.get("cover_path"),
                field_name="editing.cover_path",
            ),
            caption_variants=_mapping(creative_output.get("script")).get("caption_variants", []),
            posting_plan=_mapping(creative_output.get("posting_plan")),
            provenance=_build_package_provenance(
                execution=execution,
                asset_output=asset_output,
                editing_output=editing_output,
            ),
            temp_root=workdir,
            upload_metadata={
                "reel-id": execution.reel_id,
                "run-id": execution.run_id,
            },
        )
        package_payload = dict(built.package_payload)
        package_payload["ready_for_publish"] = True
        package_payload["local_package_path"] = str(built.local_package.directory)
        return package_payload

    def _run_workdir(self, execution: ProcessReelExecution, step: str) -> Path:
        return self._temp_root / execution.run_id / step


@task
def validate_reel_context(reel_id: str) -> str:
    """Validate the reel identifier before downstream orchestration."""

    normalized_reel_id = reel_id.strip()
    if not normalized_reel_id:
        raise ValueError("reel_id must not be blank")
    return normalized_reel_id


def build_phase_one_process_reel_executor(
    *,
    settings: Settings | None = None,
    planning_context_loader: ProcessReelPlanningContextLoader | None = None,
    asset_resolver: ProcessReelAssetResolver | None = None,
    storage_client: ProcessReelStorageClient | None = None,
    temp_root: str | Path | None = None,
    repetition_history_store: RepetitionHistoryStore | None = None,
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
) -> PhaseOneProcessReelExecutor:
    """Build the concrete phase-1 executor used by the orchestrator flow."""

    resolved_settings = settings or Settings()
    resolved_storage_client = storage_client or _build_storage_client(resolved_settings)
    return PhaseOneProcessReelExecutor(
        planning_context_loader=planning_context_loader or SQLProcessReelPlanningContextLoader(),
        asset_resolver=asset_resolver
        or SQLProcessReelAssetResolver(
            settings=resolved_settings,
            storage_client=resolved_storage_client,
        ),
        storage_client=resolved_storage_client,
        package_layout=CanonicalStorageLayout(bucket=resolved_settings.minio_bucket),
        temp_root=temp_root,
        repetition_history_store=repetition_history_store,
        ffmpeg_bin=ffmpeg_bin,
        ffprobe_bin=ffprobe_bin,
    )


def build_process_reel_event_sink() -> ProcessReelEventSink:
    """Construct the default terminal-event sink for ``process_reel``."""

    return SQLProcessReelEventSink()


def build_process_reel_runtime() -> ProcessReelRuntime:
    """Construct the default service runtime for ``process_reel``."""

    context = orchestrator_service_context()
    return cast(
        ProcessReelRuntime,
        build_process_reel_service(
            actor=context.actor or "content-lab-orchestrator",
            executor=build_phase_one_process_reel_executor(),
        ),
    )


def _execution_from_payload(payload: dict[str, Any]) -> ProcessReelExecutionLike:
    from content_lab_api.services import ProcessReelExecution

    return cast(ProcessReelExecutionLike, ProcessReelExecution.from_payload(payload))


def _execution_to_payload(execution: ProcessReelExecutionLike) -> dict[str, Any]:
    return execution.to_payload()


@task
def start_process_reel(
    reel_id: str,
    *,
    dry_run: bool,
    run_id: str | None,
) -> dict[str, Any]:
    """Create or hydrate the persisted run and task rows for execution."""

    execution = build_process_reel_runtime().start_execution(
        reel_id=reel_id,
        dry_run=dry_run,
        run_id=run_id,
    )
    return _execution_to_payload(execution)


@task
def execute_creative_planning(execution_payload: dict[str, Any]) -> dict[str, Any]:
    """Run the creative-planning boundary and persist its task state."""

    execution = _execution_from_payload(execution_payload)
    return _execution_to_payload(build_process_reel_runtime().run_creative_planning(execution))


@task
def execute_asset_resolution(execution_payload: dict[str, Any]) -> dict[str, Any]:
    """Run the asset-resolution boundary and persist its task state."""

    execution = _execution_from_payload(execution_payload)
    return _execution_to_payload(build_process_reel_runtime().run_asset_resolution(execution))


@task
def execute_editing(execution_payload: dict[str, Any]) -> dict[str, Any]:
    """Run the editing boundary and persist its task state."""

    execution = _execution_from_payload(execution_payload)
    return _execution_to_payload(build_process_reel_runtime().run_editing(execution))


@task
def execute_qa(execution_payload: dict[str, Any]) -> dict[str, Any]:
    """Run the QA boundary and persist the QA task outcome."""

    execution = _execution_from_payload(execution_payload)
    return _execution_to_payload(build_process_reel_runtime().run_qa(execution))


@task
def execute_packaging(execution_payload: dict[str, Any]) -> dict[str, Any]:
    """Run the packaging boundary and persist its task state."""

    execution = _execution_from_payload(execution_payload)
    return _execution_to_payload(build_process_reel_runtime().run_packaging(execution))


@task
def mark_process_reel_ready(execution_payload: dict[str, Any]) -> dict[str, Any]:
    """Mark a successful run as ready/succeeded."""

    execution = _execution_from_payload(execution_payload)
    return build_process_reel_runtime().mark_ready(execution)


@task
def mark_process_reel_qa_failed(execution_payload: dict[str, Any]) -> dict[str, Any]:
    """Mark a completed run as ``qa_failed`` and skip packaging."""

    execution = _execution_from_payload(execution_payload)
    return build_process_reel_runtime().mark_qa_failed(execution)


@task
def mark_process_reel_failed(
    execution_payload: dict[str, Any],
    *,
    failed_step: str,
    error_message: str,
) -> dict[str, Any]:
    """Persist an unexpected terminal failure."""

    execution = _execution_from_payload(execution_payload)
    return build_process_reel_runtime().mark_failed(
        execution,
        failed_step=failed_step,
        error_message=error_message,
    )


@task
def emit_process_reel_terminal_event(summary: dict[str, Any]) -> dict[str, Any]:
    """Persist the terminal package-ready or failure outbox event."""

    return build_process_reel_event_sink().emit_terminal_event(summary)


def _qa_passed(execution_payload: dict[str, Any]) -> bool:
    outputs = execution_payload.get("outputs", {})
    if not isinstance(outputs, dict):
        return False
    qa_payload = outputs.get("qa", {})
    if not isinstance(qa_payload, dict):
        return False
    return bool(qa_payload.get("passed"))


@flow(name="process_reel")
def process_reel(
    reel_id: str = "demo-reel",
    dry_run: bool = False,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Run the full phase-1 ``process_reel`` package-generation workflow."""

    _ = orchestrator_service_context()
    validated_reel_id = validate_reel_context(reel_id)
    execution: dict[str, Any] | None = None
    current_step = "creative_planning"

    try:
        execution = start_process_reel(validated_reel_id, dry_run=dry_run, run_id=run_id)
        execution = execute_creative_planning(execution)
        current_step = "asset_resolution"
        execution = execute_asset_resolution(execution)
        current_step = "editing"
        execution = execute_editing(execution)
        current_step = "qa"
        execution = execute_qa(execution)
        if not _qa_passed(execution):
            summary = mark_process_reel_qa_failed(execution)
            emit_process_reel_terminal_event(summary)
            return summary
        current_step = "packaging"
        execution = execute_packaging(execution)
        summary = mark_process_reel_ready(execution)
        emit_process_reel_terminal_event(summary)
        return summary
    except Exception as exc:
        if execution is not None:
            summary = mark_process_reel_failed(
                execution,
                failed_step=current_step,
                error_message=str(exc),
            )
            emit_process_reel_terminal_event(summary)
        raise


def build_process_reel_kwargs(args: Namespace) -> dict[str, object]:
    """Map CLI arguments onto the flow signature."""

    return {"reel_id": args.reel_id, "dry_run": args.dry_run, "run_id": args.run_id}


FLOW_DEFINITION = FlowDefinition(
    name="process_reel",
    description="Plan, generate, edit, QA, package, and emit terminal events for a reel.",
    entrypoint=process_reel,
    build_kwargs=build_process_reel_kwargs,
)


def _step_output(execution: ProcessReelExecution, step: str) -> dict[str, Any]:
    payload = execution.outputs.get(step)
    if not isinstance(payload, Mapping):
        raise ValueError(f"Missing step output for {step!r}")
    return dict(payload)


def _build_primary_asset_prompt(*, brief_payload: Mapping[str, Any], script: Any) -> str:
    title = _required_text(brief_payload.get("title"), field_name="brief.title")
    description = _required_text(
        brief_payload.get("description") or title,
        field_name="brief.description",
    )
    hook_text = _required_text(getattr(script, "hook_text", None), field_name="script.hook_text")
    content_pillar = _optional_text(brief_payload.get("content_pillar"))
    fragments = [title, description, hook_text]
    if content_pillar is not None:
        fragments.append(f"Visual focus: {content_pillar}")
    return ". ".join(fragment.rstrip(".") for fragment in fragments if fragment).strip()


def _build_package_provenance(
    *,
    execution: ProcessReelExecution,
    asset_output: Mapping[str, Any],
    editing_output: Mapping[str, Any],
) -> dict[str, Any]:
    provider_job = _mapping(asset_output.get("provider_job"))
    provider_status = _optional_text(provider_job.get("status")) or "succeeded"
    provider_payload: dict[str, Any] = {
        "provider": _optional_text(provider_job.get("provider"))
        or _optional_text(asset_output.get("provider"))
        or _PRIMARY_ASSET_PROVIDER,
        "status": provider_status,
    }
    job_id = _optional_text(provider_job.get("external_ref")) or _optional_text(
        asset_output.get("provider_job_id")
    )
    if job_id is not None:
        provider_payload["job_id"] = job_id

    assets = [
        {
            "role": "source_clip",
            "storage_uri": _required_text(
                asset_output.get("storage_uri"),
                field_name="asset_resolution.storage_uri",
            ),
        }
    ]
    return {
        "editor_version": _required_text(
            editing_output.get("template_version"),
            field_name="editing.template_version",
        ),
        "assets": assets,
        "provider_jobs": [provider_payload],
        "source_run_id": execution.run_id,
        "asset_ids": _asset_ids(asset_output),
        "upstream_refs": {
            "timeline_uri": _required_text(
                editing_output.get("timeline_uri"),
                field_name="editing.timeline_uri",
            ),
        },
    }


def _asset_ids(asset_output: Mapping[str, Any]) -> list[str]:
    asset_id = _optional_text(asset_output.get("asset_id"))
    if asset_id is None:
        generation = _mapping(asset_output.get("generation"))
        asset_id = _optional_text(generation.get("asset_id"))
    return [] if asset_id is None else [asset_id]


def _repetition_policy(asset_output: Mapping[str, Any]) -> RepetitionPolicy:
    policy = _mapping(asset_output.get("policy"))
    return RepetitionPolicy(
        cooldown_seconds=_optional_int(policy.get("cooldown_seconds")),
        family_reuse_cap=_optional_int(policy.get("family_reuse_cap")),
    )


def _policy_with_family_mode(
    policy: PolicyStateDocument,
    *,
    family_mode: str,
) -> PolicyStateDocument:
    normalized_mode = family_mode.strip().lower()
    if normalized_mode not in {"exploit", "explore", "mutation", "chaos"}:
        return policy
    payload = policy.model_dump(mode="json")
    payload["mode_ratios"] = {
        "exploit": 1.0 if normalized_mode == "exploit" else 0.0,
        "explore": 1.0 if normalized_mode == "explore" else 0.0,
        "mutation": 1.0 if normalized_mode == "mutation" else 0.0,
        "chaos": 1.0 if normalized_mode == "chaos" else 0.0,
    }
    return PolicyStateDocument.model_validate(payload)


def _variant_brief_index(variant_label: Any) -> int:
    normalized = _optional_text(variant_label)
    if normalized is None:
        return 0
    alpha = normalized[0].upper()
    if "A" <= alpha <= "Z":
        return ord(alpha) - ord("A")
    return 0


def _coerce_platform(value: Any) -> Platform:
    normalized = _optional_text(value)
    if normalized is None:
        return Platform.INSTAGRAM
    try:
        return Platform(normalized.lower())
    except ValueError:
        return Platform.INSTAGRAM


def _build_storage_client(settings: Settings) -> S3StorageClient:
    return S3StorageClient(
        S3StorageConfig(
            endpoint=settings.minio_endpoint,
            access_key_id=settings.minio_root_user,
            secret_access_key=settings.minio_root_password.get_secret_value(),
            default_bucket=settings.minio_bucket,
        )
    )


def _required_text(value: Any, *, field_name: str) -> str:
    normalized = _optional_text(value)
    if normalized is None:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("boolean values are not valid integers here")
    return int(value)


def _coerce_positive_int(value: Any, *, default: int) -> int:
    resolved = _optional_int(value)
    if resolved is None or resolved <= 0:
        return default
    return resolved


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("boolean values are not valid floats here")
    return float(value)


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _sequence_of_text(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    items = [item for item in (_optional_text(raw) for raw in value) if item is not None]
    return items


def _as_uuid(value: str, *, field_name: str) -> uuid.UUID:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return uuid.UUID(normalized)


__all__ = [
    "FLOW_DEFINITION",
    "PhaseOnePlanningContext",
    "PhaseOneProcessReelExecutor",
    "ProcessReelAssetResolver",
    "ProcessReelEventSink",
    "ProcessReelPlanningContextLoader",
    "SQLProcessReelAssetResolver",
    "SQLProcessReelEventSink",
    "SQLProcessReelPlanningContextLoader",
    "build_phase_one_process_reel_executor",
    "build_process_reel_event_sink",
    "build_process_reel_kwargs",
    "build_process_reel_runtime",
    "process_reel",
]
