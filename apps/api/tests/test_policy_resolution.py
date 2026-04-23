"""Unit tests for page policy inheritance resolution."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from content_lab_api.models.policy_state import PolicyState
from content_lab_api.schemas.policy import PolicyStateDocument, dump_policy_state
from content_lab_api.services.policy_resolution import build_page_policy_view

ORG_ID = uuid.uuid4()
PAGE_ID = uuid.uuid4()
_TS = datetime(2026, 4, 9, 10, 0, 0, tzinfo=UTC)


def _row(
    *,
    state: PolicyStateDocument | None = None,
    key: str = "page:test",
) -> PolicyState:
    doc = state or PolicyStateDocument()
    return PolicyState(
        org_id=ORG_ID,
        policy_key=key,
        state=dump_policy_state(doc),
    )


def test_explicit_page_row_wins() -> None:
    page_doc = PolicyStateDocument.model_validate(
        {
            "mode_ratios": {"exploit": 0.5, "explore": 0.2, "mutation": 0.2, "chaos": 0.1},
        }
    )
    global_doc = PolicyStateDocument.model_validate(
        {
            "mode_ratios": {"exploit": 0.1, "explore": 0.5, "mutation": 0.3, "chaos": 0.1},
        }
    )
    page_row = _row(state=page_doc, key=f"page:{PAGE_ID}")
    page_row.id = uuid.uuid4()
    page_row.updated_at = _TS
    global_row = _row(state=global_doc, key="global")
    global_row.id = uuid.uuid4()

    view = build_page_policy_view(
        org_id=ORG_ID,
        page_id=PAGE_ID,
        page_row=page_row,
        global_row=global_row,
    )

    assert view.is_explicit_override is True
    assert view.inherited_from is None
    assert view.id == page_row.id
    assert view.updated_at == _TS
    assert view.state.mode_ratios.exploit == 0.5


def test_inherits_global_when_no_page_row() -> None:
    global_doc = PolicyStateDocument.model_validate(
        {
            "budget": {
                "per_run_usd_limit": 25,
                "daily_usd_limit": 80,
                "monthly_usd_limit": 1600,
            },
        }
    )
    global_row = _row(state=global_doc, key="global")
    global_row.id = uuid.uuid4()
    global_row.updated_at = _TS

    view = build_page_policy_view(
        org_id=ORG_ID,
        page_id=PAGE_ID,
        page_row=None,
        global_row=global_row,
    )

    assert view.is_explicit_override is False
    assert view.inherited_from == "global"
    assert view.id is None
    assert view.updated_at == _TS
    assert view.state.budget.per_run_usd_limit == 25


def test_falls_back_to_defaults_when_no_rows() -> None:
    view = build_page_policy_view(
        org_id=ORG_ID,
        page_id=PAGE_ID,
        page_row=None,
        global_row=None,
    )

    assert view.is_explicit_override is False
    assert view.inherited_from == "default"
    assert view.id is None
    assert view.updated_at is None
    default = PolicyStateDocument()
    assert view.state.model_dump() == default.model_dump()
