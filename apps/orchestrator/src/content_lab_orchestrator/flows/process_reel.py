"""Primary phase-1 **sequencing** flow for processing an individual reel.

**Ownership:** This Prefect flow defines the only supported ``process_reel`` step
order for real runs. It routes each step to ``ProcessReelPersistenceService`` in
``content_lab_api.services.process_reel`` (via ``build_process_reel_persistence_service``),
which persists ``Run`` / ``Task`` / ``Reel`` state. Creative, asset, edit, and package
work run through ``PhaseOneProcessReelExecutor`` and related injectables below.

The API package does *not* define an alternate end-to-end pipeline; persistence there
is invoked step-by-step as this flow executes.
"""

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
    GeneratedScriptOutput,
    PageMetadata,
    PolicyStateDocument,
    PostingPlanFamilyContext,
    PostingPlanPageContext,
    PostingPlanVariantContext,
    ScriptGeneratorPath,
    build_creative_trace,
    build_posting_plan,
    compile_provider_prompt,
    compile_scene_plan,
    generate_script_output,
    plan_creative_brief,
)
from content_lab_creative.script_generator import ScriptGenerator, ScriptGeneratorPathLike
from content_lab_creative.types import (
    CaptionVariant,
    CaptionVariantName,
    OverlayCue,
    ScriptBeat,
    ScriptOverlayEmphasis,
)
from content_lab_editing import (
    CompositionCrop,
    CompositionLayer,
    CompositionManifest,
    MotionTransform,
    build_canonical_timeline,
    build_overlay_render_manifest_for_qa,
    build_ready_to_post_package,
    build_timeline_render_trace,
    compose_and_store_layered_reel,
    render_basic_vertical_edit,
)
from content_lab_outbox import (
    build_process_reel_event_payload,
    process_reel_event_type,
)
from content_lab_storage import CanonicalStorageLayout, S3StorageClient, S3StorageConfig
from prefect.flows import flow
from prefect.tasks import task
from sqlalchemy.orm import Session, sessionmaker

from content_lab_api.db import SessionLocal
from content_lab_api.models import Asset, OutboxEvent, Page, ProviderJob, Reel, ReelFamily
from content_lab_api.schemas.pages import parse_page_metadata
from content_lab_api.services import (
    SQLAlchemyPhase1AssetRegistryStore,
    build_process_reel_persistence_service,
    ensure_task_row,
    get_provider_job_by_external_ref,
    load_policy_bundle,
    record_provider_job_submission,
)
from content_lab_api.services.process_reel import ProcessReelExecution, ProcessReelQAResult
from content_lab_core.types import Platform, QAVerdict
from content_lab_orchestrator.correlation import orchestrator_service_context
from content_lab_qa import (
    PackageQualityAssuranceError,
    RepetitionGateRequest,
    RepetitionHistoryStore,
    RepetitionPolicy,
    SemanticScriptQARequest,
    default_overlay_stack_policy_for_template,
    evaluate_alignment_qa,
    evaluate_format_qa,
    evaluate_media_sync_qa,
    evaluate_overlay_text_fidelity_qa,
    evaluate_repetition,
    evaluate_semantic_script,
    evaluate_timeline_timing_qa,
    qa_result_blocks_readiness,
    validate_caption_meta_language,
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
_DURATION_MISMATCH_TOLERANCE_SECONDS = 0.25


def _primary_asset_duration_seconds(requested_duration_seconds: int) -> int:
    return min(
        max(requested_duration_seconds, 5),
        RUNWAY_GEN45_MAX_DURATION_SECONDS,
    )


class ProcessReelExecutionLike(Protocol):
    """Minimal execution payload contract used inside the orchestrator app."""

    def to_payload(self) -> dict[str, Any]: ...


class ProcessReelRuntime(Protocol):
    """Typed view of the API persistence service used for each process-reel step."""

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

    def mark_package_qa_failed(
        self,
        execution: ProcessReelExecutionLike,
        *,
        error_message: str,
        package_qa: Mapping[str, Any] | None,
    ) -> dict[str, Any]: ...

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
    source_plan: dict[str, Any] | None = None


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
            family_metadata = cast(dict[str, Any], family.metadata_ or {})
            reel_metadata = cast(dict[str, Any], reel.metadata_ or {})
            source_plan = _mapping(reel_metadata.get("idea_plan")) or _mapping(
                family_metadata.get("idea_plan")
            )
            family_mode = _optional_text(family_metadata.get("mode")) or "explore"
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
                    reel_metadata.get("duration_seconds"),
                    default=_DEFAULT_REEL_DURATION_SECONDS,
                ),
                source_plan=source_plan or None,
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
        self._storage_layout = CanonicalStorageLayout(bucket=self._settings.minio_bucket)
        self._temp_root = Path(tempfile.gettempdir()) / _DEFAULT_TEMP_ROOT_NAME
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
        composition_asset = self._resolve_composition_manifest_asset(
            execution,
            creative_output=creative_output,
            request_payload=request_payload,
        )
        if composition_asset is not None:
            return composition_asset

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

    def _resolve_composition_manifest_asset(
        self,
        execution: ProcessReelExecution,
        *,
        creative_output: Mapping[str, Any],
        request_payload: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        manifest_payload = _composition_manifest_from_creative_output(creative_output)
        if manifest_payload is None:
            return None
        roles = _mapping(manifest_payload.get("roles"))
        visual_roles = [
            (str(role), _mapping(value))
            for role, value in roles.items()
            if _mapping(value)
        ]
        visual_roles = [
            (role, value)
            for role, value in visual_roles
            if _role_storage_uri(value) is not None and _role_visual_media_type(value) is not None
        ]
        if not visual_roles:
            return None

        background_role = next(
            (
                (role, value)
                for role, value in visual_roles
                if role in {"background", "background_image", "environment"}
            ),
            visual_roles[0],
        )
        foreground_roles = [
            (role, value)
            for role, value in visual_roles
            if value is not background_role[1]
            and role not in {"audio", "format"}
            and not _role_has_baked_reference_marks(value)
        ][:3]
        duration = _optional_float(request_payload.get("duration_seconds")) or _optional_float(
            _mapping(creative_output.get("scene_plan")).get("duration_seconds")
        ) or _DEFAULT_REEL_DURATION_SECONDS
        duration = max(1.0, float(duration))
        background_asset_id = _role_asset_id(background_role[1], fallback=f"{background_role[0]}-asset")
        asset_sources: dict[str, dict[str, object]] = {
            background_asset_id: {
                "source": _required_text(
                    _role_storage_uri(background_role[1]),
                    field_name="composition_manifest.roles.background.storage_uri",
                ),
                "media_type": _role_visual_media_type(background_role[1]) or "image",
            }
        }
        layers: list[CompositionLayer] = []
        for index, (role, value) in enumerate(foreground_roles, start=1):
            asset_id = _role_asset_id(value, fallback=f"{role}-{index}")
            media_type = _role_visual_media_type(value) or "image"
            asset_sources[asset_id] = {
                "source": _required_text(
                    _role_storage_uri(value),
                    field_name=f"composition_manifest.roles.{role}.storage_uri",
                ),
                "media_type": media_type,
            }
            width = 760 if index == 1 else 520
            height = 760 if index == 1 else 520
            layers.append(
                CompositionLayer(
                    layer_id=f"{role}-{index}",
                    asset_id=asset_id,
                    asset_kind=_role_asset_kind(value, fallback=role),
                    media_type=media_type,
                    z_index=10 + index,
                    start_time=0,
                    end_time=duration,
                    x=max(0, 540 - width // 2 + (index - 1) * 84),
                    y=max(0, 960 - height // 2 + (index - 1) * 112),
                    width=width,
                    height=height,
                    crop=_role_source_crop(value, layer_role=role),
                    opacity=0.96,
                    motion_transform=MotionTransform(
                        preset="float" if index == 1 else "slow_zoom",
                    ),
                )
            )

        composition_manifest = CompositionManifest(
            canvas_width=1080,
            canvas_height=1920,
            duration=duration,
            fps=24,
            background_layer=CompositionLayer(
                layer_id="background",
                asset_id=background_asset_id,
                asset_kind=_role_asset_kind(background_role[1], fallback=background_role[0]),
                media_type=_role_visual_media_type(background_role[1]) or "image",
                z_index=0,
                start_time=0,
                end_time=duration,
                x=0,
                y=0,
                width=1080,
                height=1920,
                crop=_role_source_crop(background_role[1], layer_role=background_role[0]),
                opacity=1.0,
                motion_transform=MotionTransform(preset="slow_zoom"),
            ),
            layers=layers,
            audio_layers=[],
        )
        workdir = self._temp_root / execution.run_id / "asset-composition"
        output_path = workdir / "asset_pack_source.mp4"
        render_asset_id = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"content-lab-layered-source:{execution.run_id}")
        )
        stored = compose_and_store_layered_reel(
            composition_manifest,
            asset_sources=asset_sources,
            output_path=output_path,
            client=cast(S3StorageClient, self._storage_client),
            layout=self._storage_layout,
            render_asset_id=render_asset_id,
            storage_client=self._storage_client,
            staging_dir=workdir / "inputs",
            timeout_seconds=120,
            asset_class="derived_cinematic_source",
            filename="source.mp4",
            upload_metadata={
                "run-id": execution.run_id,
                "reel-id": execution.reel_id,
                "source": "asset-pack-composition",
            },
        )
        with self._session_factory() as session:
            asset_uuid = uuid.UUID(render_asset_id)
            if session.get(Asset, asset_uuid) is None:
                asset = Asset(
                    org_id=uuid.UUID(execution.org_id),
                    asset_class="derived_cinematic_source",
                    storage_uri=stored.stored_asset.storage_uri,
                    source="asset_pack_composition",
                    content_hash=stored.stored_asset.checksums.content_hash,
                    status="active",
                    metadata_={
                        "reel_id": execution.reel_id,
                        "run_id": execution.run_id,
                        "composition_manifest": composition_manifest.model_dump(mode="json"),
                        "source_composition_manifest": manifest_payload,
                    },
                    asset_key=f"derived_cinematic_source:{execution.run_id}",
                    asset_key_hash=render_asset_id.replace("-", ""),
                )
                asset.id = asset_uuid
                session.add(asset)
                session.commit()
        return {
            "asset_id": render_asset_id,
            "asset_kind": "layered_composition",
            "asset_source": "asset_pack_composition",
            "media_type": "video",
            "provider": "asset_pack_compositor",
            "model": "layered_ffmpeg",
            "storage_uri": stored.stored_asset.storage_uri,
            "content_hash": stored.stored_asset.checksums.content_hash,
            "content_type": stored.stored_asset.stored_object.content_type,
            "canonical_params": {"duration_seconds": duration, "ratio": "9:16", "fps": 24},
            "provider_job": {
                "provider": "asset_pack_compositor",
                "status": "succeeded",
            },
            "composition_manifest": composition_manifest.model_dump(mode="json"),
            "source_composition_manifest": manifest_payload,
            "resolution_source": "asset_pack_composition",
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


def _brief_payload_from_source_plan(
    *,
    brief_payload: dict[str, Any],
    source_plan: Mapping[str, Any],
    context: PhaseOnePlanningContext,
    max_duration_seconds: int,
) -> dict[str, Any]:
    title = _fit_text(
        _optional_text(source_plan.get("title")) or context.family_name,
        max_chars=200,
    )
    angle = _fit_text(
        _optional_text(source_plan.get("angle"))
        or _optional_text(brief_payload.get("narrative_goal"))
        or f"Create a practical short-form package for {context.page_name}.",
        max_chars=280,
    )
    content_pillar = _fit_text(
        _optional_text(source_plan.get("content_pillar")) or title,
        max_chars=160,
    )
    next_payload = dict(brief_payload)
    next_payload.update(
        {
            "title": title,
            "description": angle,
            "content_pillar": content_pillar,
            "narrative_goal": _viewer_facing_copy(angle),
            "primary_call_to_action": _plan_primary_cta(source_plan),
            "duration_seconds": _source_plan_duration_seconds(
                source_plan,
                default=context.duration_seconds,
                max_duration_seconds=max_duration_seconds,
            ),
            "source_plan": dict(source_plan),
        }
    )
    tags = [str(tag) for tag in next_payload.get("tags", []) if str(tag).strip()]
    next_payload["tags"] = tags
    return next_payload


def _script_from_source_plan(
    *,
    source_plan: Mapping[str, Any],
    brief_payload: Mapping[str, Any],
    context: PhaseOnePlanningContext,
) -> GeneratedScriptOutput:
    duration_seconds = int(brief_payload["duration_seconds"])
    hook_text = _fit_text(
        _optional_text(source_plan.get("hook"))
        or f"What makes {context.page_name} worth following this week?",
        max_chars=200,
    )
    spoken_lines = _source_plan_spoken_lines(source_plan, hook_text=hook_text)
    spoken_script = _source_plan_spoken_script(
        source_plan=source_plan,
        lines=spoken_lines,
        duration_seconds=duration_seconds,
    )
    overlay_timeline = _source_plan_overlays(
        source_plan=source_plan,
        hook_text=hook_text,
        spoken_script=spoken_script,
    )
    hashtags = _source_plan_hashtags(
        page_name=context.page_name,
        title=_required_text(brief_payload.get("title"), field_name="brief.title"),
    )
    return GeneratedScriptOutput(
        provider_name="source_plan",
        generator_path="idea_plan",
        generation_metadata={
            "generator_path": "idea_plan",
            "fallback": False,
            "strategy": "saved_idea_plan_v1",
            "plan_title": brief_payload.get("title"),
        },
        brief_title=_required_text(brief_payload.get("title"), field_name="brief.title"),
        duration_seconds=duration_seconds,
        hook_text=hook_text,
        spoken_script=spoken_script,
        overlay_timeline=overlay_timeline,
        caption_variants=_source_plan_caption_variants(
            source_plan=source_plan,
            hook_text=hook_text,
            title=_required_text(brief_payload.get("title"), field_name="brief.title"),
            angle=_required_text(
                brief_payload.get("narrative_goal"),
                field_name="brief.narrative_goal",
            ),
            hashtags=hashtags,
            page_name=context.page_name,
        ),
        hashtags=hashtags,
        pinned_comments=[],
    )


def _source_plan_spoken_lines(source_plan: Mapping[str, Any], *, hook_text: str) -> list[str]:
    beats = _source_plan_beats(source_plan)
    if not beats:
        return [
            _viewer_facing_copy(hook_text),
            "Try one useful shift today.",
            _viewer_facing_copy(_plan_primary_cta(source_plan) or "Try the next step today."),
        ]

    lines: list[str] = []
    for index, beat in enumerate(beats):
        beat_text = _required_text(beat.get("text"), field_name=f"source_plan.beats[{index}].text")
        line = hook_text if index == 0 else beat_text
        lines.append(_fit_text(_viewer_facing_copy(line), max_chars=280))
    return lines


def _source_plan_spoken_script(
    *,
    source_plan: Mapping[str, Any],
    lines: list[str],
    duration_seconds: int,
) -> list[ScriptBeat]:
    durations = _source_plan_beat_durations(source_plan, count=len(lines), total=duration_seconds)
    beats: list[ScriptBeat] = []
    cursor = 0
    for index, line in enumerate(lines):
        next_cursor = duration_seconds if index == len(lines) - 1 else cursor + durations[index]
        beats.append(
            ScriptBeat(
                start_seconds=cursor,
                end_seconds=next_cursor,
                narration=line,
                shot_direction=_source_plan_shot_direction(index, len(lines)),
            )
        )
        cursor = next_cursor
    return beats


def _source_plan_overlays(
    *,
    source_plan: Mapping[str, Any],
    hook_text: str,
    spoken_script: list[ScriptBeat],
) -> list[OverlayCue]:
    hook_overlay = _viewer_facing_copy(hook_text)
    value_overlay = _source_plan_value_overlay(source_plan)
    cta_overlay = _source_plan_cta_overlay(source_plan)
    overlays: list[OverlayCue] = []
    for index, beat in enumerate(spoken_script):
        if index == 0:
            emphasis = ScriptOverlayEmphasis.HOOK
            text = hook_overlay
        elif index == len(spoken_script) - 1:
            emphasis = ScriptOverlayEmphasis.CTA
            text = cta_overlay
        else:
            emphasis = ScriptOverlayEmphasis.VALUE
            text = value_overlay
        overlays.append(
            OverlayCue(
                start_seconds=beat.start_seconds,
                end_seconds=beat.end_seconds,
                text=text,
                emphasis=emphasis,
            )
        )
    return overlays


def _source_plan_value_overlay(source_plan: Mapping[str, Any]) -> str:
    beats = _source_plan_beats(source_plan)
    for beat in beats[1:-1] or beats[1:]:
        text = _optional_text(beat.get("text"))
        if text is not None:
            return _fit_text(_viewer_facing_copy(text), max_chars=80)
    if len(beats) == 1:
        text = _optional_text(beats[0].get("text"))
        if text is not None:
            return _fit_text(_viewer_facing_copy(text), max_chars=80)
    return _fit_text(_viewer_facing_copy(_optional_text(source_plan.get("angle")) or "Watch the build"), max_chars=80)


def _source_plan_cta_overlay(source_plan: Mapping[str, Any]) -> str:
    beats = _source_plan_beats(source_plan)
    if beats:
        text = _optional_text(beats[-1].get("text"))
        if text is not None:
            return _fit_text(_viewer_facing_copy(text), max_chars=80)
    return _fit_text(
        _viewer_facing_copy(_plan_primary_cta(source_plan) or "Save this finished reel"),
        max_chars=80,
    )


def _source_plan_caption_variants(
    *,
    source_plan: Mapping[str, Any],
    hook_text: str,
    title: str,
    angle: str,
    hashtags: list[str],
    page_name: str,
) -> list[CaptionVariant]:
    raw_caption_angles = source_plan.get("caption_angles")
    caption_angles = (
        [str(item).strip() for item in raw_caption_angles if str(item).strip()]
        if isinstance(raw_caption_angles, list)
        else []
    )
    short = _viewer_facing_copy(caption_angles[0] if caption_angles else hook_text)
    standard_tail = _viewer_facing_copy(caption_angles[1] if len(caption_angles) > 1 else angle)
    engagement = _viewer_facing_copy(caption_angles[2] if len(caption_angles) > 2 else hook_text)
    return [
        CaptionVariant(
            variant=CaptionVariantName.SHORT,
            text=_fit_text(short, max_chars=2_200),
        ),
        CaptionVariant(
            variant=CaptionVariantName.STANDARD,
            text=_fit_text(
                f"{page_name}: {_viewer_facing_copy(angle)} {standard_tail} {' '.join(hashtags)}",
                max_chars=2_200,
            ),
        ),
        CaptionVariant(
            variant=CaptionVariantName.ENGAGEMENT,
            text=_fit_text(f"{engagement} {hook_text}", max_chars=2_200),
        ),
    ]


def _source_plan_beats(source_plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_beats = source_plan.get("beats")
    if not isinstance(raw_beats, list):
        return []
    return [
        dict(beat)
        for beat in raw_beats
        if isinstance(beat, Mapping) and _optional_text(beat.get("text")) is not None
    ]


def _source_plan_beat_durations(
    source_plan: Mapping[str, Any],
    *,
    count: int,
    total: int,
) -> list[int]:
    beats = _source_plan_beats(source_plan)
    durations: list[int] = []
    for beat in beats[:count]:
        try:
            seconds = int(beat.get("seconds") or 0)
        except (TypeError, ValueError):
            seconds = 0
        if seconds > 0:
            durations.append(seconds)
    if len(durations) != count or sum(durations) <= 0:
        return _even_durations(total=total, count=count)
    delta = total - sum(durations)
    durations[-1] = max(1, durations[-1] + delta)
    return durations


def _source_plan_duration_seconds(
    source_plan: Mapping[str, Any],
    *,
    default: int,
    max_duration_seconds: int,
) -> int:
    beats = _source_plan_beats(source_plan)
    total = 0
    for beat in beats:
        try:
            seconds = int(beat.get("seconds") or 0)
        except (TypeError, ValueError):
            seconds = 0
        if seconds > 0:
            total += seconds
    resolved = total if total >= 5 else default
    return min(max(resolved, 5), max_duration_seconds, 180)


def _even_durations(*, total: int, count: int) -> list[int]:
    if count <= 0:
        return []
    base, remainder = divmod(total, count)
    return [base + (1 if index < remainder else 0) for index in range(count)]


def _source_plan_shot_direction(index: int, count: int) -> str:
    if index == 0:
        return "Open on the clearest visual proof and make the saved plan hook legible immediately."
    if index == count - 1:
        return "Resolve on a clean final frame that supports the planned next step."
    return "Show the planned shift or example with a simple, readable visual demonstration."


def _plan_primary_cta(source_plan: Mapping[str, Any]) -> str | None:
    caption_angles = source_plan.get("caption_angles")
    if isinstance(caption_angles, list) and caption_angles:
        for item in reversed(caption_angles):
            text = _optional_text(item)
            if text is not None:
                return _fit_text(text, max_chars=200)
    beats = _source_plan_beats(source_plan)
    if beats:
        return _fit_text(
            _required_text(beats[-1].get("text"), field_name="source_plan.beats[-1].text"),
            max_chars=200,
        )
    return None


def _source_plan_hashtags(*, page_name: str, title: str) -> list[str]:
    _ = title
    hashtags = [_hashtag(page_name), "#usefultips"]
    seen: set[str] = set()
    unique: list[str] = []
    for hashtag in hashtags:
        lowered = hashtag.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique.append(hashtag)
    return unique


def _hashtag(value: str) -> str:
    cleaned = "".join(char for char in value if char.isalnum())
    return f"#{cleaned.lower()}" if cleaned else "#content"


def _viewer_facing_copy(value: str) -> str:
    replacements = (
        ("short-form reel", "useful update"),
        ("short form reel", "useful update"),
        ("page strategy", "page approach"),
        ("strategy into a reel", "approach into a useful update"),
        ("into a reel", "into a useful update"),
        ("reel", "update"),
        ("content planning block", "planning block"),
    )
    normalized = str(value)
    for old, new in replacements:
        normalized = normalized.replace(old, new).replace(old.title(), new)
    return " ".join(normalized.split())


def _fit_text(value: str, *, max_chars: int) -> str:
    normalized = " ".join(str(value).split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "."


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
        script_generator: ScriptGenerator | None = None,
        script_generator_path: ScriptGeneratorPathLike = ScriptGeneratorPath.RULES_PLUS_PROVIDER,
        emit_creative_trace: bool = True,
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
        self._script_generator = script_generator
        self._script_generator_path = script_generator_path
        self._emit_creative_trace = emit_creative_trace
        self._ffmpeg_bin = ffmpeg_bin
        self._ffprobe_bin = ffprobe_bin

    def create_creative_plan(self, execution: ProcessReelExecution) -> dict[str, Any]:
        context = self._planning_context_loader.load(execution)
        duration_seconds = _primary_asset_duration_seconds(context.duration_seconds)
        brief = plan_creative_brief(
            DirectorPlanInput(
                page_name=context.page_name,
                page_metadata=context.page_metadata,
                global_policy=context.policy,
                brief_index=context.brief_index,
                target_platforms=list(context.target_platforms),
                duration_seconds=duration_seconds,
            )
        )
        if context.source_plan is None:
            brief_payload = brief.model_dump(mode="json")
            script = generate_script_output(
                brief,
                generator=self._script_generator,
                generator_path=self._script_generator_path,
            )
        else:
            brief_payload = _brief_payload_from_source_plan(
                brief_payload=brief.model_dump(mode="json"),
                source_plan=context.source_plan,
                context=context,
                max_duration_seconds=duration_seconds,
            )
            script = _script_from_source_plan(
                source_plan=context.source_plan,
                brief_payload=brief_payload,
                context=context,
            )
        script_payload = script.model_dump(mode="json")
        script_generation = _script_generation_metadata(script_payload)
        script_lint = _script_lint_result(script_payload)
        scene_plan = compile_scene_plan(brief=brief_payload, script=script)
        scene_plan_payload = scene_plan.model_dump(mode="json")
        canonical_timeline_payload = build_canonical_timeline(
            timeline_id=f"timeline-{execution.reel_id}",
            duration_seconds=float(scene_plan.duration_seconds),
            source_uri=f"s3://pending/reel/{execution.reel_id}/source.mp4",
            scene_plan=scene_plan_payload,
            overlay_timeline=cast(Any, script_payload.get("overlay_timeline")),
            spoken_script=cast(Any, script_payload.get("spoken_script")),
        ).model_dump(mode="json")
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
                content_pillar=_required_text(
                    brief_payload.get("content_pillar"),
                    field_name="brief.content_pillar",
                ),
                metadata={"mode": context.family_mode},
            ),
            mode=brief.selected_mode,
            variant=PostingPlanVariantContext(
                variant_id=execution.reel_id,
                variant_label=context.variant_label,
                variant_index=context.brief_index,
                duration_seconds=int(brief_payload["duration_seconds"]),
            ),
            available_caption_variants=[
                str(caption.get("variant"))
                for caption in cast(
                    list[dict[str, Any]], script_payload.get("caption_variants", [])
                )
            ],
        )
        if _script_lint_failed(script_lint):
            return {
                "brief": brief_payload,
                "script": script_payload,
                "script_generation": script_generation,
                "script_lint": script_lint,
                "scene_plan": scene_plan_payload,
                "canonical_timeline": canonical_timeline_payload,
                "posting_plan": posting_plan.model_dump(mode="json"),
                "creative_blocked": True,
            }
        compiled_prompt = _build_primary_asset_prompt(
            brief_payload=brief_payload,
            scene_plan=scene_plan,
        )
        compiled_prompt_payload = compiled_prompt.model_dump(mode="json")
        duration_seconds = _primary_asset_duration_seconds(int(brief_payload["duration_seconds"]))
        return {
            "brief": brief_payload,
            "script": script_payload,
            "script_generation": script_generation,
            "script_lint": script_lint,
            "scene_plan": scene_plan_payload,
            "canonical_timeline": canonical_timeline_payload,
            "compiled_prompt": compiled_prompt_payload,
            "posting_plan": posting_plan.model_dump(mode="json"),
            "primary_asset_request": {
                "asset_class": _PRIMARY_ASSET_CLASS,
                "provider": _PRIMARY_ASSET_PROVIDER,
                "model": _PRIMARY_ASSET_MODEL,
                "prompt": compiled_prompt.prompt,
                "scene_plan": scene_plan_payload,
                "compiled_prompt": compiled_prompt_payload,
                "prompt_trace": compiled_prompt_payload["trace"],
                "negative_prompt": compiled_prompt.negative_prompt,
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
        script_payload = _mapping(creative_output.get("script"))
        scene_plan_payload = _mapping(creative_output.get("scene_plan"))
        canonical_timeline_payload = _mapping(creative_output.get("canonical_timeline"))
        if not canonical_timeline_payload:
            canonical_timeline_payload = build_canonical_timeline(
                timeline_id=f"timeline-{execution.reel_id}",
                duration_seconds=float(
                    scene_plan_payload.get("duration_seconds")
                    or script_payload.get("duration_seconds")
                    or _DEFAULT_REEL_DURATION_SECONDS
                ),
                source_uri=source_uri,
                scene_plan=scene_plan_payload,
                overlay_timeline=cast(Any, script_payload.get("overlay_timeline")),
                spoken_script=cast(Any, script_payload.get("spoken_script")),
            ).model_dump(mode="json")

        canonical_overlay_timeline = cast(
            list[dict[str, Any]],
            canonical_timeline_payload.get("overlays", []),
        )
        canonical_scene_plan = {
            "schema_version": "canonical_timeline_projection_v1",
            "duration_seconds": canonical_timeline_payload.get("duration_seconds"),
            "scenes": canonical_timeline_payload.get("scenes", []),
        }
        expected_timeline_duration_seconds = float(canonical_timeline_payload["duration_seconds"])
        requested_provider_duration_seconds = _optional_float(
            _mapping(asset_output.get("canonical_params")).get("duration_seconds")
        ) or _optional_float(
            _mapping(creative_output.get("primary_asset_request")).get("duration_seconds")
        )
        workdir = self._run_workdir(execution, "editing")
        workdir.mkdir(parents=True, exist_ok=True)
        artifact = render_basic_vertical_edit(
            source_uri=source_uri,
            workdir=workdir,
            storage_client=self._storage_client,
            overlay_timeline=cast(Any, canonical_overlay_timeline),
            scene_plan_for_overlay_diagnostics=canonical_scene_plan,
            expected_timeline_duration_seconds=expected_timeline_duration_seconds,
            ffmpeg_bin=self._ffmpeg_bin,
            ffprobe_bin=self._ffprobe_bin,
        )
        timeline_path = workdir / "timeline.json"
        timeline_path.write_text(
            json.dumps(
                {
                    "timeline": canonical_timeline_payload,
                    "overlay_render_report": artifact.overlay_render_report,
                    "rendered_overlay_manifest": artifact.rendered_overlay_manifest.as_json_dict(),
                    "overlay_render_trace_uri": artifact.overlay_render_trace_path.as_uri(),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        overlay_rows, overlay_safe_area = build_overlay_render_manifest_for_qa(
            artifact.overlay_manifest,
            frame_width=int(artifact.width),
            frame_height=int(artifact.height),
        )
        stack_policy = default_overlay_stack_policy_for_template(artifact.editorial_template_id)
        duration_contract = _validate_duration_contract(
            requested_provider_duration_seconds=requested_provider_duration_seconds,
            source_clip_duration_seconds=float(artifact.source_duration_seconds),
            scene_plan_duration_seconds=expected_timeline_duration_seconds,
            final_rendered_duration_seconds=float(artifact.duration_seconds),
            tolerance_seconds=_DURATION_MISMATCH_TOLERANCE_SECONDS,
        )
        timeline_render_trace_payload = build_timeline_render_trace(
            canonical_timeline=canonical_timeline_payload,
            final_video_duration_seconds=float(artifact.duration_seconds),
            final_video_width=int(artifact.width),
            final_video_height=int(artifact.height),
            final_video_fps=artifact.fps,
            final_video_path_or_uri=artifact.final_video_path.as_uri(),
            final_video_has_video_stream=True,
            final_video_has_audio_stream=bool(artifact.has_audio_track),
            final_audio_duration_seconds=artifact.audio_duration_seconds,
            final_video_codec=artifact.video_codec,
            final_audio_codec=artifact.audio_codec,
            source_asset_duration_seconds=float(artifact.source_duration_seconds),
            source_path_or_uri=artifact.source_uri,
            creative_duration_seconds=expected_timeline_duration_seconds,
            editing_duration_seconds=float(artifact.duration_seconds),
            cover_timestamp_seconds=float(artifact.cover_frame_timestamp_seconds),
            audio_padded=not artifact.source_had_audio_track,
            audio_trimmed=True,
            source_trimmed=False,
        )
        timeline_render_trace_path = workdir / "timeline_render_trace.json"
        timeline_render_trace_path.write_text(
            json.dumps(timeline_render_trace_payload, indent=2, sort_keys=True) + "\n",
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
            "cover_frame_timestamp_seconds": artifact.cover_frame_timestamp_seconds,
            "timeline_uri": timeline_path.as_uri(),
            "timeline": canonical_timeline_payload,
            "timeline_render_trace_uri": timeline_render_trace_path.as_uri(),
            "timeline_render_trace": timeline_render_trace_payload,
            "duration_seconds": artifact.duration_seconds,
            "source_duration_seconds": artifact.source_duration_seconds,
            "requested_provider_duration_seconds": requested_provider_duration_seconds,
            "scene_plan_duration_seconds": expected_timeline_duration_seconds,
            "duration_contract": duration_contract,
            "width": artifact.width,
            "height": artifact.height,
            "has_audio_track": artifact.has_audio_track,
            "editorial_template_id": artifact.editorial_template_id,
            "overlay_stack_policy": stack_policy,
            "overlay_safe_area": overlay_safe_area,
            "overlay_render_manifest": overlay_rows,
            "overlay_render_report": artifact.overlay_render_report,
            "rendered_overlay_manifest": artifact.rendered_overlay_manifest.as_json_dict(),
            "overlay_render_trace": artifact.overlay_render_trace,
            "overlay_render_trace_path": str(artifact.overlay_render_trace_path),
            "overlay_render_trace_uri": artifact.overlay_render_trace_path.as_uri(),
        }

    def run_qa(self, execution: ProcessReelExecution) -> ProcessReelQAResult:
        creative_output = _step_output(execution, "creative_planning")
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
        semantic_report = evaluate_semantic_script(
            SemanticScriptQARequest(
                script=_mapping(creative_output.get("script")),
                scene_plan=_mapping(creative_output.get("scene_plan")) or None,
                brief=_mapping(creative_output.get("brief")) or None,
            )
        )
        alignment_report = evaluate_alignment_qa(
            brief=_mapping(creative_output.get("brief")),
            script=_mapping(creative_output.get("script")),
            scene_plan=_mapping(creative_output.get("scene_plan")),
            compiled_prompt=_mapping(creative_output.get("compiled_prompt")),
            editing=editing_output,
        )
        overlay_fidelity_report = evaluate_overlay_text_fidelity_qa(
            script=_mapping(creative_output.get("script")),
            editing=editing_output,
        )
        timeline_timing_report = evaluate_timeline_timing_qa(
            script=_mapping(creative_output.get("script")),
            scene_plan=_mapping(creative_output.get("scene_plan")) or None,
            editing=editing_output,
        )
        media_sync_report = evaluate_media_sync_qa(
            editing=editing_output,
        )
        script_payload = _mapping(creative_output.get("script"))
        caption_meta_result = validate_caption_meta_language(
            {"creative_trace": {"script": script_payload}},
        )
        alignment_gate = alignment_report.as_qa_result()
        qa_checks = [
            *[check for check in format_report.checks],
            repetition_result,
            semantic_report.as_qa_result(),
            alignment_gate,
            overlay_fidelity_report.as_qa_result(),
            timeline_timing_report,
            media_sync_report,
            caption_meta_result,
        ]
        blocking_failures = [
            check.as_payload() for check in qa_checks if qa_result_blocks_readiness(check)
        ]
        advisory_failures = [
            check.as_payload()
            for check in qa_checks
            if check.verdict == QAVerdict.FAIL and not qa_result_blocks_readiness(check)
        ]
        passed = not blocking_failures
        has_advisory_issue = bool(advisory_failures) or any(
            check.verdict == QAVerdict.WARN for check in qa_checks
        )
        verdict = "pass"
        if not passed:
            verdict = "fail"
        elif has_advisory_issue:
            verdict = "warn"

        return ProcessReelQAResult(
            passed=passed,
            details={
                "verdict": verdict,
                "checks": [check.as_payload() for check in qa_checks],
                "blocking_failures": blocking_failures,
                "advisory_failures": advisory_failures,
                "format": {
                    "verdict": format_report.verdict.value,
                    "message": format_report.message,
                    "failure_reasons": list(format_report.failure_reasons),
                },
                "repetition": repetition_result.as_payload(),
                "semantic_script": {
                    "verdict": semantic_report.verdict.value,
                    "message": semantic_report.message,
                    "failure_reasons": list(semantic_report.failure_reasons),
                    "findings": [
                        finding.model_dump(mode="json") for finding in semantic_report.findings
                    ],
                },
                "alignment": {
                    "verdict": alignment_report.verdict.value,
                    "message": alignment_report.message,
                    "findings": [
                        finding.model_dump(mode="json") for finding in alignment_report.findings
                    ],
                    "metrics": dict(alignment_report.metrics),
                    "skipped": alignment_report.skipped,
                    "skip_reason": alignment_report.skip_reason,
                    "lead_text": alignment_report.lead_text,
                },
                "overlay_text_fidelity": {
                    "verdict": overlay_fidelity_report.verdict.value,
                    "message": overlay_fidelity_report.message,
                    "findings": [
                        finding.model_dump(mode="json")
                        for finding in overlay_fidelity_report.findings
                    ],
                },
                "timeline_timing": timeline_timing_report.as_payload(),
                "media_sync": media_sync_report.as_payload(),
                "caption_meta_language": caption_meta_result.as_payload(),
            },
        )

    def package_reel(self, execution: ProcessReelExecution) -> dict[str, Any]:
        creative_output = _step_output(execution, "creative_planning")
        asset_output = _step_output(execution, "asset_resolution")
        editing_output = _step_output(execution, "editing")
        timeline_payload = _mapping(editing_output.get("timeline"))
        if not timeline_payload:
            raise ValueError("editing.timeline is required for package assembly")
        timeline_render_trace_payload = _mapping(editing_output.get("timeline_render_trace"))
        if not timeline_render_trace_payload:
            raise ValueError("editing.timeline_render_trace is required for package assembly")
        overlay_render_trace_payload = _mapping(editing_output.get("overlay_render_trace"))
        if not overlay_render_trace_payload:
            raise ValueError("editing.overlay_render_trace is required for package assembly")
        workdir = self._run_workdir(execution, "package")
        workdir.mkdir(parents=True, exist_ok=True)
        creative_trace = None
        if self._emit_creative_trace:
            creative_trace = build_creative_trace(
                reel_id=execution.reel_id,
                run_id=execution.run_id,
                creative_output=creative_output,
            ).model_dump(mode="json")
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
                creative_output=creative_output,
                asset_output=asset_output,
                editing_output=editing_output,
            ),
            creative_trace=creative_trace,
            overlay_render_trace=overlay_render_trace_payload,
            timeline=timeline_payload,
            timeline_render_trace=timeline_render_trace_payload,
            composition_manifest=_composition_manifest_from_creative_output(creative_output),
            temp_root=workdir,
            upload_metadata={
                "reel-id": execution.reel_id,
                "run-id": execution.run_id,
            },
        )
        package_payload = dict(built.package_payload)
        layered_output = _layered_output_from_editing_output(editing_output)
        if layered_output:
            package_payload["layered_output"] = layered_output
            package_payload["final_video_metadata"] = layered_output
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
    script_generator: ScriptGenerator | None = None,
    script_generator_path: ScriptGeneratorPathLike = ScriptGeneratorPath.RULES_PLUS_PROVIDER,
    emit_creative_trace: bool = True,
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
        script_generator=script_generator,
        script_generator_path=script_generator_path,
        emit_creative_trace=emit_creative_trace,
        ffmpeg_bin=ffmpeg_bin,
        ffprobe_bin=ffprobe_bin,
    )


def build_process_reel_event_sink() -> ProcessReelEventSink:
    """Construct the default terminal-event sink for ``process_reel``."""

    return SQLProcessReelEventSink()


def build_process_reel_runtime() -> ProcessReelRuntime:
    """Wire the default phase-one executor to the API process-reel persistence service."""

    context = orchestrator_service_context()
    return cast(
        ProcessReelRuntime,
        build_process_reel_persistence_service(
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
def mark_process_reel_package_qa_failed(
    execution_payload: dict[str, Any],
    failure_payload: dict[str, Any],
) -> dict[str, Any]:
    """Mark a reel as ``qa_failed`` when package-level QA blocks publish."""

    execution = _execution_from_payload(execution_payload)
    package_qa = failure_payload.get("package_qa")
    normalized_qa = dict(package_qa) if isinstance(package_qa, Mapping) else None
    return build_process_reel_runtime().mark_package_qa_failed(
        execution,
        error_message=str(failure_payload["error"]),
        package_qa=normalized_qa,
    )


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


def _creative_lint_failed(execution_payload: dict[str, Any]) -> bool:
    outputs = execution_payload.get("outputs", {})
    if not isinstance(outputs, dict):
        return False
    creative_payload = outputs.get("creative_planning", {})
    if not isinstance(creative_payload, dict):
        return False
    lint_payload = _mapping(creative_payload.get("script_lint"))
    return lint_payload.get("outcome") == "fail" or bool(creative_payload.get("creative_blocked"))


def _creative_lint_error(execution_payload: dict[str, Any]) -> str:
    outputs = execution_payload.get("outputs", {})
    creative_payload = outputs.get("creative_planning", {}) if isinstance(outputs, dict) else {}
    lint_payload = _mapping(
        creative_payload.get("script_lint") if isinstance(creative_payload, dict) else None
    )
    findings = lint_payload.get("findings")
    if isinstance(findings, list) and findings:
        first = _mapping(findings[0])
        code = _optional_text(first.get("code")) or "creative_lint_failed"
        message = _optional_text(first.get("message")) or "Creative script lint failed."
        return f"{code}: {message}"
    return "creative_lint_failed: Creative script lint failed."


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
        if _creative_lint_failed(execution):
            summary = mark_process_reel_failed(
                execution,
                failed_step="asset_resolution",
                error_message=_creative_lint_error(execution),
            )
            emit_process_reel_terminal_event(summary)
            return summary
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
        try:
            execution = execute_packaging(execution)
        except PackageQualityAssuranceError as exc:
            package_qa_payload = exc.package_qa.as_payload() if exc.package_qa else None
            summary = mark_process_reel_package_qa_failed(
                execution,
                {"error": str(exc), "package_qa": package_qa_payload},
            )
            emit_process_reel_terminal_event(summary)
            return summary
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


def _composition_manifest_from_creative_output(
    creative_output: Mapping[str, Any],
) -> dict[str, Any] | None:
    source_plan = _mapping(_mapping(creative_output.get("brief")).get("source_plan"))
    manifest = _mapping(source_plan.get("composition_manifest"))
    return manifest or None


def _layered_output_from_editing_output(
    editing_output: Mapping[str, Any],
) -> dict[str, Any]:
    width = _optional_float(editing_output.get("width"))
    height = _optional_float(editing_output.get("height"))
    duration = _optional_float(editing_output.get("duration_seconds"))
    output: dict[str, Any] = {
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "container": "mp4",
    }
    if width is not None:
        output["width"] = width
    if height is not None:
        output["height"] = height
    if duration is not None:
        output["duration_seconds"] = duration

    streams: list[dict[str, Any]] = []
    if width is not None and height is not None:
        video_stream: dict[str, Any] = {
            "codec_type": "video",
            "width": width,
            "height": height,
        }
        video_codec = _optional_text(editing_output.get("final_video_codec"))
        if video_codec:
            video_stream["codec_name"] = video_codec
        streams.append(video_stream)

    has_audio = bool(editing_output.get("has_audio_track"))
    audio_codec = _optional_text(editing_output.get("final_audio_codec"))
    if has_audio or audio_codec:
        audio_stream = {"codec_type": "audio"}
        if audio_codec:
            audio_stream["codec_name"] = audio_codec
        streams.append(audio_stream)
    if streams:
        output["streams"] = streams
    if not has_audio and not audio_codec:
        output["intentional_silence"] = bool(editing_output.get("intentional_silence"))
    return output


def _build_primary_asset_prompt(
    *,
    brief_payload: Mapping[str, Any],
    scene_plan: Any,
) -> Any:
    return compile_provider_prompt(
        brief_payload=brief_payload,
        scene_plan=scene_plan,
        provider=_PRIMARY_ASSET_PROVIDER,
        model=_PRIMARY_ASSET_MODEL,
        negative_prompt="text overlays, captions, watermarks",
    )


def _build_package_provenance(
    *,
    execution: ProcessReelExecution,
    creative_output: Mapping[str, Any],
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

    asset_id = _optional_text(asset_output.get("asset_id"))
    if asset_id is None:
        generation = _mapping(asset_output.get("generation"))
        asset_id = _optional_text(generation.get("asset_id"))
    asset_kind = _optional_text(asset_output.get("asset_kind")) or "generated_clip"
    media_type = _optional_text(asset_output.get("media_type")) or "video"
    source_type = _optional_text(asset_output.get("asset_source")) or "generated"
    generation = _mapping(asset_output.get("generation"))
    stored_content_hash = (
        _optional_text(asset_output.get("content_hash"))
        or _optional_text(generation.get("content_hash"))
        or _optional_text(asset_output.get("asset_key_hash"))
    )
    asset_lineage: dict[str, Any] = {
        "role": "source_clip",
        "asset_kind": asset_kind,
        "media_type": media_type,
        "source_type": source_type,
        "storage_uri": _required_text(
            asset_output.get("storage_uri"),
            field_name="asset_resolution.storage_uri",
        ),
        "used_as_component_role": "source_clip",
    }
    if asset_id is not None:
        asset_lineage["asset_id"] = asset_id
    if stored_content_hash is not None:
        asset_lineage["stored_content_hash"] = stored_content_hash
    assets = [asset_lineage]
    return {
        "editor_version": _required_text(
            editing_output.get("template_version"),
            field_name="editing.template_version",
        ),
        "assets": assets,
        "provider_jobs": [provider_payload],
        "script_generation": _script_generation_metadata(
            _mapping(creative_output.get("script_generation"))
            or _mapping(creative_output.get("script"))
        ),
        "script_lint": _mapping(creative_output.get("script_lint")),
        "scene_plan": _mapping(creative_output.get("scene_plan")),
        "prompt_trace": _mapping(_mapping(creative_output.get("compiled_prompt")).get("trace")),
        "source_run_id": execution.run_id,
        "asset_ids": _asset_ids(asset_output),
        "upstream_refs": {
            "timeline_uri": _required_text(
                editing_output.get("timeline_uri"),
                field_name="editing.timeline_uri",
            ),
        },
    }


def _script_generation_metadata(script_output: Mapping[str, Any]) -> dict[str, Any]:
    generator_path = _optional_text(script_output.get("generator_path")) or "unspecified"
    provider_name = _optional_text(script_output.get("provider_name")) or "unspecified"
    metadata = _mapping(script_output.get("generation_metadata")) or _mapping(
        script_output.get("metadata")
    )
    return {
        "generator_path": generator_path,
        "provider_name": provider_name,
        "metadata": metadata,
    }


def _script_lint_result(script_output: Mapping[str, Any]) -> dict[str, Any]:
    generation_metadata = _mapping(script_output.get("generation_metadata"))
    lint_result = _mapping(generation_metadata.get("creative_lint"))
    if lint_result:
        return lint_result
    return {"outcome": "pass", "passed": True, "findings": [], "checked_fields": []}


def _script_lint_failed(lint_result: Mapping[str, Any]) -> bool:
    return lint_result.get("outcome") == "fail" or lint_result.get("passed") is False


def _asset_ids(asset_output: Mapping[str, Any]) -> list[str]:
    asset_id = _optional_text(asset_output.get("asset_id"))
    if asset_id is None:
        generation = _mapping(asset_output.get("generation"))
        asset_id = _optional_text(generation.get("asset_id"))
    return [] if asset_id is None else [asset_id]


def _validate_duration_contract(
    *,
    requested_provider_duration_seconds: float | None,
    source_clip_duration_seconds: float,
    scene_plan_duration_seconds: float,
    final_rendered_duration_seconds: float,
    tolerance_seconds: float,
) -> dict[str, Any]:
    values: dict[str, float | None] = {
        "requested_provider_duration_seconds": (
            None
            if requested_provider_duration_seconds is None
            else float(requested_provider_duration_seconds)
        ),
        "source_clip_duration_seconds": float(source_clip_duration_seconds),
        "scene_plan_duration_seconds": float(scene_plan_duration_seconds),
        "final_rendered_duration_seconds": float(final_rendered_duration_seconds),
    }
    comparisons = (
        (
            "source_vs_requested",
            "source_clip_duration_seconds",
            "requested_provider_duration_seconds",
        ),
        ("source_vs_scene_plan", "source_clip_duration_seconds", "scene_plan_duration_seconds"),
        ("final_vs_scene_plan", "final_rendered_duration_seconds", "scene_plan_duration_seconds"),
        (
            "final_vs_requested",
            "final_rendered_duration_seconds",
            "requested_provider_duration_seconds",
        ),
    )
    mismatches: list[dict[str, Any]] = []
    for code, left_key, right_key in comparisons:
        left = values[left_key]
        right = values[right_key]
        if left is None or right is None:
            continue
        delta = abs(float(left) - float(right))
        if delta > tolerance_seconds:
            mismatches.append(
                {
                    "code": code,
                    "left_key": left_key,
                    "right_key": right_key,
                    "left_seconds": float(left),
                    "right_seconds": float(right),
                    "delta_seconds": delta,
                    "tolerance_seconds": tolerance_seconds,
                }
            )
    if mismatches:
        details = "; ".join(
            f"{item['code']} ({item['left_seconds']:.3f}s vs {item['right_seconds']:.3f}s, "
            f"delta={item['delta_seconds']:.3f}s > tol={tolerance_seconds:.3f}s)"
            for item in mismatches
        )
        raise ValueError(f"Duration contract mismatch: {details}")
    return {
        "status": "pass",
        "tolerance_seconds": tolerance_seconds,
        **values,
        "mismatches": [],
    }


def _build_timeline_render_trace(
    *,
    canonical_timeline: Mapping[str, Any],
    final_rendered_duration_seconds: float,
    source_asset_duration_seconds: float,
    duration_contract: Mapping[str, Any],
    cover_frame_timestamp_seconds: float,
) -> dict[str, Any]:
    scenes = canonical_timeline.get("scenes")
    overlays = canonical_timeline.get("overlays")
    audio_tracks = canonical_timeline.get("audio_tracks")
    return {
        "schema_version": "timeline_render_trace.v1",
        "timeline_id": canonical_timeline.get("timeline_id"),
        "scene_timings": list(scenes) if isinstance(scenes, list) else [],
        "overlay_timings": list(overlays) if isinstance(overlays, list) else [],
        "audio_timings": list(audio_tracks) if isinstance(audio_tracks, list) else [],
        "fade_durations": [
            {
                "track_id": track.get("track_id"),
                "fade_in_seconds": track.get("fade_in_seconds"),
                "fade_out_seconds": track.get("fade_out_seconds"),
            }
            for track in (audio_tracks if isinstance(audio_tracks, list) else [])
            if isinstance(track, Mapping)
        ],
        "final_render_duration_seconds": float(final_rendered_duration_seconds),
        "source_asset_duration_seconds": float(source_asset_duration_seconds),
        "duration_mismatch_checks": dict(duration_contract),
        "cover_timestamp_seconds": float(cover_frame_timestamp_seconds),
    }


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


def _role_metadata(role_payload: Mapping[str, Any]) -> dict[str, Any]:
    return _mapping(role_payload.get("metadata"))


def _role_storage_uri(role_payload: Mapping[str, Any]) -> str | None:
    metadata = _role_metadata(role_payload)
    return _optional_text(role_payload.get("storage_uri")) or _optional_text(metadata.get("storage_uri"))


def _role_media_label(role_payload: Mapping[str, Any]) -> str | None:
    metadata = _role_metadata(role_payload)
    return (
        _optional_text(role_payload.get("media_type"))
        or _optional_text(metadata.get("media_type"))
        or _optional_text(role_payload.get("content_type"))
        or _optional_text(metadata.get("content_type"))
    )


def _role_visual_media_type(role_payload: Mapping[str, Any]) -> str | None:
    media_label = (_role_media_label(role_payload) or "").lower()
    if media_label.startswith("video") or media_label.endswith("/mp4"):
        return "video"
    if media_label.startswith("image") or media_label.endswith("/png") or media_label.endswith("/jpeg"):
        return "image"
    storage_uri = (_role_storage_uri(role_payload) or "").lower()
    if storage_uri.endswith((".mp4", ".mov", ".webm")):
        return "video"
    if storage_uri.endswith((".png", ".jpg", ".jpeg", ".webp")):
        return "image"
    return None


def _role_visual_size(role_payload: Mapping[str, Any]) -> tuple[int, int] | None:
    metadata = _role_metadata(role_payload)
    visual = _mapping(metadata.get("visual"))
    width = _optional_int(role_payload.get("width") or metadata.get("width") or visual.get("width"))
    height = _optional_int(role_payload.get("height") or metadata.get("height") or visual.get("height"))
    if width is None or height is None or width <= 0 or height <= 0:
        return None
    return width, height


def _role_source_crop(role_payload: Mapping[str, Any], *, layer_role: str) -> CompositionCrop | None:
    storage_uri = (_role_storage_uri(role_payload) or "").lower()
    if "ratatouille_ingredients" in storage_uri:
        return CompositionCrop(x=620, y=150, width=460, height=820)
    if "tomato_cut" in storage_uri and layer_role not in {"background", "background_image", "environment"}:
        return CompositionCrop(x=0, y=0, width=800, height=800)
    size = _role_visual_size(role_payload)
    if size is None:
        return None
    width, height = size
    if "ratatouille_ingredients" in storage_uri and width >= 900 and height >= 900:
        crop_width = min(width - 1, max(480, int(width * 0.48)))
        return CompositionCrop(x=max(0, width - crop_width), y=0, width=crop_width, height=height)
    if layer_role not in {"background", "background_image", "environment"} and height / width > 2.0:
        crop_height = min(height, width)
        return CompositionCrop(x=0, y=0, width=width, height=crop_height)
    return None


def _role_has_baked_reference_marks(role_payload: Mapping[str, Any]) -> bool:
    storage_uri = (_role_storage_uri(role_payload) or "").lower()
    return "tomato_cut" in storage_uri


def _role_asset_id(role_payload: Mapping[str, Any], *, fallback: str) -> str:
    return _optional_text(role_payload.get("asset_id")) or fallback


def _role_asset_kind(role_payload: Mapping[str, Any], *, fallback: str) -> str:
    return _optional_text(role_payload.get("asset_kind")) or _optional_text(role_payload.get("pack_role")) or fallback


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
