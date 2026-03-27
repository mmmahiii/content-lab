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
_DEFAULT_ESTIMATED_REEL_COST_USD = 1.5
_PACKAGE_DELIVERY_MODEL = "package_first"
_READY_TO_POST_ARTIFACT = "ready_to_post_package"
_OPERATOR_SUMMARY_EVENT_TYPE = "daily_reel_factory.operator_summary"
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
    metadata: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "allowed": self.allowed,
            "status": self.status,
            "detail": self.detail,
        }
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


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
class PersistedRunSummary:
    """Persisted run-summary snapshot for operators and later inspection."""

    summary_id: str
    selector: str
    payload: dict[str, object]

    def to_payload(self) -> dict[str, object]:
        return {
            "summary_id": self.summary_id,
            "selector": self.selector,
            **deepcopy(self.payload),
        }


@dataclass(frozen=True, slots=True)
class OperatorSummaryEvent:
    """Operator-facing outbox event emitted after summary persistence."""

    event_id: str
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: dict[str, object]
    delivery_status: str = "pending"
    emitted: bool = True

    def to_payload(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "event_type": self.event_type,
            "payload": deepcopy(self.payload),
            "delivery_status": self.delivery_status,
            "emitted": self.emitted,
        }


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

    def persist_run_summary(
        self,
        *,
        selector: str,
        summary: dict[str, object],
    ) -> PersistedRunSummary: ...

    def emit_operator_summary_event(
        self,
        *,
        selector: str,
        summary: PersistedRunSummary,
    ) -> OperatorSummaryEvent: ...


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

    def persist_run_summary(
        self,
        *,
        selector: str,
        summary: dict[str, object],
    ) -> PersistedRunSummary:
        identity: dict[str, JSONValue] = {
            "selector": selector,
            "summary": cast(JSONValue, deepcopy(summary)),
        }
        return PersistedRunSummary(
            summary_id=idempotency_key_from_payload("daily_reel_factory_summary", identity),
            selector=selector,
            payload=deepcopy(summary),
        )

    def emit_operator_summary_event(
        self,
        *,
        selector: str,
        summary: PersistedRunSummary,
    ) -> OperatorSummaryEvent:
        identity: dict[str, JSONValue] = {
            "selector": selector,
            "summary_id": summary.summary_id,
            "event_type": _OPERATOR_SUMMARY_EVENT_TYPE,
        }
        return OperatorSummaryEvent(
            event_id=idempotency_key_from_payload("daily_reel_factory_operator_event", identity),
            aggregate_type="daily_reel_factory_run_summary",
            aggregate_id=summary.summary_id,
            event_type=_OPERATOR_SUMMARY_EVENT_TYPE,
            payload={
                "selector": selector,
                "summary": summary.to_payload(),
            },
        )


class PolicyBudgetGuardrailChecker:
    """Phase-1 budget gate using configured policy limits and reel-count estimates."""

    def __init__(
        self, *, estimated_reel_cost_usd: float = _DEFAULT_ESTIMATED_REEL_COST_USD
    ) -> None:
        self._estimated_reel_cost_usd = estimated_reel_cost_usd

    def check(
        self,
        *,
        page: OwnedPageSelection,
        policy: AppliedPolicy,
        reels: tuple[ReelVariantWorkUnit, ...],
    ) -> BudgetGuardrailOutcome:
        budget = _policy_budget(policy.effective_policy)
        per_run_limit = _numeric_policy_value(budget.get("per_run_usd_limit"))
        estimated_run_cost = round(len(reels) * self._estimated_reel_cost_usd, 2)
        metadata: dict[str, object] = {
            "page_id": page.page_id,
            "reel_count": len(reels),
            "estimated_reel_cost_usd": self._estimated_reel_cost_usd,
            "estimated_run_cost_usd": estimated_run_cost,
        }
        for key in ("per_run_usd_limit", "daily_usd_limit", "monthly_usd_limit"):
            value = _numeric_policy_value(budget.get(key))
            if value is not None:
                metadata[key] = value

        if per_run_limit is not None and estimated_run_cost > per_run_limit:
            return BudgetGuardrailOutcome(
                allowed=False,
                status="blocked",
                detail=(
                    f"estimated run cost {estimated_run_cost:.2f} exceeds "
                    f"per-run limit {per_run_limit:.2f}"
                ),
                metadata=metadata,
            )

        detail = "estimated run cost is within configured budget limits"
        if per_run_limit is None:
            detail = "no per-run budget limit configured; allowing scheduling in phase 1"
        return BudgetGuardrailOutcome(
            allowed=True,
            status="within_limits",
            detail=detail,
            metadata=metadata,
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


def _policy_budget(policy: dict[str, object]) -> dict[str, object]:
    raw_budget = policy.get("budget")
    if isinstance(raw_budget, dict):
        return raw_budget
    return {}


def _numeric_policy_value(value: object) -> float | None:
    if isinstance(value, float | int):
        return float(value)
    return None


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

    return PolicyBudgetGuardrailChecker()


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
                        "mode_ratio": _mode_ratio(applied_policy.effective_policy, mode),
                        "production_model": _PACKAGE_DELIVERY_MODEL,
                        "target_artifact": _READY_TO_POST_ARTIFACT,
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
                    "production_model": _PACKAGE_DELIVERY_MODEL,
                    "target_artifact": _READY_TO_POST_ARTIFACT,
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


def _build_run_summary_payload(
    *,
    selector: str,
    page_batches: list[PageBatch],
    guardrails: dict[str, BudgetGuardrailOutcome],
    dispatches: list[DispatchRecord],
) -> dict[str, object]:
    dispatch_count = sum(1 for dispatch in dispatches if dispatch.status == "dispatched")
    skipped_count = sum(1 for dispatch in dispatches if dispatch.status == "skipped")
    family_count = sum(len(page_batch.families) for page_batch in page_batches)
    reel_count = sum(len(page_batch.reels) for page_batch in page_batches)
    dispatch_by_reel_id = {dispatch.reel_id: dispatch for dispatch in dispatches}

    pages: list[dict[str, object]] = []
    for page_batch in page_batches:
        guardrail = guardrails[page_batch.page.page_id]
        page_dispatches = [
            dispatch_by_reel_id[reel.reel_id]
            for reel in page_batch.reels
            if reel.reel_id in dispatch_by_reel_id
        ]
        pages.append(
            {
                "org_id": page_batch.page.org_id,
                "page_id": page_batch.page.page_id,
                "display_name": page_batch.page.display_name,
                "platform": page_batch.page.platform,
                "family_count": len(page_batch.families),
                "reel_count": len(page_batch.reels),
                "dispatched_reels": sum(
                    1 for dispatch in page_dispatches if dispatch.status == "dispatched"
                ),
                "skipped_reels": sum(
                    1 for dispatch in page_dispatches if dispatch.status == "skipped"
                ),
                "guardrail": guardrail.to_payload(),
                "family_modes": [family.mode for family in page_batch.families],
                "content_pillars": [
                    str(family.metadata.get("content_pillar"))
                    for family in page_batch.families
                    if family.metadata.get("content_pillar") is not None
                ],
            }
        )

    return {
        "selector": selector,
        "status": _factory_status(
            page_count=len(page_batches),
            reel_count=reel_count,
            dispatch_count=dispatch_count,
        ),
        "production_model": _PACKAGE_DELIVERY_MODEL,
        "target_artifact": _READY_TO_POST_ARTIFACT,
        "counts": {
            "pages": len(page_batches),
            "families": family_count,
            "reels": reel_count,
            "dispatched": dispatch_count,
            "skipped": skipped_count,
            "blocked_pages": sum(1 for guardrail in guardrails.values() if not guardrail.allowed),
        },
        "guardrails": _guardrail_summary(guardrails),
        "pages": pages,
    }


def persist_factory_run_summary(
    selector: str,
    *,
    page_batches: list[PageBatch],
    guardrails: dict[str, BudgetGuardrailOutcome],
    dispatches: list[DispatchRecord],
    service: DailyReelFactoryService,
) -> PersistedRunSummary:
    """Persist a clear run-summary snapshot for later inspection."""

    return service.persist_run_summary(
        selector=selector,
        summary=_build_run_summary_payload(
            selector=selector,
            page_batches=page_batches,
            guardrails=guardrails,
            dispatches=dispatches,
        ),
    )


def emit_operator_summary_event(
    selector: str,
    *,
    summary: PersistedRunSummary,
    service: DailyReelFactoryService,
) -> OperatorSummaryEvent:
    """Emit the operator-facing summary outbox event."""

    return service.emit_operator_summary_event(selector=selector, summary=summary)


def _serialize_factory_result(
    *,
    page_batches: list[PageBatch],
    guardrails: dict[str, BudgetGuardrailOutcome],
    dispatches: list[DispatchRecord],
    run_summary: PersistedRunSummary | None = None,
    operator_event: OperatorSummaryEvent | None = None,
) -> dict[str, object]:
    dispatch_count = sum(1 for dispatch in dispatches if dispatch.status == "dispatched")
    skipped_count = sum(1 for dispatch in dispatches if dispatch.status == "skipped")
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
                "selection": {
                    "production_model": _PACKAGE_DELIVERY_MODEL,
                    "target_artifact": _READY_TO_POST_ARTIFACT,
                    "family_modes": [family.mode for family in page_batch.families],
                    "variant_labels": [reel.variant_label for reel in page_batch.reels],
                },
                "families": [family.to_payload() for family in page_batch.families],
                "reels": [reel.to_payload() for reel in page_batch.reels],
            }
        )

    result: dict[str, object] = {
        "status": _factory_status(
            page_count=len(page_batches),
            reel_count=reel_count,
            dispatch_count=dispatch_count,
        ),
        "production_model": _PACKAGE_DELIVERY_MODEL,
        "target_artifact": _READY_TO_POST_ARTIFACT,
        "page_count": len(page_batches),
        "family_count": family_count,
        "reel_count": reel_count,
        "dispatch_count": dispatch_count,
        "skipped_count": skipped_count,
        "budget_guardrails": _guardrail_summary(guardrails),
        "pages": page_payloads,
        "dispatches": [dispatch.to_payload() for dispatch in dispatches],
    }
    if run_summary is not None:
        result["run_summary"] = run_summary.to_payload()
    if operator_event is not None:
        result["operator_event"] = operator_event.to_payload()
    return result


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
    run_summary = persist_factory_run_summary(
        name,
        page_batches=page_batches,
        guardrails=guardrails,
        dispatches=dispatches,
        service=service,
    )
    operator_event = emit_operator_summary_event(
        name,
        summary=run_summary,
        service=service,
    )
    return _serialize_factory_result(
        page_batches=page_batches,
        guardrails=guardrails,
        dispatches=dispatches,
        run_summary=run_summary,
        operator_event=operator_event,
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
