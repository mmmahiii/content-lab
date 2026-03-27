from __future__ import annotations

from content_lab_core.budget import (
    BudgetPolicy,
    BudgetUsage,
    budget_policy_from_mapping,
    budget_usage_from_mapping,
    evaluate_daily_budget_guardrail,
    evaluate_provider_submission_guardrail,
)


def test_daily_budget_guardrail_reduces_requested_work_to_remaining_budget() -> None:
    decision = evaluate_daily_budget_guardrail(
        policy=BudgetPolicy(per_run_usd_limit=6.0, daily_usd_limit=15.0),
        usage=BudgetUsage(spent_usd=3.0),
        requested_units=4,
    )

    assert decision.allowed is True
    assert decision.status == "warn"
    assert decision.action == "reduce"
    assert decision.requested_units == 4
    assert decision.approved_units == 2
    assert decision.requested_cost_usd == 24.0
    assert decision.approved_cost_usd == 12.0
    assert decision.remaining_before_usd == 12.0
    assert decision.remaining_after_usd == 0.0
    assert decision.reasons == (
        "limited_to_remaining_budget",
        "remaining_budget_below_warning_threshold",
    )


def test_daily_budget_guardrail_warns_when_approved_work_nears_limit() -> None:
    decision = evaluate_daily_budget_guardrail(
        policy=BudgetPolicy(per_run_usd_limit=5.0, daily_usd_limit=20.0, warning_fraction=0.5),
        usage=BudgetUsage(spent_usd=5.0),
        requested_units=1,
    )

    assert decision.allowed is True
    assert decision.status == "warn"
    assert decision.action == "proceed"
    assert decision.approved_units == 1
    assert decision.remaining_after_usd == 10.0
    assert decision.reasons == ("remaining_budget_below_warning_threshold",)


def test_provider_submission_guardrail_stops_when_remaining_budget_is_too_small() -> None:
    decision = evaluate_provider_submission_guardrail(
        policy=BudgetPolicy(per_run_usd_limit=6.0, daily_usd_limit=10.0),
        usage=BudgetUsage(spent_usd=7.0),
    )

    assert decision.allowed is False
    assert decision.status == "stop"
    assert decision.action == "stop"
    assert decision.approved_units == 0
    assert decision.requested_cost_usd == 6.0
    assert decision.remaining_before_usd == 3.0
    assert decision.reasons == ("daily_budget_exhausted",)


def test_budget_mapping_helpers_read_nested_budget_usage() -> None:
    policy = budget_policy_from_mapping(
        {
            "budget": {
                "per_run_usd_limit": 4,
                "daily_usd_limit": 30,
                "warning_fraction": 0.6,
            }
        }
    )
    usage = budget_usage_from_mapping(
        {
            "budget": {
                "daily_spent_usd": 8,
                "daily_committed_usd": 4,
            }
        }
    )

    assert policy == BudgetPolicy(per_run_usd_limit=4.0, daily_usd_limit=30.0, warning_fraction=0.6)
    assert usage == BudgetUsage(spent_usd=8.0, committed_usd=4.0)
