"""Provider-facing worker actor definitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from content_lab_assets.providers.runway.jobs import (
    RUNWAY_PROVIDER,
    RunwayJobStatus,
    normalize_runway_job_status,
)
from content_lab_core.budget import (
    BudgetGuardrailDecision,
    BudgetPolicy,
    BudgetUsage,
    budget_policy_from_mapping,
    budget_usage_from_mapping,
    evaluate_provider_submission_guardrail,
)
from content_lab_runs import TaskRowSpec, TaskStatus, build_task_idempotency_key
from content_lab_worker.actors._shared import ActorLike, build_queue_name, get_actor_logger

logger = get_actor_logger("provider")
QUEUE_NAME = build_queue_name("provider")
_PROVIDER_SUBMISSION_TASK_TYPE = "provider.submit"
_RUNWAY_SWEEP_THRESHOLDS = {
    RunwayJobStatus.SUBMITTED.value: timedelta(minutes=15),
    RunwayJobStatus.RUNNING.value: timedelta(minutes=30),
    "polling_failed": timedelta(minutes=10),
    "retryable": timedelta(minutes=10),
    "submission_failed": timedelta(minutes=10),
}
_TERMINAL_PROVIDER_JOB_STATUSES = frozenset(
    {
        RunwayJobStatus.SUCCEEDED.value,
        RunwayJobStatus.FAILED.value,
        RunwayJobStatus.CANCELLED.value,
    }
)


@dataclass(frozen=True, slots=True)
class ProviderSweepThreshold:
    """Sweep threshold attached to a provider-job status."""

    provider: str
    status: str
    max_age: timedelta


def is_terminal_provider_job_status(*, provider: str, status: str) -> bool:
    """Return whether a provider-job status should be excluded from sweeping."""

    normalized_provider = provider.strip().lower()
    normalized_status = status.strip().lower()
    if normalized_provider == RUNWAY_PROVIDER:
        return normalized_status in _TERMINAL_PROVIDER_JOB_STATUSES
    return normalized_status in {"succeeded", "failed", "cancelled"}


def get_provider_sweep_threshold(
    *,
    provider: str,
    status: str,
) -> ProviderSweepThreshold | None:
    """Return the stale-age threshold for a non-terminal provider-job status."""

    normalized_provider = provider.strip().lower()
    normalized_status = status.strip().lower()
    if is_terminal_provider_job_status(provider=normalized_provider, status=normalized_status):
        return None
    if normalized_provider == RUNWAY_PROVIDER:
        max_age = _RUNWAY_SWEEP_THRESHOLDS.get(normalized_status, timedelta(minutes=30))
        return ProviderSweepThreshold(
            provider=normalized_provider,
            status=normalized_status,
            max_age=max_age,
        )
    return ProviderSweepThreshold(
        provider=normalized_provider,
        status=normalized_status,
        max_age=timedelta(minutes=30),
    )


def build_provider_submission_task(
    *,
    org_id: str,
    provider: str,
    external_ref: str,
    run_id: str | None = None,
    asset_id: str | None = None,
    provider_job_id: str | None = None,
    provider_job_status: str = RunwayJobStatus.SUBMITTED.value,
    payload: dict[str, Any] | None = None,
    budget_policy: Mapping[str, object] | BudgetPolicy | None = None,
    budget_usage: Mapping[str, object] | BudgetUsage | None = None,
    submission_cost_usd: float | int | None = None,
) -> TaskRowSpec:
    """Build a durable task envelope for a provider submission/polling cycle."""

    normalized_provider = provider.strip().lower()
    normalized_external_ref = external_ref.strip()
    if not normalized_provider:
        raise ValueError("provider must not be blank")
    if not normalized_external_ref:
        raise ValueError("external_ref must not be blank")
    normalized_provider_job_status = (
        normalize_runway_job_status(provider_job_status).value
        if normalized_provider == RUNWAY_PROVIDER
        else provider_job_status.strip().lower()
    )
    if not normalized_provider_job_status:
        raise ValueError("provider_job_status must not be blank")
    budget_guardrail = _provider_submission_budget_guardrail(
        payload=payload,
        budget_policy=budget_policy,
        budget_usage=budget_usage,
        submission_cost_usd=submission_cost_usd,
    )
    task_payload = {
        "provider": normalized_provider,
        "external_ref": normalized_external_ref,
        "provider_job_status": normalized_provider_job_status,
        **({} if payload is None else dict(payload)),
    }
    if budget_guardrail is not None:
        task_payload["budget_guardrail"] = budget_guardrail.to_payload()
    if asset_id is not None:
        task_payload["asset_id"] = asset_id
    if provider_job_id is not None:
        task_payload["provider_job_id"] = provider_job_id
    if budget_guardrail is not None:
        log = (
            logger.warning
            if not budget_guardrail.allowed or budget_guardrail.status == "warn"
            else logger.info
        )
        log(
            "provider submission budget guardrail provider=%s external_ref=%s status=%s action=%s detail=%s",
            normalized_provider,
            normalized_external_ref,
            budget_guardrail.status,
            budget_guardrail.action,
            budget_guardrail.detail,
        )
    task_spec = TaskRowSpec(
        org_id=org_id,
        task_type=_PROVIDER_SUBMISSION_TASK_TYPE,
        idempotency_key=build_task_idempotency_key(
            _PROVIDER_SUBMISSION_TASK_TYPE,
            payload={
                "provider": normalized_provider,
                "external_ref": normalized_external_ref,
            },
        ),
        status=TaskStatus.QUEUED,
        run_id=run_id,
        payload=task_payload,
    )
    if budget_guardrail is not None and not budget_guardrail.allowed:
        return task_spec.skipped(
            result={
                "budget_guardrail": budget_guardrail.to_payload(),
                "reason": budget_guardrail.detail,
                "status": "skipped_by_budget_guardrail",
            }
        )
    return task_spec


def _provider_submission_budget_guardrail(
    *,
    payload: dict[str, Any] | None,
    budget_policy: Mapping[str, object] | BudgetPolicy | None,
    budget_usage: Mapping[str, object] | BudgetUsage | None,
    submission_cost_usd: float | int | None,
) -> BudgetGuardrailDecision | None:
    raw_policy: object = budget_policy
    raw_usage: object = budget_usage
    if payload is not None:
        raw_policy = raw_policy if raw_policy is not None else payload.get("budget_policy")
        raw_usage = raw_usage if raw_usage is not None else payload.get("budget_usage")

    if raw_policy is None and raw_usage is None and submission_cost_usd is None:
        return None

    resolved_policy = (
        raw_policy
        if isinstance(raw_policy, BudgetPolicy)
        else budget_policy_from_mapping(raw_policy if isinstance(raw_policy, Mapping) else None)
    )
    resolved_usage = (
        raw_usage
        if isinstance(raw_usage, BudgetUsage)
        else budget_usage_from_mapping(raw_usage if isinstance(raw_usage, Mapping) else None)
    )
    return evaluate_provider_submission_guardrail(
        policy=resolved_policy,
        usage=resolved_usage,
        submission_cost_usd=submission_cost_usd,
    )


ACTORS: tuple[ActorLike, ...] = ()

__all__ = [
    "ACTORS",
    "ProviderSweepThreshold",
    "QUEUE_NAME",
    "build_provider_submission_task",
    "get_provider_sweep_threshold",
    "is_terminal_provider_job_status",
    "logger",
]
