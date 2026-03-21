"""Reel/page model invariants (generated vs observed)."""

import pytest
from sqlalchemy.schema import Table

from content_lab_api.models.reel import (
    GENERATED_REEL_STATUSES,
    OBSERVED_REEL_STATUSES,
    GeneratedReelStatus,
    ObservedReelStatus,
    Reel,
    ReelOrigin,
    validate_reel_origin_status,
)


def test_generated_statuses_cover_canonical_lifecycle() -> None:
    expected = {
        "draft",
        "planning",
        "generating",
        "editing",
        "qa",
        "qa_failed",
        "ready",
        "posted",
        "archived",
    }
    assert expected == GENERATED_REEL_STATUSES
    assert {s.value for s in GeneratedReelStatus} == expected


def test_observed_statuses_are_terminal_only() -> None:
    expected = {"active", "removed", "unavailable"}
    assert expected == OBSERVED_REEL_STATUSES
    assert {s.value for s in ObservedReelStatus} == expected


@pytest.mark.parametrize(
    "status",
    sorted(GENERATED_REEL_STATUSES),
)
def test_validate_accepts_generated_pairs(status: str) -> None:
    validate_reel_origin_status(ReelOrigin.GENERATED.value, status)


@pytest.mark.parametrize(
    "status",
    sorted(OBSERVED_REEL_STATUSES),
)
def test_validate_accepts_observed_pairs(status: str) -> None:
    validate_reel_origin_status(ReelOrigin.OBSERVED.value, status)


def test_validate_rejects_pipeline_status_on_observed() -> None:
    with pytest.raises(ValueError, match="observed reel"):
        validate_reel_origin_status(ReelOrigin.OBSERVED.value, "draft")


def test_validate_rejects_observed_status_on_generated() -> None:
    with pytest.raises(ValueError, match="generated reel"):
        validate_reel_origin_status(ReelOrigin.GENERATED.value, "active")


def test_validate_rejects_bad_origin() -> None:
    with pytest.raises(ValueError, match="Invalid reel origin"):
        validate_reel_origin_status("scraped", "active")


def test_reel_table_has_origin_status_checks() -> None:
    table = Reel.__table__
    assert isinstance(table, Table)
    names = {c.name for c in table.constraints if c.name is not None}
    assert "ck_reels_origin" in names
    assert "ck_reels_origin_status" in names
