"""Primary phase-1 orchestration flow for daily reel planning."""

# mypy: disable-error-code="no-any-return,untyped-decorator"

from __future__ import annotations

from argparse import Namespace
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Protocol, cast

from prefect.flows import flow

from content_lab_orchestrator.correlation import orchestrator_service_context
from content_lab_runs import JSONValue, idempotency_key_from_payload

from .process_reel import process_reel
from .registry import FlowDefinition

_DEFAULT_POLICY_STATE: dict[str, object] = {
    "mode_ratios": {
        "exploit": 0.3,
        "explore": 0.4,
        "mutation": 0.2,
        "chaos": 0.1,
    },
    "budget": {
        "per_run_usd_limit": 10.0,
        "daily_usd_limit": 40.0,
        "monthly_usd_limit": 800.0,
    },
    "thresholds": {
        "similarity": {
            "warn_at": 0.72,
            "block_at": 0.88,
        },
        "min_quality_score": 0.55,
    },
}
_DEFAULT_CONTENT_PILLARS = ("proof", "faq")
_DEFAULT_VARIANT_LABELS = ("A", "B")
_MAX_FAMILY_COUNT = 2
_MODE_PRIORITY = {
    "explore": 0,
    "exploit": 1,
    "mutation": 2,
    "chaos": 3,
}


@dataclass(frozen=True, slots=True)
class OwnedPageSelection:
    """Minimal owned-page context the factory needs in phase 1."""

    org_id: str
    page_id: str
    display_name: str
    platform: str
    handle: str | None = None
    content_pillars: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "org_id": self.org_id,
            "page_id": self.page_id,
            "display_name": self.display_name,
            "platform": self.platform,
            "content_pillars": list(self.content_pillars),
            "metadata": dict(self.metadata),
        }
        if self.handle is not None:
            payload["handle"] = self.handle
        return payload


@dataclass(frozen=True, slots=True)
class AppliedPolicy:
    """Global + page policy bundle applied to a selected page."""

    page: OwnedPageSelection
    global_policy: dict[str, object]
    page_policy: dict[str, object] | None
    effective_policy: dict[str, object]

    def to_payload(self) -> dict[str, object]:
        return {
            "global": deepcopy(self.global_policy),
            "page": None if self.page_policy is None else deepcopy(self.page_policy),
            "effective": deepcopy(self.effective_policy),
        }


@dataclass(frozen=True, slots=True)
class PlannedFamilySpec:
    """Rule-based phase-1 plan for a reel family and its variants."""

    page: OwnedPageSelection
    policy: AppliedPolicy
    name: str
    mode: str
    content_pillar: str
    variant_labels: tuple[str, ...]
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReelFamilyWorkUnit:
    """Created reel-family work unit."""

    family_id: str
    org_id: str
    page_id: str
    name: str
    mode: str
    metadata: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return {
            "family_id": self.family_id,
            "org_id": self.org_id,
            "page_id": self.page_id,
            "name": self.name,
            "mode": self.mode,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ReelVariantWorkUnit:
    """Created reel-variant work unit ready for downstream processing."""

    reel_id: str
    org_id: str
    page_id: str
    family_id: str
    variant_label: str
    status: str
    metadata: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return {
            "reel_id": self.reel_id,
            "org_id": self.org_id,
            "page_id": self.page_id,
            "family_id": self.family_id,
            "variant_label": self.variant_label,
            "status": self.status,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class BudgetGuardrailOutcome:
    """Result of the current budget-guardrail gate."""

    allowed: bool
    status: str
    detail: str

    def to_payload(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class DispatchRecord:
    """Per-reel downstream dispatch result."""

    reel_id: str
    status: str
    result: object | None = None
    reason: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "reel_id": self.reel_id,
            "status": self.status,
        }
        if self.result is not None:
            payload["result"] = self.result
        if self.reason is not None:
            payload["reason"] = self.reason
        return payload


@dataclass(frozen=True, slots=True)
class PageBatch:
    """Created work units grouped by page."""

    page: OwnedPageSelection
    policy: AppliedPolicy
    families: tuple[ReelFamilyWorkUnit, ...]
    reels: tuple[ReelVariantWorkUnit, ...]


class DailyReelFactoryService(Protocol):
    """Owned-page, policy, and creation operations the factory depends on."""

    def list_owned_pages(self, selector: str) -> list[OwnedPageSelection]: ...

    def load_global_policy(self, *, org_id: str) -> dict[str, object]: ...

    def load_page_policy(self, *, org_id: str, page_id: str) -> dict[str, object] | None: ...

    def create_reel_family(
        self,
        *,
        page: OwnedPageSelection,
        family_name: str,
        mode: str,
        metadata: dict[str, object],
    ) -> ReelFamilyWorkUnit: ...

    def create_reel_variant(
        self,
        *,
        page: OwnedPageSelection,
        family: ReelFamilyWorkUnit,
        variant_label: str,
        metadata: dict[str, object],
    ) -> ReelVariantWorkUnit: ...


class BudgetGuardrailChecker(Protocol):
    """Decision point for the future budget service."""

    def check(
        self,
        *,
        page: OwnedPageSelection,
        policy: AppliedPolicy,
        reels: tuple[ReelVariantWorkUnit, ...],
    ) -> BudgetGuardrailOutcome: ...


class InMemoryDailyReelFactoryService:
    """Deterministic local fallback used until the real orchestration bridge lands."""

    def list_owned_pages(self, selector: str) -> list[OwnedPageSelection]:
        normalized = selector.strip()
        if not normalized:
            raise ValueError("name must not be blank")
        slug = _slugify(normalized)
        return [
            OwnedPageSelection(
                org_id=f"org-{slug}",
                page_id=f"page-{slug}",
                display_name=normalized,
                platform="instagram",
                handle=f"@{slug}",
                content_pillars=_DEFAULT_CONTENT_PILLARS,
                metadata={"selection_seed": normalized},
            )
        ]

    def load_global_policy(self, *, org_id: str) -> dict[str, object]:
        _ = org_id
        return deepcopy(_DEFAULT_POLICY_STATE)

    def load_page_policy(self, *, org_id: str, page_id: str) -> dict[str, object] | None:
        _ = org_id, page_id
        return {
            "mode_ratios": {
                "explore": 0.45,
                "exploit": 0.35,
            },
            "budget": {
                "per_run_usd_limit": 8.0,
            },
        }

    def create_reel_family(
        self,
        *,
        page: OwnedPageSelection,
        family_name: str,
        mode: str,
        metadata: dict[str, object],
    ) -> ReelFamilyWorkUnit:
        identity: dict[str, JSONValue] = {
            "org_id": page.org_id,
            "page_id": page.page_id,
            "family_name": family_name,
            "mode": mode,
        }
        return ReelFamilyWorkUnit(
            family_id=idempotency_key_from_payload("reel_family", identity),
            org_id=page.org_id,
            page_id=page.page_id,
            name=family_name,
            mode=mode,
            metadata=dict(metadata),
        )


    def create_reel_variant(
        self,
        *,
        page: OwnedPageSelection,
        family: ReelFamilyWorkUnit,
        variant_label: str,
        metadata: dict[str, object],
    ) -> ReelVariantWorkUnit:
        identity: dict[str, JSONValue] = {
            "org_id": page.org_id,
            "page_id": page.page_id,
            "family_id": family.family_id,
            "variant_label": variant_label,
        }
        return ReelVariantWorkUnit(
            reel_id=idempotency_key_from_payload("reel", identity),
            org_id=page.org_id,
            page_id=page.page_id,
            family_id=family.family_id,
            variant_label=variant_label,
            status="planning",
            metadata=dict(metadata),
        )


class StubBudgetGuardrailChecker:
    """Placeholder until the durable budget service exists."""

    def check(
        self,
        *,
        page: OwnedPageSelection,
        policy: AppliedPolicy,
        reels: tuple[ReelVariantWorkUnit, ...],
    ) -> BudgetGuardrailOutcome:
        _ = page, policy, reels
        return BudgetGuardrailOutcome(
            allowed=True,
            status="stubbed",
            detail="Budget guardrails are not implemented yet; allowing phase-1 scheduling.",
        )


def _slugify(value: str) -> str:
    fragments = []
    for char in value.strip().lower():
        fragments.append(char if char.isalnum() else "-")
    slug = "-".join(part for part in "".join(fragments).split("-") if part)
    return slug or "world"


def _deep_merge_policy(
    base: dict[str, object],
    overlay: dict[str, object] | None,
) -> dict[str, object]:
    merged = deepcopy(base)
    if overlay is None:
        return merged

    for key, value in overlay.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_policy(existing, value)
            continue
        merged[key] = deepcopy(value)
    return merged


def _mode_ratio(policy: dict[str, object], mode: str) -> float:
    raw_mode_ratios = policy.get("mode_ratios")
    if not isinstance(raw_mode_ratios, dict):
        return 0.0
    raw_ratio = raw_mode_ratios.get(mode)
    if isinstance(raw_ratio, float | int):
        return float(raw_ratio)
    return 0.0


def _selected_modes(policy: dict[str, object], *, family_count: int) -> tuple[str, ...]:
    ranked_modes = sorted(
        _MODE_PRIORITY,
        key=lambda mode: (-_mode_ratio(policy, mode), _MODE_PRIORITY[mode]),
    )
    return tuple(ranked_modes[:family_count])


def _family_name(page: OwnedPageSelection, *, content_pillar: str, mode: str) -> str:
    return f"{page.display_name} {content_pillar} {mode}"


def get_daily_reel_factory_service() -> DailyReelFactoryService:
    """Dependency seam for the current factory data adapter."""

    return InMemoryDailyReelFactoryService()


def get_budget_guardrail_checker() -> BudgetGuardrailChecker:
    """Dependency seam for the future budget service."""

    return StubBudgetGuardrailChecker()


def choose_target_owned_pages(
    seed_name: str,
    *,
    service: DailyReelFactoryService,
) -> list[OwnedPageSelection]:
    """Select the owned pages the daily factory should target."""

    return service.list_owned_pages(seed_name)


def load_applicable_policy(
    target_pages: list[OwnedPageSelection],
    *,
    service: DailyReelFactoryService,
) -> list[AppliedPolicy]:
    """Load the effective policy for each selected page."""

    policies: list[AppliedPolicy] = []
    for page in target_pages:
        global_policy = service.load_global_policy(org_id=page.org_id)
        page_policy = service.load_page_policy(org_id=page.org_id, page_id=page.page_id)
        effective_policy = _deep_merge_policy(global_policy, page_policy)
        policies.append(
            AppliedPolicy(
                page=page,
                global_policy=global_policy,
                page_policy=page_policy,
                effective_policy=effective_policy,
            )
        )
    return policies


def plan_variant_strategy(policy_by_page: list[AppliedPolicy]) -> list[PlannedFamilySpec]:
    """Build a deterministic phase-1 family/variant plan from page and policy state."""

    family_specs: list[PlannedFamilySpec] = []
    for applied_policy in policy_by_page:
        content_pillars = applied_policy.page.content_pillars or _DEFAULT_CONTENT_PILLARS
        family_count = min(_MAX_FAMILY_COUNT, max(1, len(content_pillars)))
        for index, mode in enumerate(
            _selected_modes(applied_policy.effective_policy, family_count=family_count)
        ):
            content_pillar = content_pillars[index % len(content_pillars)]
            family_specs.append(
                PlannedFamilySpec(
                    page=applied_policy.page,
                    policy=applied_policy,
                    name=_family_name(
                        applied_policy.page,
                        content_pillar=content_pillar,
                        mode=mode,
                    ),
                    mode=mode,
                    content_pillar=content_pillar,
                    variant_labels=_DEFAULT_VARIANT_LABELS,
                    metadata={
                        "content_pillar": content_pillar,
                        "selection_seed": applied_policy.page.metadata.get("selection_seed"),
                    },
                )
            )
    return family_specs


def create_reel_work_units(
    plans: list[PlannedFamilySpec],
    *,
    service: DailyReelFactoryService,
) -> list[PageBatch]:
    """Create reel-family and reel work units from the phase-1 plan."""

    batches_by_page: dict[str, PageBatch] = {}
    for plan in plans:
        family = service.create_reel_family(
            page=plan.page,
            family_name=plan.name,
            mode=plan.mode,
            metadata={
                **dict(plan.metadata),
                "policy_mode": plan.mode,
            },
        )
        reels = tuple(
            service.create_reel_variant(
                page=plan.page,
                family=family,
                variant_label=variant_label,
                metadata={
                    "content_pillar": plan.content_pillar,
                    "family_mode": plan.mode,
                },
            )
            for variant_label in plan.variant_labels
        )

        existing_batch = batches_by_page.get(plan.page.page_id)
        if existing_batch is None:
            batches_by_page[plan.page.page_id] = PageBatch(
                page=plan.page,
                policy=plan.policy,
                families=(family,),
                reels=reels,
            )
            continue

        batches_by_page[plan.page.page_id] = PageBatch(
            page=existing_batch.page,
            policy=existing_batch.policy,
            families=(*existing_batch.families, family),
            reels=(*existing_batch.reels, *reels),
        )

    return list(batches_by_page.values())


def evaluate_budget_guardrails(
    page_batches: list[PageBatch],
    *,
    checker: BudgetGuardrailChecker,
) -> dict[str, BudgetGuardrailOutcome]:
    """Run the current budget gate for each page batch."""

    return {
        page_batch.page.page_id: checker.check(
            page=page_batch.page,
            policy=page_batch.policy,
            reels=page_batch.reels,
        )
        for page_batch in page_batches
    }


def run_process_reel(reel: ReelVariantWorkUnit) -> object:
    """Dispatch ``process_reel`` when a persisted reel exists, else return a stub result."""

    if reel.metadata.get("dispatch_mode") == "persisted":
        return cast(object, process_reel(reel_id=reel.reel_id, dry_run=False))
    return {
        "status": "stubbed_dispatch",
        "reel_id": reel.reel_id,
        "detail": "daily_reel_factory has not persisted reel rows for process_reel yet",
    }


def dispatch_process_reel_runs(
    page_batches: list[PageBatch],
    *,
    guardrails: dict[str, BudgetGuardrailOutcome],
) -> list[DispatchRecord]:
    """Invoke ``process_reel`` for each allowed reel."""

    dispatches: list[DispatchRecord] = []
    for page_batch in page_batches:
        guardrail = guardrails[page_batch.page.page_id]
        if not guardrail.allowed:
            dispatches.extend(
                DispatchRecord(
                    reel_id=reel.reel_id,
                    status="skipped",
                    reason=guardrail.detail,
                )
                for reel in page_batch.reels
            )
            continue

        dispatches.extend(
            DispatchRecord(
                reel_id=reel.reel_id,
                status="dispatched",
                result=run_process_reel(reel),
            )
            for reel in page_batch.reels
        )
    return dispatches


def _guardrail_summary(guardrails: dict[str, BudgetGuardrailOutcome]) -> dict[str, object]:
    unique_statuses = sorted({guardrail.status for guardrail in guardrails.values()})
    if not unique_statuses:
        status = "not_run"
    elif len(unique_statuses) == 1:
        status = unique_statuses[0]
    else:
        status = "mixed"

    return {
        "status": status,
        "checked_pages": len(guardrails),
        "blocked_pages": sum(1 for guardrail in guardrails.values() if not guardrail.allowed),
    }


def _factory_status(
    *,
    page_count: int,
    reel_count: int,
    dispatch_count: int,
) -> str:
    if page_count == 0:
        return "no_target_pages"
    if reel_count == 0:
        return "no_work_units"
    if dispatch_count == 0:
        return "guardrail_blocked"
    if dispatch_count == reel_count:
        return "scheduled"
    return "partially_scheduled"


def _serialize_factory_result(
    *,
    page_batches: list[PageBatch],
    guardrails: dict[str, BudgetGuardrailOutcome],
    dispatches: list[DispatchRecord],
) -> dict[str, object]:
    dispatch_count = sum(1 for dispatch in dispatches if dispatch.status == "dispatched")
    page_payloads: list[dict[str, object]] = []
    family_count = 0
    reel_count = 0

    for page_batch in page_batches:
        family_count += len(page_batch.families)
        reel_count += len(page_batch.reels)
        guardrail = guardrails[page_batch.page.page_id]
        page_payloads.append(
            {
                **page_batch.page.to_payload(),
                "policy_sources": {
                    "global": True,
                    "page": page_batch.policy.page_policy is not None,
                },
                "policy": page_batch.policy.to_payload(),
                "guardrail": guardrail.to_payload(),
                "families": [family.to_payload() for family in page_batch.families],
                "reels": [reel.to_payload() for reel in page_batch.reels],
            }
        )

    return {
        "status": _factory_status(
            page_count=len(page_batches),
            reel_count=reel_count,
            dispatch_count=dispatch_count,
        ),
        "page_count": len(page_batches),
        "family_count": family_count,
        "reel_count": reel_count,
        "dispatch_count": dispatch_count,
        "budget_guardrails": _guardrail_summary(guardrails),
        "pages": page_payloads,
        "dispatches": [dispatch.to_payload() for dispatch in dispatches],
    }


@flow(name="daily_reel_factory")
def daily_reel_factory(name: str = "world") -> dict[str, object]:
    """Phase-1 daily factory entrypoint for local execution."""

    _ = orchestrator_service_context()
    service = get_daily_reel_factory_service()
    checker = get_budget_guardrail_checker()

    target_pages = choose_target_owned_pages(name, service=service)
    policy_by_page = load_applicable_policy(target_pages, service=service)
    variant_plan = plan_variant_strategy(policy_by_page)
    page_batches = create_reel_work_units(variant_plan, service=service)
    guardrails = evaluate_budget_guardrails(page_batches, checker=checker)
    dispatches = dispatch_process_reel_runs(page_batches, guardrails=guardrails)
    return _serialize_factory_result(
        page_batches=page_batches,
        guardrails=guardrails,
        dispatches=dispatches,
    )


def build_daily_reel_factory_kwargs(args: Namespace) -> dict[str, object]:
    """Map CLI arguments onto the flow signature."""

    return {"name": args.name}


FLOW_DEFINITION = FlowDefinition(
    name="daily_reel_factory",
    description="Select owned pages, apply policy, and plan the daily reel batch.",
    entrypoint=daily_reel_factory,
    build_kwargs=build_daily_reel_factory_kwargs,
)
