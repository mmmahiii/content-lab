"""Regression for the common 'nonsense reel' class: structurally presentable, semantically empty/spammy.

This targets :func:`content_lab_qa.evaluate_semantic_script` only (no format/Mux, no alignment),
matching the live orchestrator's highest-risk false-positive pattern.
"""

from __future__ import annotations

import pytest

from content_lab_core.types import QAVerdict
from content_lab_qa import SemanticScriptQARequest, evaluate_semantic_script

# Minimal overlays so CTA heuristics are about spoken lines, not missing-overlay failures.


def _weak_cta_narration_script() -> dict:
    return {
        "hook_text": "Quick fix:",
        "duration_seconds": 12,
        "spoken_script": [
            {"start_seconds": 0, "end_seconds": 4, "narration": "Follow for more."},
            {
                "start_seconds": 4,
                "end_seconds": 8,
                "narration": "Comment below if you liked this.",
            },
            {
                "start_seconds": 8,
                "end_seconds": 12,
                "narration": "Save this for later and share this.",
            },
        ],
        "overlay_timeline": [
            {"start_seconds": 0, "end_seconds": 4, "text": "More", "emphasis": "hook"},
            {"start_seconds": 4, "end_seconds": 8, "text": "Comment", "emphasis": "value"},
            {"start_seconds": 8, "end_seconds": 12, "text": "Save", "emphasis": "cta"},
        ],
        "caption_variants": [{"variant": "short", "text": "ok"}],
    }


def _strong_viewer_script() -> dict:
    return {
        "hook_text": "You can fix tight hips in 45 seconds.",
        "duration_seconds": 12,
        "spoken_script": [
            {
                "start_seconds": 0,
                "end_seconds": 4,
                "narration": "Tight hips usually come from sitting, not bad posture.",
            },
            {
                "start_seconds": 4,
                "end_seconds": 8,
                "narration": "Do these three controlled hip rotations before meetings.",
            },
            {
                "start_seconds": 8,
                "end_seconds": 12,
                "narration": "Follow for the next routine to loosen up fast.",
            },
        ],
        "overlay_timeline": [
            {
                "start_seconds": 0,
                "end_seconds": 4,
                "text": "Tight hips? Try 45 seconds.",
                "emphasis": "hook",
            },
            {
                "start_seconds": 4,
                "end_seconds": 8,
                "text": "Three controlled rotations",
                "emphasis": "value",
            },
            {
                "start_seconds": 8,
                "end_seconds": 12,
                "text": "Follow for the next routine",
                "emphasis": "cta",
            },
        ],
        "caption_variants": [{"variant": "short", "text": "Tight hips? 45s, three rotations."}],
    }


def _empty_hook_script() -> dict:
    return {
        "hook_text": "",
        "duration_seconds": 6,
        "spoken_script": [
            {"start_seconds": 0, "end_seconds": 3, "narration": "Some line"},
            {"start_seconds": 3, "end_seconds": 6, "narration": "Another line."},
        ],
        "overlay_timeline": [
            {"start_seconds": 0, "end_seconds": 2, "text": "x", "emphasis": "hook"},
        ],
        "caption_variants": [{"variant": "short", "text": "c"}],
    }


@pytest.mark.semantic_reel_regression
def test_cta_and_hook_spam_fails_with_documented_finding_codes() -> None:
    report = evaluate_semantic_script(
        SemanticScriptQARequest(script=_weak_cta_narration_script(), scene_plan=None, brief=None)
    )
    assert report.verdict == QAVerdict.FAIL
    codes = {f.code for f in report.findings}
    assert "incomplete_hook" in codes
    assert "cta_heavy_script" in codes


@pytest.mark.semantic_reel_regression
def test_missing_hook_fails() -> None:
    report = evaluate_semantic_script(
        SemanticScriptQARequest(script=_empty_hook_script(), scene_plan=None, brief=None)
    )
    assert report.verdict == QAVerdict.FAIL
    codes = {f.code for f in report.findings}
    assert "missing_hook" in codes


@pytest.mark.semantic_reel_regression
def test_strong_mobility_script_does_not_fail_semantic_gate() -> None:
    report = evaluate_semantic_script(
        SemanticScriptQARequest(script=_strong_viewer_script(), scene_plan=None, brief=None)
    )
    assert report.verdict != QAVerdict.FAIL
