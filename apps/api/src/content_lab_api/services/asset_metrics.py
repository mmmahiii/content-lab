"""Asset usage and performance aggregation helpers."""

from __future__ import annotations

import itertools
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from content_lab_api.models import (
    AssetCombinationPerformance,
    AssetPackItem,
    AssetPerformanceSummary,
    AssetUsage,
    AssetUsageSummary,
    ReelMetric,
    Run,
)

ATTRIBUTION_NOTE = "correlational_not_causal"
DEFAULT_COMBINATION_SIZES = (2, 3, 4)


def refresh_asset_usage_summaries(
    db: Session,
    *,
    org_id: uuid.UUID,
    asset_ids: Sequence[uuid.UUID] | None = None,
) -> list[AssetUsageSummary]:
    """Recompute usage counters for selected assets or the whole org."""

    resolved_asset_ids = _asset_ids_for_usage_refresh(db, org_id=org_id, asset_ids=asset_ids)
    summaries: list[AssetUsageSummary] = []
    for asset_id in resolved_asset_ids:
        usage_rows = (
            db.query(AssetUsage)
            .filter(AssetUsage.org_id == org_id, AssetUsage.asset_id == asset_id)
            .all()
        )
        role_counts: dict[str, int] = {}
        reel_ids: set[uuid.UUID] = set()
        last_used_at: datetime | None = None
        for usage in usage_rows:
            reel_ids.add(usage.reel_id)
            role = usage.component_role or usage.usage_role
            role_counts[role] = role_counts.get(role, 0) + 1
            if last_used_at is None or usage.created_at > last_used_at:
                last_used_at = usage.created_at
        used_in_pack_count = int(
            db.query(func.count(distinct(AssetPackItem.asset_pack_id)))
            .filter(AssetPackItem.asset_id == asset_id)
            .scalar()
            or 0
        )
        summary = _get_or_create_usage_summary(db, org_id=org_id, asset_id=asset_id)
        summary.reuse_count = len(usage_rows)
        summary.used_in_reel_count = len(reel_ids)
        summary.used_in_pack_count = used_in_pack_count
        summary.used_as_component_role_counts = role_counts
        summary.last_used_at = last_used_at
        summaries.append(summary)
    db.flush()
    return summaries


def aggregate_reel_metric_asset_performance(
    db: Session,
    *,
    reel_metric_id: uuid.UUID,
    combination_sizes: Sequence[int] = DEFAULT_COMBINATION_SIZES,
) -> dict[str, int]:
    """Attribute one reel metric snapshot back to component assets and combinations.

    The resulting rows are intentionally correlational summaries. They make assets and
    asset groups rankable without pretending the asset caused the observed performance.
    """

    metric = db.get(ReelMetric, reel_metric_id)
    if metric is None:
        raise ValueError(f"Unknown reel_metric_id {reel_metric_id!s}")
    reel_id = _reel_id_from_metric(db, metric)
    if reel_id is None:
        return {"asset_summaries": 0, "combination_summaries": 0}
    numeric_metrics = _numeric_metrics(metric.metrics)
    if not numeric_metrics:
        return {"asset_summaries": 0, "combination_summaries": 0}
    usages = (
        db.query(AssetUsage)
        .filter(AssetUsage.org_id == metric.org_id, AssetUsage.reel_id == reel_id)
        .order_by(AssetUsage.sort_order.asc().nullslast(), AssetUsage.created_at.asc())
        .all()
    )
    asset_summary_count = 0
    for usage in usages:
        summary = _get_or_create_performance_summary(
            db,
            org_id=metric.org_id,
            asset_id=usage.asset_id,
            component_role=usage.component_role or usage.usage_role,
        )
        _apply_metric_sample(summary, metrics=numeric_metrics, captured_at=metric.captured_at)
        asset_summary_count += 1

    combination_summary_count = 0
    for combo in _usage_combinations(usages, sizes=combination_sizes):
        combo_summary = _get_or_create_combination_summary(
            db,
            org_id=metric.org_id,
            usages=combo,
        )
        _apply_metric_sample(
            combo_summary,
            metrics=numeric_metrics,
            captured_at=metric.captured_at,
        )
        combination_summary_count += 1

    db.flush()
    return {
        "asset_summaries": asset_summary_count,
        "combination_summaries": combination_summary_count,
    }


def _asset_ids_for_usage_refresh(
    db: Session,
    *,
    org_id: uuid.UUID,
    asset_ids: Sequence[uuid.UUID] | None,
) -> list[uuid.UUID]:
    if asset_ids is not None:
        return list(dict.fromkeys(asset_ids))
    usage_ids = (
        db.query(AssetUsage.asset_id)
        .filter(AssetUsage.org_id == org_id)
        .distinct()
        .all()
    )
    pack_ids = db.query(AssetPackItem.asset_id).filter(AssetPackItem.asset_id.isnot(None)).all()
    return [
        uuid.UUID(str(value))
        for value in dict.fromkeys([row[0] for row in usage_ids] + [row[0] for row in pack_ids])
        if value is not None
    ]


def _get_or_create_usage_summary(
    db: Session,
    *,
    org_id: uuid.UUID,
    asset_id: uuid.UUID,
) -> AssetUsageSummary:
    summary = (
        db.query(AssetUsageSummary)
        .filter(AssetUsageSummary.org_id == org_id, AssetUsageSummary.asset_id == asset_id)
        .one_or_none()
    )
    if summary is not None:
        return summary
    summary = AssetUsageSummary(org_id=org_id, asset_id=asset_id)
    db.add(summary)
    return summary


def _get_or_create_performance_summary(
    db: Session,
    *,
    org_id: uuid.UUID,
    asset_id: uuid.UUID,
    component_role: str,
) -> AssetPerformanceSummary:
    summary = (
        db.query(AssetPerformanceSummary)
        .filter(
            AssetPerformanceSummary.org_id == org_id,
            AssetPerformanceSummary.asset_id == asset_id,
            AssetPerformanceSummary.component_role == component_role,
        )
        .one_or_none()
    )
    if summary is not None:
        return summary
    summary = AssetPerformanceSummary(
        org_id=org_id,
        asset_id=asset_id,
        component_role=component_role,
    )
    db.add(summary)
    return summary


def _get_or_create_combination_summary(
    db: Session,
    *,
    org_id: uuid.UUID,
    usages: Sequence[AssetUsage],
) -> AssetCombinationPerformance:
    key = _combination_key(usages)
    summary = (
        db.query(AssetCombinationPerformance)
        .filter(
            AssetCombinationPerformance.org_id == org_id,
            AssetCombinationPerformance.combination_key == key,
        )
        .one_or_none()
    )
    if summary is not None:
        return summary
    ordered = sorted(
        usages,
        key=lambda usage: (usage.component_role or usage.usage_role, usage.asset_id.hex),
    )
    summary = AssetCombinationPerformance(
        org_id=org_id,
        combination_key=key,
        component_roles=[usage.component_role or usage.usage_role for usage in ordered],
        asset_ids=[str(usage.asset_id) for usage in ordered],
    )
    db.add(summary)
    return summary


def _apply_metric_sample(
    summary: AssetPerformanceSummary | AssetCombinationPerformance,
    *,
    metrics: Mapping[str, float],
    captured_at: datetime,
) -> None:
    sample_count = summary.sample_count + 1
    totals = {str(key): float(value) for key, value in dict(summary.metric_totals or {}).items()}
    for key, value in metrics.items():
        totals[key] = totals.get(key, 0.0) + float(value)
    summary.sample_count = sample_count
    summary.metric_totals = totals
    summary.metric_averages = {key: value / sample_count for key, value in totals.items()}
    summary.last_metric_at = captured_at
    summary.attribution_note = ATTRIBUTION_NOTE


def _numeric_metrics(metrics: Mapping[str, Any]) -> dict[str, float]:
    numeric: dict[str, float] = {}
    for key, value in metrics.items():
        if isinstance(value, bool) or not isinstance(value, int | float):
            continue
        numeric[str(key)] = float(value)
    return numeric


def _reel_id_from_metric(db: Session, metric: ReelMetric) -> uuid.UUID | None:
    run = db.get(Run, metric.run_id)
    if run is None:
        return None
    for payload in (run.input_params, run.output_payload or {}):
        value = _mapping_value(payload, "reel_id")
        if value is None:
            continue
        try:
            return uuid.UUID(str(value))
        except ValueError:
            continue
    return None


def _mapping_value(value: Mapping[str, Any], key: str) -> Any:
    candidate = value.get(key)
    if candidate is not None:
        return candidate
    for child in value.values():
        if isinstance(child, Mapping):
            found = _mapping_value(cast(Mapping[str, Any], child), key)
            if found is not None:
                return found
    return None


def _usage_combinations(
    usages: Sequence[AssetUsage],
    *,
    sizes: Sequence[int],
) -> list[tuple[AssetUsage, ...]]:
    distinct_usages = list(
        {
            (usage.asset_id, usage.component_role or usage.usage_role): usage
            for usage in usages
        }.values()
    )
    combinations: list[tuple[AssetUsage, ...]] = []
    for size in sizes:
        if size < 2:
            continue
        combinations.extend(itertools.combinations(distinct_usages, size))
    return combinations


def _combination_key(usages: Sequence[AssetUsage]) -> str:
    parts = sorted(
        f"{usage.component_role or usage.usage_role}:{usage.asset_id}" for usage in usages
    )
    return "|".join(parts)
