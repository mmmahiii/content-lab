from __future__ import annotations

import importlib
from typing import cast

import pytest
from botocore.exceptions import ClientError
from content_lab_storage.client import RetrievedObject, StoredObject
from content_lab_storage.integrity import S3ObjectIntegrityVerifier
from content_lab_storage.refs import StorageRef

from content_lab_api.services import (
    InMemoryProcessReelRepository,
    ProcessReelExecution,
    ProcessReelQAResult,
    ProcessReelService,
)
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
from content_lab_orchestrator.flows.provider_job_sweeper import (
    ProviderJobSweepCandidate,
    ProviderJobSweepResult,
)
from content_lab_orchestrator.flows.storage_integrity_check import (
    AssetIntegrityCandidate,
    ReelPackageArtifactCandidate,
    ReelPackageIntegrityCandidate,
    StorageIntegrityCheckResult,
)

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
storage_integrity_flow_module = importlib.import_module(
    "content_lab_orchestrator.flows.storage_integrity_check"
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


class RecordingStorageIntegrityRuntime:
    def __init__(
        self,
        *,
        asset_candidates: tuple[AssetIntegrityCandidate, ...],
        package_candidates: tuple[ReelPackageIntegrityCandidate, ...],
        asset_results: dict[str, list[StorageIntegrityCheckResult]],
        package_results: dict[str, list[StorageIntegrityCheckResult]],
    ) -> None:
        self._asset_candidates = asset_candidates
        self._package_candidates = package_candidates
        self._asset_results = {key: list(value) for key, value in asset_results.items()}
        self._package_results = {key: list(value) for key, value in package_results.items()}
        self.asset_limits: list[int] = []
        self.package_limits: list[int] = []
        self.reconciled_asset_ids: list[str] = []
        self.reconciled_reel_ids: list[str] = []

    def list_recent_assets(
        self,
        *,
        limit: int = 50,
    ) -> tuple[AssetIntegrityCandidate, ...]:
        self.asset_limits.append(limit)
        return self._asset_candidates[:limit]

    def list_recent_reel_packages(
        self,
        *,
        limit: int = 25,
    ) -> tuple[ReelPackageIntegrityCandidate, ...]:
        self.package_limits.append(limit)
        return self._package_candidates[:limit]

    def reconcile_asset(self, candidate: AssetIntegrityCandidate) -> StorageIntegrityCheckResult:
        self.reconciled_asset_ids.append(candidate.asset_id)
        return self._asset_results[candidate.asset_id].pop(0)

    def reconcile_reel_package(
        self,
        candidate: ReelPackageIntegrityCandidate,
    ) -> StorageIntegrityCheckResult:
        self.reconciled_reel_ids.append(candidate.reel_id)
        return self._package_results[candidate.reel_id].pop(0)


class FakeStorageClient:
    def __init__(
        self,
        *,
        head_error: Exception | None = None,
        get_error: Exception | None = None,
        head_object: StoredObject | None = None,
        retrieved_object: RetrievedObject | None = None,
    ) -> None:
        self._head_error = head_error
        self._get_error = get_error
        self._head_object = head_object
        self._retrieved_object = retrieved_object

    def head_object(self, *, storage_uri: str) -> StoredObject:
        assert storage_uri.startswith("s3://")
        if self._head_error is not None:
            raise self._head_error
        assert self._head_object is not None
        return self._head_object

    def get_object(self, *, storage_uri: str) -> RetrievedObject:
        assert storage_uri.startswith("s3://")
        if self._get_error is not None:
            raise self._get_error
        assert self._retrieved_object is not None
        return self._retrieved_object


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
    assert list_flow_names() == (
        "daily_reel_factory",
        "process_reel",
        "provider_job_sweeper",
        "storage_integrity_check",
    )


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


def test_storage_object_integrity_verifier_marks_missing_objects() -> None:
    missing_error = ClientError({"Error": {"Code": "NoSuchKey"}}, "HeadObject")
    verifier = S3ObjectIntegrityVerifier(FakeStorageClient(head_error=missing_error))

    result = verifier.verify_object(
        storage_uri="s3://content-lab/assets/missing.mp4",
        expected_checksum_sha256=_SHA256_A,
        verify_checksum=True,
    )

    assert result.status == "missing"
    assert result.exists is False
    assert result.expected_checksum_sha256 == _SHA256_A
    assert result.actual_checksum_sha256 is None


def test_storage_object_integrity_verifier_detects_checksum_mismatch() -> None:
    ref = StorageRef(bucket="content-lab", key="packages/reel-1/final_video.mp4")
    verifier = S3ObjectIntegrityVerifier(
        FakeStorageClient(
            head_object=StoredObject(
                ref=ref,
                size_bytes=3,
                metadata={"checksum-sha256": _SHA256_A},
                checksum_sha256=_SHA256_A,
            ),
            retrieved_object=RetrievedObject(
                ref=ref,
                size_bytes=3,
                metadata={"checksum-sha256": _SHA256_A},
                checksum_sha256=_SHA256_A,
                body=b"bad",
            ),
        )
    )

    result = verifier.verify_object(
        storage_uri=ref.uri,
        expected_checksum_sha256=_SHA256_A,
        verify_checksum=True,
    )

    assert result.status == "corrupt"
    assert result.exists is True
    assert result.expected_checksum_sha256 == _SHA256_A
    assert result.actual_checksum_sha256 != _SHA256_A


def test_storage_integrity_check_flow_records_missing_assets_and_corrupt_packages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_candidate = AssetIntegrityCandidate(
        asset_id="asset-1",
        org_id="org-1",
        asset_class="video",
        storage_uri="s3://content-lab/assets/asset-1/video.mp4",
        expected_checksum_sha256=_SHA256_A,
        created_at="2026-03-26T12:00:00+00:00",
    )
    package_candidate = ReelPackageIntegrityCandidate(
        reel_id="reel-1",
        org_id="org-1",
        reel_status="ready",
        package_root_uri="s3://content-lab/packages/reel-1",
        updated_at="2026-03-26T13:00:00+00:00",
        artifacts=(
            ReelPackageArtifactCandidate(
                name="final_video",
                storage_uri="s3://content-lab/packages/reel-1/final_video.mp4",
                expected_checksum_sha256=_SHA256_A,
            ),
            ReelPackageArtifactCandidate(
                name="cover",
                storage_uri="s3://content-lab/packages/reel-1/cover.png",
                expected_checksum_sha256=_SHA256_B,
            ),
        ),
    )
    runtime = RecordingStorageIntegrityRuntime(
        asset_candidates=(asset_candidate,),
        package_candidates=(package_candidate,),
        asset_results={
            "asset-1": [
                StorageIntegrityCheckResult(
                    org_id="org-1",
                    check_kind="asset_object",
                    status="missing",
                    asset_id="asset-1",
                    check_id="check-asset-1",
                    alert_emitted=True,
                    checked_object_count=1,
                    issue_count=1,
                    detail={
                        "asset": {"asset_id": "asset-1"},
                        "objects": [{"status": "missing"}],
                    },
                )
            ]
        },
        package_results={
            "reel-1": [
                StorageIntegrityCheckResult(
                    org_id="org-1",
                    check_kind="reel_package",
                    status="corrupt",
                    reel_id="reel-1",
                    check_id="check-reel-1",
                    alert_emitted=True,
                    checked_object_count=2,
                    issue_count=2,
                    detail={
                        "package": {"reel_id": "reel-1"},
                        "objects": [
                            {"artifact_name": "final_video", "status": "corrupt"},
                            {"artifact_name": "posting_plan", "status": "missing"},
                        ],
                    },
                )
            ]
        },
    )
    monkeypatch.setattr(
        storage_integrity_flow_module,
        "build_storage_integrity_runtime",
        lambda: runtime,
    )

    result = storage_integrity_flow_module.storage_integrity_check(asset_limit=5, package_limit=5)

    assert runtime.asset_limits == [5]
    assert runtime.package_limits == [5]
    assert runtime.reconciled_asset_ids == ["asset-1"]
    assert runtime.reconciled_reel_ids == ["reel-1"]
    assert result["status"] == "completed"
    assert result["counts"] == {
        "assets_scanned": 1,
        "packages_scanned": 1,
        "healthy": 0,
        "missing": 1,
        "corrupt": 1,
        "skipped": 0,
        "alerts_emitted": 2,
        "records_written": 2,
    }
    assert [item["status"] for item in result["results"]] == ["missing", "corrupt"]
