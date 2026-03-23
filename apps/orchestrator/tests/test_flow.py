from __future__ import annotations

import importlib
from typing import cast

import pytest

from content_lab_orchestrator.flows import (
    DEFAULT_FLOW_NAME,
    example_flow,
    get_flow_definition,
    list_flow_names,
    process_reel,
)
from content_lab_orchestrator.flows.daily_reel_factory import (
    AppliedPolicy,
    BudgetGuardrailOutcome,
    OwnedPageSelection,
    ReelFamilyWorkUnit,
    ReelVariantWorkUnit,
)

daily_reel_factory_module = importlib.import_module(
    "content_lab_orchestrator.flows.daily_reel_factory"
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
    assert list_flow_names() == ("daily_reel_factory", "process_reel")


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


def test_process_reel_flow_supports_named_execution() -> None:
    assert process_reel(reel_id="reel-42", dry_run=True) == "dry-run processed reel reel-42"
