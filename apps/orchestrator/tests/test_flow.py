from __future__ import annotations

import importlib
import subprocess
import uuid
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from content_lab_assets.providers.runway import (
    RunwayDownloadedAsset,
    RunwaySubmittedTask,
    RunwayTaskSnapshot,
)
from content_lab_assets.store import ProviderJobSnapshot, StoredRunwayGeneration
from content_lab_creative import (
    PageConstraints,
    PageMetadata,
    PersonaProfile,
    PolicyStateDocument,
)
from content_lab_storage import StorageRef, StoredObject

from content_lab_api.services import (
    InMemoryProcessReelRepository,
    ProcessReelExecution,
    ProcessReelQAResult,
    ProcessReelService,
)
from content_lab_core.types import Platform
from content_lab_orchestrator.flows import (
    DEFAULT_FLOW_NAME,
    example_flow,
    get_flow_definition,
    list_flow_names,
    process_reel,
    provider_job_sweeper,
)
from content_lab_orchestrator.flows.daily_reel_factory import (
    AppliedPolicy,
    BudgetGuardrailOutcome,
    OwnedPageSelection,
    ReelFamilyWorkUnit,
    ReelVariantWorkUnit,
)
from content_lab_orchestrator.flows.process_reel import (
    PhaseOnePlanningContext,
    PhaseOneProcessReelExecutor,
)
from content_lab_orchestrator.flows.provider_job_sweeper import (
    ProviderJobSweepCandidate,
    ProviderJobSweepResult,
)
from content_lab_worker.actors.runway import process_runway_asset

_SHA256_A = "sha256:" + ("a" * 64)
_SHA256_B = "sha256:" + ("b" * 64)
_SHA256_C = "sha256:" + ("c" * 64)
_SHA256_D = "sha256:" + ("d" * 64)
_SHA256_E = "sha256:" + ("e" * 64)

daily_reel_factory_module = importlib.import_module(
    "content_lab_orchestrator.flows.daily_reel_factory"
)
process_reel_flow_module = importlib.import_module("content_lab_orchestrator.flows.process_reel")
provider_job_sweeper_flow_module = importlib.import_module(
    "content_lab_orchestrator.flows.provider_job_sweeper"
)


class RecordingFactoryService:
    def __init__(self) -> None:
        self.created_families: list[ReelFamilyWorkUnit] = []
        self.created_reels: list[ReelVariantWorkUnit] = []

    def list_owned_pages(
        self,
        selector: str,
    ) -> list[OwnedPageSelection]:
        assert selector == "seed-page"
        return [
            OwnedPageSelection(
                org_id="org-1",
                page_id="page-1",
                display_name="Page One",
                platform="instagram",
                handle="@page-one",
                content_pillars=("proof", "faq"),
                metadata={"selection_seed": selector},
            )
        ]

    def load_global_policy(self, *, org_id: str) -> dict[str, object]:
        assert org_id == "org-1"
        return {
            "mode_ratios": {
                "explore": 0.4,
                "exploit": 0.3,
                "mutation": 0.2,
                "chaos": 0.1,
            },
            "budget": {"per_run_usd_limit": 10.0},
        }

    def load_page_policy(self, *, org_id: str, page_id: str) -> dict[str, object] | None:
        assert org_id == "org-1"
        assert page_id == "page-1"
        return {
            "mode_ratios": {
                "mutation": 0.5,
                "explore": 0.2,
            },
            "budget": {"per_run_usd_limit": 6.0},
        }

    def create_reel_family(
        self,
        *,
        page: OwnedPageSelection,
        family_name: str,
        mode: str,
        metadata: dict[str, object],
    ) -> ReelFamilyWorkUnit:
        family = ReelFamilyWorkUnit(
            family_id=f"family-{len(self.created_families) + 1}",
            org_id=page.org_id,
            page_id=page.page_id,
            name=family_name,
            mode=mode,
            metadata=dict(metadata),
        )
        self.created_families.append(family)
        return family

    def create_reel_variant(
        self,
        *,
        page: OwnedPageSelection,
        family: ReelFamilyWorkUnit,
        variant_label: str,
        metadata: dict[str, object],
    ) -> ReelVariantWorkUnit:
        reel = ReelVariantWorkUnit(
            reel_id=f"reel-{len(self.created_reels) + 1}",
            org_id=page.org_id,
            page_id=page.page_id,
            family_id=family.family_id,
            variant_label=variant_label,
            status="planning",
            metadata=dict(metadata),
        )
        self.created_reels.append(reel)
        return reel


class RecordingProcessReelExecutor:
    def __init__(self, *, qa_passes: bool = True) -> None:
        self._qa_passes = qa_passes
        self.calls: list[str] = []

    def create_creative_plan(self, execution: ProcessReelExecution) -> dict[str, object]:
        self.calls.append("creative_planning")
        return {"brief_id": f"brief-{execution.reel_id}"}

    def resolve_assets(self, execution: ProcessReelExecution) -> dict[str, object]:
        self.calls.append("asset_resolution")
        return {
            "asset_refs": [f"asset://{execution.reel_id}/primary"],
            "brief_id": execution.outputs["creative_planning"]["brief_id"],
        }

    def edit_reel(self, execution: ProcessReelExecution) -> dict[str, object]:
        self.calls.append("editing")
        return {"timeline_uri": f"memory://edits/{execution.reel_id}.json"}

    def run_qa(self, execution: ProcessReelExecution) -> ProcessReelQAResult:
        self.calls.append("qa")
        verdict = "pass" if self._qa_passes else "fail"
        return ProcessReelQAResult(
            passed=self._qa_passes,
            details={
                "verdict": verdict,
                "timeline_uri": execution.outputs["editing"]["timeline_uri"],
            },
        )

    def package_reel(self, execution: ProcessReelExecution) -> dict[str, object]:
        self.calls.append("packaging")
        return {
            "reel_id": execution.reel_id,
            "package_root_uri": f"memory://packages/{execution.reel_id}",
            "manifest_uri": f"memory://packages/{execution.reel_id}/package_manifest.json",
            "manifest": {
                "version": 1,
                "artifact_count": 5,
                "complete": True,
                "artifacts": [
                    {
                        "name": "final_video",
                        "filename": "final_video.mp4",
                        "checksum_sha256": _SHA256_A,
                    },
                    {
                        "name": "cover",
                        "filename": "cover.png",
                        "checksum_sha256": _SHA256_B,
                    },
                    {
                        "name": "caption_variants",
                        "filename": "caption_variants.txt",
                        "checksum_sha256": _SHA256_C,
                    },
                    {
                        "name": "posting_plan",
                        "filename": "posting_plan.json",
                        "checksum_sha256": _SHA256_D,
                    },
                    {
                        "name": "provenance",
                        "filename": "provenance.json",
                        "checksum_sha256": _SHA256_E,
                    },
                ],
            },
            "provenance": {
                "editor_version": "basic_vertical_v1",
                "assets": [
                    {
                        "role": "source_clip",
                        "storage_uri": f"memory://assets/{execution.reel_id}/source.mp4",
                    }
                ],
                "provider_jobs": [{"provider": "runway", "status": "succeeded"}],
            },
            "artifacts": [
                {
                    "name": "final_video",
                    "filename": "final_video.mp4",
                    "storage_uri": f"memory://packages/{execution.reel_id}/final_video.mp4",
                    "checksum_sha256": _SHA256_A,
                },
                {
                    "name": "cover",
                    "filename": "cover.png",
                    "storage_uri": f"memory://packages/{execution.reel_id}/cover.png",
                    "checksum_sha256": _SHA256_B,
                },
                {
                    "name": "caption_variants",
                    "filename": "caption_variants.txt",
                    "storage_uri": f"memory://packages/{execution.reel_id}/caption_variants.txt",
                    "checksum_sha256": _SHA256_C,
                },
                {
                    "name": "posting_plan",
                    "filename": "posting_plan.json",
                    "storage_uri": f"memory://packages/{execution.reel_id}/posting_plan.json",
                    "checksum_sha256": _SHA256_D,
                },
                {
                    "name": "provenance",
                    "filename": "provenance.json",
                    "storage_uri": f"memory://packages/{execution.reel_id}/provenance.json",
                    "checksum_sha256": _SHA256_E,
                },
                {
                    "name": "package_manifest",
                    "filename": "package_manifest.json",
                    "storage_uri": f"memory://packages/{execution.reel_id}/package_manifest.json",
                    "checksum_sha256": "sha256:" + ("f" * 64),
                },
            ],
        }


class FakeProcessReelEventSink:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def emit_terminal_event(self, summary: Mapping[str, Any]) -> dict[str, object]:
        event: dict[str, object] = {
            "event_type": "process_reel.package_ready"
            if summary["reel_status"] == "ready"
            else "process_reel.failed",
            "aggregate_id": str(summary["run_id"]),
            "emitted": True,
        }
        self.events.append(event | {"summary": dict(summary)})
        return event


class FakePlanningContextLoader:
    def load(self, execution: ProcessReelExecution) -> PhaseOnePlanningContext:
        _ = execution
        return PhaseOnePlanningContext(
            page_name="Northwind Fitness",
            page_metadata=PageMetadata(
                persona=PersonaProfile(
                    label="Coach-next-door",
                    audience="Busy professionals who want practical routines",
                    brand_tone=["direct", "optimistic"],
                    content_pillars=["mobility", "strength"],
                    differentiators=["simple progressions"],
                    primary_call_to_action="Follow for the next routine",
                ),
                constraints=PageConstraints(
                    required_disclosures=["Results vary"],
                    max_hashtags=4,
                ),
            ),
            family_name="Northwind proof mutation",
            family_mode="mutation",
            variant_label="A",
            brief_index=0,
            target_platforms=(Platform.INSTAGRAM,),
            timezone="UTC",
            locale="en",
            policy=PolicyStateDocument(),
            duration_seconds=5,
        )


class FakeRetrievedObject:
    def __init__(self, *, body: bytes, content_type: str | None) -> None:
        self.body = body
        self.content_type = content_type


class FakeStorageClient:
    def __init__(self) -> None:
        self.objects: dict[str, FakeRetrievedObject] = {}

    def put_object(
        self,
        *,
        ref: StorageRef | None = None,
        data: bytes,
        key: str | None = None,
        content_type: str | None = None,
        metadata: Mapping[str, str] | None = None,
        checksum_sha256: str | None = None,
    ) -> StoredObject:
        resolved_ref = ref or StorageRef(bucket="content-lab", key=cast(str, key))
        self.objects[resolved_ref.uri] = FakeRetrievedObject(body=data, content_type=content_type)
        return StoredObject(
            ref=resolved_ref,
            size_bytes=len(data),
            content_type=content_type,
            metadata={} if metadata is None else dict(metadata),
            checksum_sha256=checksum_sha256,
        )

    def get_object(self, *, storage_uri: str) -> FakeRetrievedObject:
        return self.objects[storage_uri]


class FakeRunwayStore:
    def __init__(self, state: StoredRunwayGeneration) -> None:
        self.state = state

    def load_generation(self, *, asset_id: uuid.UUID | str) -> StoredRunwayGeneration:
        assert str(self.state.asset_id) == str(asset_id)
        return self.state

    def mark_running(
        self,
        generation: StoredRunwayGeneration,
        *,
        external_ref: str | None,
        provider_status: str,
        provider_metadata: Mapping[str, Any] | None = None,
        task_result: Mapping[str, Any] | None = None,
    ) -> StoredRunwayGeneration:
        self.state = replace(
            generation,
            task_status="running",
            task_result=None if task_result is None else dict(task_result),
            provider_job=self._provider_job(
                generation, external_ref, provider_status, provider_metadata
            ),
        )
        return self.state

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
        self.state = replace(
            generation,
            task_status="retrying",
            task_result=result,
            provider_job=self._provider_job(
                generation, external_ref, provider_status, provider_metadata
            ),
        )
        return self.state

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
        self.state = replace(
            generation,
            asset_status="failed",
            asset_metadata=_merge_dicts(generation.asset_metadata, asset_metadata),
            task_status="failed",
            task_result=result,
            provider_job=self._provider_job(
                generation, external_ref, provider_status, provider_metadata
            ),
        )
        return self.state

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
        metadata = _merge_dicts(generation.asset_metadata, asset_metadata)
        metadata["content_hash"] = content_hash
        self.state = replace(
            generation,
            asset_status="ready",
            storage_uri=storage_uri,
            asset_metadata=metadata,
            task_status="succeeded",
            task_result=None if task_result is None else dict(task_result),
            provider_job=self._provider_job(
                generation, external_ref, provider_status, provider_metadata
            ),
        )
        return self.state

    @staticmethod
    def _provider_job(
        generation: StoredRunwayGeneration,
        external_ref: str | None,
        provider_status: str,
        provider_metadata: Mapping[str, Any] | None,
    ) -> ProviderJobSnapshot | None:
        if external_ref is None:
            return generation.provider_job
        return ProviderJobSnapshot(
            id=uuid.uuid4(),
            org_id=generation.org_id,
            provider="runway",
            external_ref=external_ref,
            task_id=generation.task_id,
            status=provider_status,
            metadata={} if provider_metadata is None else dict(provider_metadata),
        )


class FakeRunwayClient:
    def __init__(self, *, clip_bytes: bytes) -> None:
        self.clip_bytes = clip_bytes
        self.submit_calls = 0
        self.polled_refs: list[str] = []

    def submit_generation(
        self,
        *,
        task_payload: Mapping[str, Any],
        canonical_params: Mapping[str, Any],
        idempotency_key: str,
    ) -> RunwaySubmittedTask:
        self.submit_calls += 1
        assert task_payload["provider_submission"]["provider"] == "runway"
        assert canonical_params["model"] == "gen4.5"
        assert idempotency_key.startswith("asset.generate:")
        return RunwaySubmittedTask(id="rwy-task-123", raw_response={"id": "rwy-task-123"})

    def get_task(self, external_ref: str) -> RunwayTaskSnapshot:
        self.polled_refs.append(external_ref)
        if len(self.polled_refs) == 1:
            return RunwayTaskSnapshot(id=external_ref, status="RUNNING")
        return RunwayTaskSnapshot(
            id=external_ref,
            status="SUCCEEDED",
            output=("https://cdn.runwayml.com/out/generated.mp4",),
        )

    def download_output(self, task: RunwayTaskSnapshot) -> RunwayDownloadedAsset:
        assert task.is_success
        return RunwayDownloadedAsset(
            url="https://cdn.runwayml.com/out/generated.mp4",
            body=self.clip_bytes,
            content_type="video/mp4",
        )


class FakeProcessReelAssetResolver:
    def __init__(self, *, storage_client: FakeStorageClient, clip_bytes: bytes) -> None:
        self.storage_client = storage_client
        self.runway_client = FakeRunwayClient(clip_bytes=clip_bytes)
        self.calls = 0

    def resolve_primary_asset(
        self,
        execution: ProcessReelExecution,
        *,
        creative_output: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.calls += 1
        request_payload = cast(dict[str, Any], creative_output["primary_asset_request"])
        asset_id = uuid.uuid4()
        generation = StoredRunwayGeneration(
            asset_id=asset_id,
            org_id=uuid.uuid4(),
            asset_class="clip",
            asset_status="staged",
            asset_source="runway",
            storage_uri=f"s3://content-lab/assets/raw/{asset_id}/source.bin",
            asset_key="asset-key",
            asset_key_hash="asset-key-hash",
            canonical_params={
                "asset_class": "clip",
                "provider": "runway",
                "model": "gen4.5",
                "prompt": request_payload["prompt"],
                "duration_seconds": request_payload["duration_seconds"],
                "ratio": request_payload["ratio"],
            },
            task_id=uuid.uuid4(),
            task_type="asset.generate",
            task_status="queued",
            task_idempotency_key="asset.generate:asset-key-hash",
            task_payload={
                "request": request_payload,
                "provider_submission": {
                    "provider": "runway",
                    "model": "gen4.5",
                    "asset_class": "clip",
                    "external_ref": "runway-gen45:asset-key-hash",
                    "status": "submitted",
                },
            },
        )
        store = FakeRunwayStore(generation)
        generation_summary = process_runway_asset(
            asset_id=generation.asset_id,
            store=store,
            provider_client=self.runway_client,
            storage_client=self.storage_client,
            max_polls=3,
            poll_interval_seconds=0,
        )
        return {
            "decision": "generate",
            "asset_id": str(asset_id),
            "asset_key": "asset-key",
            "asset_key_hash": "asset-key-hash",
            "asset_class": "clip",
            "provider": "runway",
            "model": "gen4.5",
            "canonical_params": dict(generation.canonical_params),
            "provenance": {"source": "asset_registry", "resolution": "generate"},
            "policy": {},
            "provider_job": {
                "provider": "runway",
                **cast(dict[str, Any], generation_summary["provider_job"]),
            },
            "storage_uri": cast(str, generation_summary["storage_uri"]),
            "generation": generation_summary,
        }


class FailingProcessReelAssetResolver:
    def resolve_primary_asset(
        self,
        execution: ProcessReelExecution,
        *,
        creative_output: Mapping[str, Any],
    ) -> dict[str, Any]:
        _ = execution, creative_output
        raise RuntimeError("runway generation failed")


def _merge_dicts(
    left: Mapping[str, Any] | None,
    right: Mapping[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(left or {})
    if right is not None:
        merged.update(dict(right))
    return merged


def _build_fixture_clip_bytes(tmp_path: Path) -> bytes:
    clip_path = tmp_path / "provider-output.mp4"
    completed = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=720x1280:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:sample_rate=48000",
            "-t",
            "5.000",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ac",
            "2",
            "-ar",
            "48000",
            str(clip_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return clip_path.read_bytes()


class RecordingProviderJobSweeperRuntime:
    def __init__(
        self,
        *,
        candidates: tuple[ProviderJobSweepCandidate, ...],
        results: dict[str, list[ProviderJobSweepResult]],
    ) -> None:
        self._candidates = candidates
        self._results = {key: list(value) for key, value in results.items()}
        self.limits: list[int] = []
        self.reconciled_job_ids: list[str] = []

    def list_stale_jobs(
        self,
        *,
        now: object | None = None,
        limit: int = 50,
    ) -> tuple[ProviderJobSweepCandidate, ...]:
        _ = now
        self.limits.append(limit)
        return self._candidates[:limit]

    def reconcile_job(self, candidate: ProviderJobSweepCandidate) -> ProviderJobSweepResult:
        self.reconciled_job_ids.append(candidate.provider_job_id)
        sequence = self._results[candidate.provider_job_id]
        return sequence.pop(0)


def _install_service(
    monkeypatch: pytest.MonkeyPatch,
    *,
    qa_passes: bool = True,
) -> tuple[ProcessReelService, InMemoryProcessReelRepository, RecordingProcessReelExecutor]:
    repository = InMemoryProcessReelRepository()
    repository.seed_reel(
        reel_id="reel-42",
        org_id="org-1",
        page_id="page-7",
        reel_family_id="family-9",
    )
    executor = RecordingProcessReelExecutor(qa_passes=qa_passes)
    service = ProcessReelService(repository=repository, executor=executor)
    monkeypatch.setattr(process_reel_flow_module, "build_process_reel_runtime", lambda: service)
    return service, repository, executor


def _install_phase_one_service(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tmp_path: Path,
    asset_resolver: object | None = None,
) -> tuple[
    ProcessReelService,
    InMemoryProcessReelRepository,
    FakeProcessReelEventSink,
    FakeStorageClient,
    FakeProcessReelAssetResolver | None,
]:
    repository = InMemoryProcessReelRepository()
    repository.seed_reel(
        reel_id="reel-42",
        org_id="org-1",
        page_id="page-7",
        reel_family_id="family-9",
    )
    storage_client = FakeStorageClient()
    clip_bytes = _build_fixture_clip_bytes(tmp_path)
    resolved_asset_resolver = (
        cast(FakeProcessReelAssetResolver, asset_resolver)
        if asset_resolver is not None
        else FakeProcessReelAssetResolver(storage_client=storage_client, clip_bytes=clip_bytes)
    )
    executor = PhaseOneProcessReelExecutor(
        planning_context_loader=FakePlanningContextLoader(),
        asset_resolver=cast(Any, resolved_asset_resolver),
        storage_client=storage_client,
        package_layout=process_reel_flow_module.CanonicalStorageLayout(bucket="content-lab"),
        temp_root=tmp_path / "phase-one",
    )
    service = ProcessReelService(repository=repository, executor=executor)
    event_sink = FakeProcessReelEventSink()
    monkeypatch.setattr(process_reel_flow_module, "build_process_reel_runtime", lambda: service)
    monkeypatch.setattr(
        process_reel_flow_module, "build_process_reel_event_sink", lambda: event_sink
    )
    return (
        service,
        repository,
        event_sink,
        storage_client,
        (
            resolved_asset_resolver
            if isinstance(resolved_asset_resolver, FakeProcessReelAssetResolver)
            else None
        ),
    )


def _result_payload(value: object) -> dict[str, object]:
    return cast(dict[str, object], value)


def _dispatch_payloads(result: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], result["dispatches"])


def test_example_flow_alias_uses_default_phase1_flow() -> None:
    result = _result_payload(example_flow("ryan"))

    assert result["status"] == "scheduled"
    assert result["page_count"] == 1
    assert result["family_count"] == 2
    assert result["reel_count"] == 4


def test_flow_discovery_lists_phase1_flows() -> None:
    assert list_flow_names() == ("daily_reel_factory", "process_reel", "provider_job_sweeper")


def test_default_flow_registration_points_at_daily_factory() -> None:
    result = _result_payload(get_flow_definition(DEFAULT_FLOW_NAME).entrypoint(name="ryan"))

    assert result["status"] == "scheduled"
    assert result["dispatch_count"] == 4


def test_daily_reel_factory_creates_work_units_and_dispatches_reels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RecordingFactoryService()
    process_calls: list[str] = []

    class EnforcingGuardrails:
        def check(
            self,
            *,
            page: OwnedPageSelection,
            policy: AppliedPolicy,
            reels: tuple[ReelVariantWorkUnit, ...],
        ) -> BudgetGuardrailOutcome:
            assert page.page_id == "page-1"
            assert policy.effective_policy["budget"] == {"per_run_usd_limit": 6.0}
            assert len(reels) == 4
            return BudgetGuardrailOutcome(
                allowed=True,
                status="enforced",
                detail="budget-ok",
            )

    monkeypatch.setattr(
        daily_reel_factory_module,
        "get_daily_reel_factory_service",
        lambda: service,
    )
    monkeypatch.setattr(
        daily_reel_factory_module,
        "get_budget_guardrail_checker",
        lambda: EnforcingGuardrails(),
    )

    def _record_process_call(reel: ReelVariantWorkUnit) -> str:
        process_calls.append(reel.reel_id)
        return f"processed {reel.reel_id}"

    monkeypatch.setattr(
        daily_reel_factory_module,
        "run_process_reel",
        _record_process_call,
    )

    result = _result_payload(daily_reel_factory_module.daily_reel_factory(name="seed-page"))

    assert [family.mode for family in service.created_families] == ["mutation", "exploit"]
    assert [family.name for family in service.created_families] == [
        "Page One proof mutation",
        "Page One faq exploit",
    ]
    assert [reel.variant_label for reel in service.created_reels] == ["A", "B", "A", "B"]
    assert process_calls == ["reel-1", "reel-2", "reel-3", "reel-4"]

    assert result["status"] == "scheduled"
    assert result["page_count"] == 1
    assert result["family_count"] == 2
    assert result["reel_count"] == 4
    assert result["dispatch_count"] == 4
    assert result["budget_guardrails"] == {
        "status": "enforced",
        "checked_pages": 1,
        "blocked_pages": 0,
    }


def test_daily_reel_factory_skips_dispatch_when_guardrails_block_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RecordingFactoryService()

    class BlockingGuardrails:
        def check(
            self,
            *,
            page: OwnedPageSelection,
            policy: AppliedPolicy,
            reels: tuple[ReelVariantWorkUnit, ...],
        ) -> BudgetGuardrailOutcome:
            _ = page, policy, reels
            return BudgetGuardrailOutcome(
                allowed=False,
                status="stubbed",
                detail="budget service pending",
            )

    monkeypatch.setattr(
        daily_reel_factory_module,
        "get_daily_reel_factory_service",
        lambda: service,
    )
    monkeypatch.setattr(
        daily_reel_factory_module,
        "get_budget_guardrail_checker",
        lambda: BlockingGuardrails(),
    )
    monkeypatch.setattr(
        daily_reel_factory_module,
        "run_process_reel",
        lambda reel: (_ for _ in ()).throw(
            AssertionError(f"process_reel should not run for {reel.reel_id}")
        ),
    )

    result = _result_payload(daily_reel_factory_module.daily_reel_factory(name="seed-page"))

    assert result["status"] == "guardrail_blocked"
    assert result["dispatch_count"] == 0
    assert result["budget_guardrails"] == {
        "status": "stubbed",
        "checked_pages": 1,
        "blocked_pages": 1,
    }
    assert [dispatch["status"] for dispatch in _dispatch_payloads(result)] == [
        "skipped",
        "skipped",
        "skipped",
        "skipped",
    ]


def test_process_reel_flow_persists_success_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _, repository, executor = _install_service(monkeypatch, qa_passes=True)

    result = process_reel(reel_id="reel-42", dry_run=True)

    assert executor.calls == [
        "creative_planning",
        "asset_resolution",
        "editing",
        "qa",
        "packaging",
    ]
    assert result["reel_status"] == "ready"
    assert result["run_status"] == "succeeded"
    assert result["step_outputs"]["packaging"]["package_root_uri"] == "memory://packages/reel-42"
    assert result["step_outputs"]["packaging"]["package_qa"]["passed"] is True

    run_id = result["run_id"]
    assert repository.reels["reel-42"].status == "ready"
    assert repository.runs[run_id].status == "succeeded"
    assert result["task_statuses"] == {
        "asset_resolution": "succeeded",
        "creative_planning": "succeeded",
        "editing": "succeeded",
        "packaging": "succeeded",
        "process_reel": "succeeded",
        "qa": "succeeded",
    }


def test_process_reel_flow_marks_qa_failure_and_skips_packaging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, repository, executor = _install_service(monkeypatch, qa_passes=False)

    result = process_reel(reel_id="reel-42", dry_run=False)

    assert executor.calls == [
        "creative_planning",
        "asset_resolution",
        "editing",
        "qa",
    ]
    assert result["reel_status"] == "qa_failed"
    assert result["run_status"] == "failed"

    run_id = result["run_id"]
    assert repository.reels["reel-42"].status == "qa_failed"
    assert repository.tasks[(run_id, "qa")].status == "failed"
    assert repository.tasks[(run_id, "packaging")].status == "skipped"
    assert result["task_statuses"] == {
        "asset_resolution": "succeeded",
        "creative_planning": "succeeded",
        "editing": "succeeded",
        "packaging": "skipped",
        "process_reel": "failed",
        "qa": "failed",
    }


def test_process_reel_flow_runs_full_phase_one_package_generation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, repository, event_sink, storage_client, asset_resolver = _install_phase_one_service(
        monkeypatch,
        tmp_path=tmp_path,
    )

    result = process_reel(reel_id="reel-42", dry_run=False)

    assert asset_resolver is not None
    assert asset_resolver.calls == 1
    assert asset_resolver.runway_client.submit_calls == 1
    assert asset_resolver.runway_client.polled_refs == ["rwy-task-123", "rwy-task-123"]
    assert result["reel_status"] == "ready"
    assert result["run_status"] == "succeeded"
    assert result["package"]["manifest"]["complete"] is True
    assert result["package"]["package_qa"]["passed"] is True
    assert result["step_outputs"]["packaging"]["ready_for_publish"] is True

    run_id = result["run_id"]
    assert repository.reels["reel-42"].status == "ready"
    assert repository.runs[run_id].status == "succeeded"
    assert result["task_statuses"] == {
        "asset_resolution": "succeeded",
        "creative_planning": "succeeded",
        "editing": "succeeded",
        "packaging": "succeeded",
        "process_reel": "succeeded",
        "qa": "succeeded",
    }
    assert len(event_sink.events) == 1
    assert event_sink.events[0]["event_type"] == "process_reel.package_ready"
    stored_uris = set(storage_client.objects)
    assert (
        f"s3://content-lab/reels/packages/{result['reel_id']}/package_manifest.json" in stored_uris
    )
    assert f"s3://content-lab/reels/packages/{result['reel_id']}/final_video.mp4" in stored_uris


def test_process_reel_flow_emits_failure_event_and_stops_before_ready(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, repository, event_sink, _, _ = _install_phase_one_service(
        monkeypatch,
        tmp_path=tmp_path,
        asset_resolver=FailingProcessReelAssetResolver(),
    )

    with pytest.raises(RuntimeError, match="runway generation failed"):
        process_reel(reel_id="reel-42", dry_run=False)

    run_id = next(iter(repository.runs))
    assert repository.runs[run_id].status == "failed"
    assert repository.tasks[(run_id, "asset_resolution")].status == "failed"
    assert repository.tasks[(run_id, "editing")].status == "skipped"
    assert repository.tasks[(run_id, "qa")].status == "skipped"
    assert repository.tasks[(run_id, "packaging")].status == "skipped"
    assert repository.reels["reel-42"].status == "generating"
    assert len(event_sink.events) == 1
    assert event_sink.events[0]["event_type"] == "process_reel.failed"
    summary = cast(dict[str, object], event_sink.events[0]["summary"])
    assert summary["run_status"] == "failed"
    assert summary["error"] == "runway generation failed"


def test_provider_job_sweeper_reconciles_stale_jobs_and_counts_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = (
        ProviderJobSweepCandidate(
            provider_job_id="provider-job-1",
            org_id="org-1",
            provider="runway",
            external_ref="runway-gen45:hash-1",
            provider_job_status="running",
            task_id="task-1",
            task_status="running",
            asset_id="asset-1",
            asset_status="staged",
            last_updated_at="2026-03-25T09:00:00+00:00",
            stale_for_seconds=5400,
        ),
        ProviderJobSweepCandidate(
            provider_job_id="provider-job-2",
            org_id="org-1",
            provider="runway",
            external_ref="runway-gen45:hash-2",
            provider_job_status="polling_failed",
            task_id="task-2",
            task_status="retrying",
            asset_id="asset-2",
            asset_status="staged",
            last_updated_at="2026-03-25T08:30:00+00:00",
            stale_for_seconds=7200,
        ),
    )
    runtime = RecordingProviderJobSweeperRuntime(
        candidates=candidates,
        results={
            "provider-job-1": [
                ProviderJobSweepResult(
                    provider_job_id="provider-job-1",
                    external_ref="runway-gen45:hash-1",
                    provider="runway",
                    reconciliation_status="repaired",
                    provider_job_status="succeeded",
                    task_status="succeeded",
                    asset_status="ready",
                    signal_event_type="provider_job.repaired",
                    signal_emitted=True,
                )
            ],
            "provider-job-2": [
                ProviderJobSweepResult(
                    provider_job_id="provider-job-2",
                    external_ref="runway-gen45:hash-2",
                    provider="runway",
                    reconciliation_status="retrying",
                    provider_job_status="running",
                    task_status="retrying",
                    asset_status="staged",
                    detail="Runway task runway-gen45:hash-2 is still running",
                    signal_event_type="provider_job.reconciliation_failed",
                    signal_emitted=True,
                )
            ],
        },
    )
    monkeypatch.setattr(
        provider_job_sweeper_flow_module,
        "build_provider_job_sweeper_runtime",
        lambda: runtime,
    )

    result = provider_job_sweeper(limit=10)

    assert runtime.limits == [10]
    assert runtime.reconciled_job_ids == ["provider-job-1", "provider-job-2"]
    assert result["status"] == "completed"
    assert result["counts"] == {
        "stale": 2,
        "repaired": 1,
        "failed": 0,
        "retrying": 1,
        "already_finalized": 0,
        "skipped": 0,
        "signals_emitted": 2,
    }
    assert [item["reconciliation_status"] for item in result["results"]] == [
        "repaired",
        "retrying",
    ]


def test_provider_job_sweeper_is_idempotent_when_a_revisited_job_is_already_finalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = ProviderJobSweepCandidate(
        provider_job_id="provider-job-3",
        org_id="org-1",
        provider="runway",
        external_ref="runway-gen45:hash-3",
        provider_job_status="running",
        task_id="task-3",
        task_status="running",
        asset_id="asset-3",
        asset_status="staged",
        last_updated_at="2026-03-25T07:30:00+00:00",
        stale_for_seconds=10800,
    )
    runtime = RecordingProviderJobSweeperRuntime(
        candidates=(candidate,),
        results={
            "provider-job-3": [
                ProviderJobSweepResult(
                    provider_job_id="provider-job-3",
                    external_ref="runway-gen45:hash-3",
                    provider="runway",
                    reconciliation_status="already_finalized",
                    provider_job_status="succeeded",
                    task_status="succeeded",
                    asset_status="ready",
                    signal_event_type="provider_job.repaired",
                    signal_emitted=True,
                ),
                ProviderJobSweepResult(
                    provider_job_id="provider-job-3",
                    external_ref="runway-gen45:hash-3",
                    provider="runway",
                    reconciliation_status="already_finalized",
                    provider_job_status="succeeded",
                    task_status="succeeded",
                    asset_status="ready",
                    signal_event_type="provider_job.repaired",
                    signal_emitted=False,
                ),
            ]
        },
    )
    monkeypatch.setattr(
        provider_job_sweeper_flow_module,
        "build_provider_job_sweeper_runtime",
        lambda: runtime,
    )

    first_result = provider_job_sweeper()
    second_result = provider_job_sweeper()

    assert runtime.reconciled_job_ids == ["provider-job-3", "provider-job-3"]
    assert first_result["counts"]["already_finalized"] == 1
    assert first_result["counts"]["signals_emitted"] == 1
    assert second_result["counts"]["already_finalized"] == 1
    assert second_result["counts"]["signals_emitted"] == 0
