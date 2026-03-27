"""Deterministic budget guardrail helpers shared across services."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import floor


def _normalize_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _normalize_money(
    value: float | int | None,
    *,
    field_name: str,
    allow_none: bool = False,
) -> float | None:
    if value is None:
        if allow_none:
            return None
        raise ValueError(f"{field_name} must not be None")
    normalized = round(float(value), 2)
    if normalized < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return normalized


def _coerce_money(value: object, *, default: float | None) -> float | None:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError("budget values must be numeric")
    if isinstance(value, int | float):
        return _normalize_money(value, field_name="budget value", allow_none=False)
    raise ValueError("budget values must be numeric")


def _budget_mapping(payload: Mapping[str, object] | None) -> Mapping[str, object]:
    if payload is None:
        return {}
    raw_budget = payload.get("budget")
    if isinstance(raw_budget, Mapping):
        return raw_budget
    return payload


def _warning_threshold(policy: BudgetPolicy) -> float | None:
    if policy.daily_usd_limit is None:
        return None
    return round(policy.daily_usd_limit * (1 - policy.warning_fraction), 2)


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    """Inspectable spend policy used for planning and submission guardrails."""

    per_run_usd_limit: float = 0.0
    daily_usd_limit: float | None = None
    warning_fraction: float = 0.8

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "per_run_usd_limit",
            _normalize_money(
                self.per_run_usd_limit,
                field_name="per_run_usd_limit",
                allow_none=False,
            ),
        )
        object.__setattr__(
            self,
            "daily_usd_limit",
            _normalize_money(
                self.daily_usd_limit,
                field_name="daily_usd_limit",
                allow_none=True,
            ),
        )
        warning_fraction = float(self.warning_fraction)
        if not 0 <= warning_fraction <= 1:
            raise ValueError("warning_fraction must be between 0 and 1")
        object.__setattr__(self, "warning_fraction", warning_fraction)

    @property
    def warning_threshold_usd(self) -> float | None:
        return _warning_threshold(self)


@dataclass(frozen=True, slots=True)
class BudgetUsage:
    """Current spend snapshot used to calculate remaining budget."""

    spent_usd: float = 0.0
    committed_usd: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "spent_usd",
            _normalize_money(self.spent_usd, field_name="spent_usd", allow_none=False),
        )
        object.__setattr__(
            self,
            "committed_usd",
            _normalize_money(
                self.committed_usd,
                field_name="committed_usd",
                allow_none=False,
            ),
        )

    @property
    def reserved_usd(self) -> float:
        return round(self.spent_usd + self.committed_usd, 2)


@dataclass(frozen=True, slots=True)
class BudgetGuardrailDecision:
    """Structured outcome of a budget guardrail evaluation."""

    allowed: bool
    status: str
    detail: str
    action: str = "proceed"
    scope: str = "budget"
    requested_units: int = 0
    approved_units: int = 0
    unit_cost_usd: float = 0.0
    requested_cost_usd: float = 0.0
    approved_cost_usd: float = 0.0
    spent_usd: float = 0.0
    committed_usd: float = 0.0
    reserved_usd: float = 0.0
    remaining_before_usd: float | None = None
    remaining_after_usd: float | None = None
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", _normalize_text(self.status, field_name="status"))
        object.__setattr__(self, "detail", _normalize_text(self.detail, field_name="detail"))
        object.__setattr__(self, "action", _normalize_text(self.action, field_name="action"))
        object.__setattr__(self, "scope", _normalize_text(self.scope, field_name="scope"))
        if self.requested_units < 0:
            raise ValueError("requested_units must be non-negative")
        if self.approved_units < 0:
            raise ValueError("approved_units must be non-negative")
        object.__setattr__(
            self,
            "unit_cost_usd",
            _normalize_money(self.unit_cost_usd, field_name="unit_cost_usd", allow_none=False),
        )
        object.__setattr__(
            self,
            "requested_cost_usd",
            _normalize_money(
                self.requested_cost_usd,
                field_name="requested_cost_usd",
                allow_none=False,
            ),
        )
        object.__setattr__(
            self,
            "approved_cost_usd",
            _normalize_money(
                self.approved_cost_usd,
                field_name="approved_cost_usd",
                allow_none=False,
            ),
        )
        object.__setattr__(
            self,
            "spent_usd",
            _normalize_money(self.spent_usd, field_name="spent_usd", allow_none=False),
        )
        object.__setattr__(
            self,
            "committed_usd",
            _normalize_money(
                self.committed_usd,
                field_name="committed_usd",
                allow_none=False,
            ),
        )
        object.__setattr__(
            self,
            "reserved_usd",
            _normalize_money(self.reserved_usd, field_name="reserved_usd", allow_none=False),
        )
        object.__setattr__(
            self,
            "remaining_before_usd",
            _normalize_money(
                self.remaining_before_usd,
                field_name="remaining_before_usd",
                allow_none=True,
            ),
        )
        object.__setattr__(
            self,
            "remaining_after_usd",
            _normalize_money(
                self.remaining_after_usd,
                field_name="remaining_after_usd",
                allow_none=True,
            ),
        )
        object.__setattr__(
            self,
            "reasons",
            tuple(_normalize_text(reason, field_name="reason") for reason in self.reasons),
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "status": self.status,
            "detail": self.detail,
            "action": self.action,
            "scope": self.scope,
            "requested_units": self.requested_units,
            "approved_units": self.approved_units,
            "unit_cost_usd": self.unit_cost_usd,
            "requested_cost_usd": self.requested_cost_usd,
            "approved_cost_usd": self.approved_cost_usd,
            "spent_usd": self.spent_usd,
            "committed_usd": self.committed_usd,
            "reserved_usd": self.reserved_usd,
            "remaining_before_usd": self.remaining_before_usd,
            "remaining_after_usd": self.remaining_after_usd,
            "reasons": list(self.reasons),
        }


def budget_policy_from_mapping(payload: Mapping[str, object] | None) -> BudgetPolicy:
    """Build a normalized policy from a plain mapping or nested ``budget`` block."""

    budget = _budget_mapping(payload)
    warning_value = budget.get("warning_fraction")
    if warning_value is None:
        warning_value = budget.get("warn_fraction")
    normalized_warning = _coerce_money(warning_value, default=0.8)
    return BudgetPolicy(
        per_run_usd_limit=_coerce_money(budget.get("per_run_usd_limit"), default=0.0) or 0.0,
        daily_usd_limit=_coerce_money(budget.get("daily_usd_limit"), default=None),
        warning_fraction=0.8 if normalized_warning is None else float(normalized_warning),
    )


def budget_usage_from_mapping(payload: Mapping[str, object] | None) -> BudgetUsage:
    """Build a normalized usage snapshot from a plain mapping or nested ``budget`` block."""

    budget = _budget_mapping(payload)
    return BudgetUsage(
        spent_usd=_coerce_money(
            budget.get("daily_spent_usd", budget.get("spent_usd")),
            default=0.0,
        )
        or 0.0,
        committed_usd=_coerce_money(
            budget.get("daily_committed_usd", budget.get("committed_usd")),
            default=0.0,
        )
        or 0.0,
    )


def evaluate_daily_budget_guardrail(
    *,
    policy: BudgetPolicy,
    usage: BudgetUsage,
    requested_units: int,
) -> BudgetGuardrailDecision:
    """Evaluate a planned batch of daily generation work."""

    return _evaluate_guardrail(
        scope="daily_plan",
        policy=policy,
        usage=usage,
        requested_units=requested_units,
        unit_cost_usd=policy.per_run_usd_limit,
        allow_partial=True,
    )


def evaluate_provider_submission_guardrail(
    *,
    policy: BudgetPolicy,
    usage: BudgetUsage,
    submission_cost_usd: float | int | None = None,
) -> BudgetGuardrailDecision:
    """Evaluate whether a single provider submission fits inside remaining budget."""

    return _evaluate_guardrail(
        scope="provider_submission",
        policy=policy,
        usage=usage,
        requested_units=1,
        unit_cost_usd=policy.per_run_usd_limit
        if submission_cost_usd is None
        else submission_cost_usd,
        allow_partial=False,
    )


def _evaluate_guardrail(
    *,
    scope: str,
    policy: BudgetPolicy,
    usage: BudgetUsage,
    requested_units: int,
    unit_cost_usd: float | int,
    allow_partial: bool,
) -> BudgetGuardrailDecision:
    if requested_units < 0:
        raise ValueError("requested_units must be non-negative")

    unit_cost = _normalize_money(unit_cost_usd, field_name="unit_cost_usd", allow_none=False)
    if unit_cost is None:
        raise ValueError("unit_cost_usd must not be None")
    requested_cost = round(requested_units * unit_cost, 2)
    reserved_usd = usage.reserved_usd

    if requested_units == 0:
        return BudgetGuardrailDecision(
            allowed=True,
            status="allow",
            detail="No budgeted work was requested.",
            action="proceed",
            scope=scope,
            requested_units=0,
            approved_units=0,
            unit_cost_usd=unit_cost,
            requested_cost_usd=0.0,
            approved_cost_usd=0.0,
            spent_usd=usage.spent_usd,
            committed_usd=usage.committed_usd,
            reserved_usd=reserved_usd,
        )

    if policy.daily_usd_limit is None:
        return BudgetGuardrailDecision(
            allowed=True,
            status="allow",
            detail="No daily budget limit is configured; allowing the requested work.",
            action="proceed",
            scope=scope,
            requested_units=requested_units,
            approved_units=requested_units,
            unit_cost_usd=unit_cost,
            requested_cost_usd=requested_cost,
            approved_cost_usd=requested_cost,
            spent_usd=usage.spent_usd,
            committed_usd=usage.committed_usd,
            reserved_usd=reserved_usd,
            reasons=("daily_limit_not_configured",),
        )

    remaining_before = round(max(policy.daily_usd_limit - reserved_usd, 0.0), 2)
    if unit_cost == 0 or requested_cost <= remaining_before:
        approved_units = requested_units
    elif allow_partial:
        approved_units = min(requested_units, floor((remaining_before / unit_cost) + 1e-9))
    else:
        approved_units = 0

    approved_cost = round(approved_units * unit_cost, 2)
    remaining_after = round(max(remaining_before - approved_cost, 0.0), 2)
    warning_threshold = policy.warning_threshold_usd

    if approved_units == 0:
        return BudgetGuardrailDecision(
            allowed=False,
            status="stop",
            detail=(
                f"Stopped {scope}: requested {requested_cost:.2f} USD but only "
                f"{remaining_before:.2f} USD remains in today's budget."
            ),
            action="stop",
            scope=scope,
            requested_units=requested_units,
            approved_units=0,
            unit_cost_usd=unit_cost,
            requested_cost_usd=requested_cost,
            approved_cost_usd=0.0,
            spent_usd=usage.spent_usd,
            committed_usd=usage.committed_usd,
            reserved_usd=reserved_usd,
            remaining_before_usd=remaining_before,
            remaining_after_usd=remaining_before,
            reasons=("daily_budget_exhausted",),
        )

    if approved_units < requested_units:
        reasons = ["limited_to_remaining_budget"]
        if warning_threshold is not None and remaining_after <= warning_threshold:
            reasons.append("remaining_budget_below_warning_threshold")
        return BudgetGuardrailDecision(
            allowed=True,
            status="warn",
            detail=(
                f"Reduced {scope}: approved {approved_units} of {requested_units} "
                f"units within the remaining daily budget of {remaining_before:.2f} USD."
            ),
            action="reduce",
            scope=scope,
            requested_units=requested_units,
            approved_units=approved_units,
            unit_cost_usd=unit_cost,
            requested_cost_usd=requested_cost,
            approved_cost_usd=approved_cost,
            spent_usd=usage.spent_usd,
            committed_usd=usage.committed_usd,
            reserved_usd=reserved_usd,
            remaining_before_usd=remaining_before,
            remaining_after_usd=remaining_after,
            reasons=tuple(reasons),
        )

    if warning_threshold is not None and remaining_after <= warning_threshold:
        return BudgetGuardrailDecision(
            allowed=True,
            status="warn",
            detail=(
                f"Approved {requested_units} units, but only {remaining_after:.2f} USD "
                f"remains before today's budget guardrail is fully consumed."
            ),
            action="proceed",
            scope=scope,
            requested_units=requested_units,
            approved_units=approved_units,
            unit_cost_usd=unit_cost,
            requested_cost_usd=requested_cost,
            approved_cost_usd=approved_cost,
            spent_usd=usage.spent_usd,
            committed_usd=usage.committed_usd,
            reserved_usd=reserved_usd,
            remaining_before_usd=remaining_before,
            remaining_after_usd=remaining_after,
            reasons=("remaining_budget_below_warning_threshold",),
        )

    return BudgetGuardrailDecision(
        allowed=True,
        status="allow",
        detail=(
            f"Approved {requested_units} units within the daily budget; "
            f"{remaining_after:.2f} USD remains available."
        ),
        action="proceed",
        scope=scope,
        requested_units=requested_units,
        approved_units=approved_units,
        unit_cost_usd=unit_cost,
        requested_cost_usd=requested_cost,
        approved_cost_usd=approved_cost,
        spent_usd=usage.spent_usd,
        committed_usd=usage.committed_usd,
        reserved_usd=reserved_usd,
        remaining_before_usd=remaining_before,
        remaining_after_usd=remaining_after,
    )


__all__ = [
    "BudgetGuardrailDecision",
    "BudgetPolicy",
    "BudgetUsage",
    "budget_policy_from_mapping",
    "budget_usage_from_mapping",
    "evaluate_daily_budget_guardrail",
    "evaluate_provider_submission_guardrail",
]
