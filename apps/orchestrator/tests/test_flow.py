from __future__ import annotations

import importlib
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
    OwnedPageSelection,
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
            "budget": {
                "per_run_usd_limit": 10.0,
                "daily_usd_limit": 40.0,
            },
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
            assert cast(dict[str, object], policy.effective_policy["budget"]) == {
                "per_run_usd_limit": 6.0,
                "daily_usd_limit": 40.0,
            }
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
        "warned_pages": 0,
        "limited_pages": 0,
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
        "warned_pages": 0,
        "limited_pages": 0,
    }
    assert [dispatch["status"] for dispatch in _dispatch_payloads(result)] == [
        "skipped",
        "skipped",
        "skipped",
        "skipped",
    ]


def test_daily_reel_factory_reduces_dispatches_when_budget_guardrail_limits_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RecordingFactoryService()
    process_calls: list[str] = []

    def _limited_global_policy(*, org_id: str) -> dict[str, object]:
        assert org_id == "org-1"
        return {
            "mode_ratios": {
                "explore": 0.4,
                "exploit": 0.3,
                "mutation": 0.2,
                "chaos": 0.1,
            },
            "budget": {
                "per_run_usd_limit": 10.0,
                "daily_usd_limit": 15.0,
                "daily_spent_usd": 3.0,
            },
        }

    monkeypatch.setattr(service, "load_global_policy", _limited_global_policy)
    monkeypatch.setattr(
        daily_reel_factory_module,
        "get_daily_reel_factory_service",
        lambda: service,
    )

    def _record_limited_process_call(reel: ReelVariantWorkUnit) -> str:
        process_calls.append(reel.reel_id)
        return f"processed {reel.reel_id}"

    monkeypatch.setattr(
        daily_reel_factory_module,
        "run_process_reel",
        _record_limited_process_call,
    )

    result = _result_payload(daily_reel_factory_module.daily_reel_factory(name="seed-page"))

    assert result["status"] == "partially_scheduled"
    assert result["dispatch_count"] == 2
    assert process_calls == ["reel-1", "reel-2"]
    assert result["budget_guardrails"] == {
        "status": "warn",
        "checked_pages": 1,
        "blocked_pages": 0,
        "warned_pages": 1,
        "limited_pages": 1,
    }
    assert [dispatch["status"] for dispatch in _dispatch_payloads(result)] == [
        "dispatched",
        "dispatched",
        "skipped",
        "skipped",
    ]
    assert cast(list[dict[str, object]], result["pages"])[0]["guardrail"] == {
        "allowed": True,
        "status": "warn",
        "detail": "Reduced daily_plan: approved 2 of 4 units within the remaining daily budget of 12.00 USD.",
        "action": "reduce",
        "scope": "daily_plan",
        "requested_units": 4,
        "approved_units": 2,
        "unit_cost_usd": 6.0,
        "requested_cost_usd": 24.0,
        "approved_cost_usd": 12.0,
        "spent_usd": 3.0,
        "committed_usd": 0.0,
        "reserved_usd": 3.0,
        "remaining_before_usd": 12.0,
        "remaining_after_usd": 0.0,
        "reasons": [
            "limited_to_remaining_budget",
            "remaining_budget_below_warning_threshold",
        ],
    }


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
