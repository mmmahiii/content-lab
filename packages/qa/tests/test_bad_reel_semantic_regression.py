from __future__ import annotations

import pytest

from content_lab_qa.alignment import evaluate_alignment_qa
from tests.fixtures.bad_reels.loader import expected_outcome, list_case_ids, load_bad_reel_case


@pytest.mark.parametrize("case_id", list_case_ids())
def test_bad_reel_cases_match_expected_alignment_semantics(case_id: str) -> None:
    """Semantic (alignment) expectations: distinct from technical media validity (format gate)."""

    bundle = load_bad_reel_case(case_id)
    exp = expected_outcome(case_id)
    alignment_exp = exp["alignment"]
    report = evaluate_alignment_qa(
        brief=bundle["brief"],
        script=bundle["script"],
        scene_plan=bundle["scene_plan"],
        compiled_prompt=bundle["compiled_prompt"],
        editing=bundle.get("editing"),
    )

    if "verdicts_allowed" in alignment_exp:
        assert report.verdict.value in alignment_exp["verdicts_allowed"]
    else:
        assert report.verdict.value == alignment_exp["verdict"]
    assert report.blocks_readiness is alignment_exp["blocks_readiness"]

    codes = {f.code for f in report.findings}
    severities = {f.severity for f in report.findings}

    if "must_include_fail_codes" in alignment_exp:
        for code in alignment_exp["must_include_fail_codes"]:
            assert code in codes

    if "must_not_include_severities" in alignment_exp:
        for sev in alignment_exp["must_not_include_severities"]:
            assert sev not in severities

    # Technical-vs-semantic: alignment does not "fix" a broken encode; that is format/FFprobe.
    assert exp["failure_domain"] in {"semantic", "none"}


def test_intent_drift_is_semantic_not_technical_label() -> None:
    exp = expected_outcome("intent_drift_solar_mismatch")
    assert exp["failure_domain"] == "semantic"
    assert exp["quality_axis"] == "alignment"
