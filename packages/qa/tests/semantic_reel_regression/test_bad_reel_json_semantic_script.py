"""Regression: ``evaluate_semantic_script`` on JSON bad-reel bundles (phase-1 scope only)."""

from __future__ import annotations

import pytest
from tests.fixtures.bad_reels.loader import (
    expected_outcome,
    list_semantic_script_regression_case_ids,
    load_bad_reel_case,
)

from content_lab_qa import SemanticScriptQARequest, evaluate_semantic_script


@pytest.mark.semantic_reel_regression
@pytest.mark.parametrize("case_id", list_semantic_script_regression_case_ids())
def test_bad_reel_fixture_respects_semantic_script_contract(case_id: str) -> None:
    bundle = load_bad_reel_case(case_id)
    exp = expected_outcome(case_id)["semantic_script"]
    assert isinstance(exp, dict)

    report = evaluate_semantic_script(
        SemanticScriptQARequest(
            script=bundle["script"],
            scene_plan=bundle.get("scene_plan"),
            brief=bundle.get("brief"),
        )
    )

    if (blocked := exp.get("must_not_verdict")) is not None:
        assert report.verdict.value != str(blocked)

    if "verdicts_allowed" in exp:
        allowed: object = exp["verdicts_allowed"]
        assert isinstance(allowed, list)
        assert report.verdict.value in (str(x) for x in allowed)

    required_codes = exp.get("must_include_finding_codes")
    if required_codes is not None:
        assert isinstance(required_codes, list)
        codes = {f.code for f in report.findings}
        for code in required_codes:
            assert str(code) in codes
