from __future__ import annotations

import importlib
from copy import deepcopy
from typing import cast

import pytest

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
    OperatorSummaryEvent,
    OwnedPageSelection,
    PersistedRunSummary,
    ReelFamilyWorkUnit,
    ReelVariantWorkUnit,
)
from content_lab_orchestrator.flows.provider_job_sweeper import (
    ProviderJobSweepCandidate,
    ProviderJobSweepResult,
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


class RecordingFactoryService:
    def __init__(
        self,
        *,
        pages: list[OwnedPageSelection] | None = None,
        global_policies: dict[str, dict[str, object]] | None = None,
        page_policies: dict[str, dict[str, object] | None] | None = None,
    ) -> None:
        self._pages = pages or [
            OwnedPageSelection(
                org_id="org-1",
                page_id="page-1",
                display_name="Page One",
                platform="instagram",
                handle="@page-one",
                content_pillars=("proof", "faq"),
                metadata={"selection_seed": "seed-page"},
            )
        ]
        self._global_policies = global_policies or {
            "org-1": {
                "mode_ratios": {
                    "explore": 0.4,
                    "exploit": 0.3,
                    "mutation": 0.2,
                    "chaos": 0.1,
                },
                "budget": {"per_run_usd_limit": 10.0},
            }
        }
        self._page_policies = page_policies or {
            "page-1": {
                "mode_ratios": {
                    "mutation": 0.5,
                    "explore": 0.2,
                },
                "budget": {"per_run_usd_limit": 6.0},
            }
        }
        self.created_families: list[ReelFamilyWorkUnit] = []
        self.created_reels: list[ReelVariantWorkUnit] = []
        self.persisted_summaries: list[PersistedRunSummary] = []
        self.operator_events: list[OperatorSummaryEvent] = []

    def list_owned_pages(
        self,
        selector: str,
    ) -> list[OwnedPageSelection]:
        assert selector == "seed-page"
        return list(self._pages)

    def load_global_policy(self, *, org_id: str) -> dict[str, object]:
        return deepcopy(self._global_policies[org_id])

    def load_page_policy(self, *, org_id: str, page_id: str) -> dict[str, object] | None:
        _ = org_id
        policy = self._page_policies.get(page_id)
        return None if policy is None else deepcopy(policy)

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

    def persist_run_summary(
        self,
        *,
        selector: str,
        summary: dict[str, object],
    ) -> PersistedRunSummary:
        persisted = PersistedRunSummary(
            summary_id=f"summary-{len(self.persisted_summaries) + 1}",
            selector=selector,
            payload=deepcopy(summary),
        )
        self.persisted_summaries.append(persisted)
        return persisted

    def emit_operator_summary_event(
        self,
        *,
        selector: str,
        summary: PersistedRunSummary,
    ) -> OperatorSummaryEvent:
        event = OperatorSummaryEvent(
            event_id=f"event-{len(self.operator_events) + 1}",
            aggregate_type="daily_reel_factory_run_summary",
            aggregate_id=summary.summary_id,
            event_type="daily_reel_factory.operator_summary",
            payload={
                "selector": selector,
                "summary": summary.to_payload(),
            },
        )
        self.operator_events.append(event)
        return event


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


def _run_summary_payload(result: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], result["run_summary"])


def _operator_event_payload(result: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], result["operator_event"])


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
    assert service.created_families[0].metadata["production_model"] == "package_first"
    assert service.created_reels[0].metadata["target_artifact"] == "ready_to_post_package"
    assert process_calls == ["reel-1", "reel-2", "reel-3", "reel-4"]

    assert result["status"] == "scheduled"
    assert result["production_model"] == "package_first"
    assert result["target_artifact"] == "ready_to_post_package"
    assert result["page_count"] == 1
    assert result["family_count"] == 2
    assert result["reel_count"] == 4
    assert result["dispatch_count"] == 4
    assert result["skipped_count"] == 0
    assert result["budget_guardrails"] == {
        "status": "enforced",
        "checked_pages": 1,
        "blocked_pages": 0,
    }
    assert len(service.persisted_summaries) == 1
    assert len(service.operator_events) == 1

    run_summary = _run_summary_payload(result)
    assert run_summary["summary_id"] == "summary-1"
    assert cast(dict[str, object], run_summary["counts"]) == {
        "pages": 1,
        "families": 2,
        "reels": 4,
        "dispatched": 4,
        "skipped": 0,
        "blocked_pages": 0,
    }
    summary_pages = cast(list[dict[str, object]], run_summary["pages"])
    assert summary_pages[0]["dispatched_reels"] == 4
    assert summary_pages[0]["skipped_reels"] == 0

    operator_event = _operator_event_payload(result)
    assert operator_event["event_id"] == "event-1"
    assert operator_event["event_type"] == "daily_reel_factory.operator_summary"
    assert cast(dict[str, object], operator_event["payload"])["selector"] == "seed-page"


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
    assert result["skipped_count"] == 4
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
    run_summary = _run_summary_payload(result)
    assert cast(dict[str, object], run_summary["counts"]) == {
        "pages": 1,
        "families": 2,
        "reels": 4,
        "dispatched": 0,
        "skipped": 4,
        "blocked_pages": 1,
    }
    operator_event = _operator_event_payload(result)
    assert cast(dict[str, object], operator_event["payload"])["selector"] == "seed-page"


def test_daily_reel_factory_processes_multiple_pages_and_summarizes_partial_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RecordingFactoryService(
        pages=[
            OwnedPageSelection(
                org_id="org-1",
                page_id="page-1",
                display_name="Page One",
                platform="instagram",
                handle="@page-one",
                content_pillars=("proof", "faq"),
                metadata={"selection_seed": "seed-page"},
            ),
            OwnedPageSelection(
                org_id="org-2",
                page_id="page-2",
                display_name="Page Two",
                platform="instagram",
                handle="@page-two",
                content_pillars=("proof", "faq"),
                metadata={"selection_seed": "seed-page"},
            ),
        ],
        global_policies={
            "org-1": {
                "mode_ratios": {
                    "explore": 0.4,
                    "exploit": 0.3,
                    "mutation": 0.2,
                    "chaos": 0.1,
                },
                "budget": {"per_run_usd_limit": 10.0},
            },
            "org-2": {
                "mode_ratios": {
                    "explore": 0.5,
                    "exploit": 0.3,
                    "mutation": 0.1,
                    "chaos": 0.1,
                },
                "budget": {"per_run_usd_limit": 10.0},
            },
        },
        page_policies={
            "page-1": {
                "mode_ratios": {
                    "mutation": 0.6,
                    "explore": 0.2,
                },
                "budget": {"per_run_usd_limit": 6.0},
            },
            "page-2": {
                "mode_ratios": {
                    "exploit": 0.7,
                    "explore": 0.2,
                },
                "budget": {"per_run_usd_limit": 6.0},
            },
        },
    )
    process_calls: list[str] = []

    class MixedGuardrails:
        def check(
            self,
            *,
            page: OwnedPageSelection,
            policy: AppliedPolicy,
            reels: tuple[ReelVariantWorkUnit, ...],
        ) -> BudgetGuardrailOutcome:
            assert len(reels) == 4
            _ = policy
            if page.page_id == "page-2":
                return BudgetGuardrailOutcome(
                    allowed=False,
                    status="blocked",
                    detail="daily limit reached",
                )
            return BudgetGuardrailOutcome(
                allowed=True,
                status="within_limits",
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
        lambda: MixedGuardrails(),
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

    assert result["status"] == "partially_scheduled"
    assert result["page_count"] == 2
    assert result["family_count"] == 4
    assert result["reel_count"] == 8
    assert result["dispatch_count"] == 4
    assert result["skipped_count"] == 4
    assert process_calls == ["reel-1", "reel-2", "reel-3", "reel-4"]

    run_summary = _run_summary_payload(result)
    assert cast(dict[str, object], run_summary["counts"]) == {
        "pages": 2,
        "families": 4,
        "reels": 8,
        "dispatched": 4,
        "skipped": 4,
        "blocked_pages": 1,
    }
    summary_pages = cast(list[dict[str, object]], run_summary["pages"])
    assert [page["dispatched_reels"] for page in summary_pages] == [4, 0]
    assert [page["skipped_reels"] for page in summary_pages] == [0, 4]
    assert [page["family_modes"] for page in summary_pages] == [
        ["mutation", "exploit"],
        ["exploit", "explore"],
    ]

    operator_event = _operator_event_payload(result)
    assert operator_event["aggregate_id"] == "summary-1"
    assert cast(dict[str, object], operator_event["payload"])["selector"] == "seed-page"


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
