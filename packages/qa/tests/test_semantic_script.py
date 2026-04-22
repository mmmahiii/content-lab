from __future__ import annotations

from typing import Any

from content_lab_core.types import QAVerdict
from content_lab_qa import (
    SEMANTIC_SCRIPT_GATE_NAME,
    SemanticScriptQARequest,
    evaluate_semantic_script,
)


def _strong_script() -> dict[str, Any]:
    return {
        "hook_text": "You can fix tight hips in 45 seconds.",
        "duration_seconds": 12,
        "spoken_script": [
            {
                "start_seconds": 0,
                "end_seconds": 3,
                "narration": "Tight hips come from sitting, not from bad posture.",
            },
            {
                "start_seconds": 3,
                "end_seconds": 8,
                "narration": "Do these three controlled rotations before your first meeting.",
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
                "end_seconds": 3,
                "text": "Tight hips? Try 45 seconds.",
                "emphasis": "hook",
            },
            {
                "start_seconds": 3,
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
        "caption_variants": [
            {"variant": "short", "text": "Tight hips? 45 seconds, three rotations."},
        ],
    }


def _strong_scene_plan() -> dict[str, Any]:
    return {
        "duration_seconds": 12,
        "scenes": [
            {
                "scene_id": "s1",
                "purpose": "hook",
                "start_seconds": 0,
                "end_seconds": 3,
                "visual_intent": "Tight close-up of hips releasing during a controlled rotation.",
                "shot_guidance": "Tight close-up on the rotation.",
                "overlay_role": "hook",
                "overlay_text": "Tight hips? Try 45 seconds.",
            },
            {
                "scene_id": "s2",
                "purpose": "setup",
                "start_seconds": 3,
                "end_seconds": 6,
                "visual_intent": "Show seated desk posture to frame the problem.",
                "shot_guidance": "Medium shot at the desk.",
                "overlay_role": "context",
            },
            {
                "scene_id": "s3",
                "purpose": "value",
                "start_seconds": 6,
                "end_seconds": 9,
                "visual_intent": "Demonstrate the three-rotation drill clearly.",
                "shot_guidance": "Wide then close on hips.",
                "overlay_role": "emphasis",
                "overlay_text": "Three controlled rotations",
            },
            {
                "scene_id": "s4",
                "purpose": "payoff",
                "start_seconds": 9,
                "end_seconds": 11,
                "visual_intent": "Reveal the improved range of motion.",
                "shot_guidance": "Hold the wider rotation.",
                "overlay_role": "emphasis",
            },
            {
                "scene_id": "s5",
                "purpose": "close",
                "start_seconds": 11,
                "end_seconds": 12,
                "visual_intent": "End on a confident beat and CTA.",
                "shot_guidance": "Clean final frame.",
                "overlay_role": "cta",
                "overlay_text": "Follow for the next routine",
            },
        ],
    }


def _strong_brief() -> dict[str, Any]:
    return {
        "title": "45-second hip reset",
        "content_pillar": "mobility",
        "primary_call_to_action": "Follow for the next routine",
    }


def test_semantic_script_qa_passes_for_strong_content() -> None:
    report = evaluate_semantic_script(
        SemanticScriptQARequest(
            script=_strong_script(),
            scene_plan=_strong_scene_plan(),
            brief=_strong_brief(),
        )
    )

    assert report.verdict == QAVerdict.PASS
    assert report.passed is True
    assert report.findings == []
    assert report.failure_reasons == []
    assert report.gate_name == SEMANTIC_SCRIPT_GATE_NAME


def test_semantic_script_qa_accepts_plain_mapping() -> None:
    report = evaluate_semantic_script(
        {
            "script": _strong_script(),
            "scene_plan": _strong_scene_plan(),
            "brief": _strong_brief(),
        }
    )
    assert report.verdict == QAVerdict.PASS


def test_semantic_script_qa_fails_on_incomplete_hook_ending_with_connector() -> None:
    script = _strong_script()
    script["hook_text"] = "You can fix tight hips in"

    report = evaluate_semantic_script(
        SemanticScriptQARequest(
            script=script,
            scene_plan=_strong_scene_plan(),
            brief=_strong_brief(),
        )
    )

    assert report.verdict == QAVerdict.FAIL
    codes = [finding.code for finding in report.findings]
    assert "incomplete_hook" in codes
    assert any("connector" in reason.lower() for reason in report.failure_reasons)


def test_semantic_script_qa_fails_on_hook_ending_with_colon() -> None:
    script = _strong_script()
    script["hook_text"] = "Quick mobility fix:"

    report = evaluate_semantic_script(
        SemanticScriptQARequest(script=script, scene_plan=_strong_scene_plan())
    )

    assert report.verdict == QAVerdict.FAIL
    codes = [finding.code for finding in report.findings]
    assert "incomplete_hook" in codes


def test_semantic_script_qa_fails_on_generic_meta_text() -> None:
    script = _strong_script()
    script["spoken_script"][0]["narration"] = "Insert hook here."

    report = evaluate_semantic_script(
        SemanticScriptQARequest(script=script, scene_plan=_strong_scene_plan())
    )

    assert report.verdict == QAVerdict.FAIL
    codes = [finding.code for finding in report.findings]
    assert "meta_placeholder" in codes


def test_semantic_script_qa_fails_on_low_information_overlays() -> None:
    script = _strong_script()
    script["overlay_timeline"] = [
        {"start_seconds": 0, "end_seconds": 3, "text": "Wow", "emphasis": "hook"},
        {"start_seconds": 3, "end_seconds": 6, "text": "OK", "emphasis": "value"},
        {"start_seconds": 6, "end_seconds": 9, "text": "Amazing", "emphasis": "value"},
        {"start_seconds": 9, "end_seconds": 12, "text": "Yes", "emphasis": "cta"},
    ]

    report = evaluate_semantic_script(
        SemanticScriptQARequest(script=script, scene_plan=_strong_scene_plan())
    )

    assert report.verdict == QAVerdict.FAIL
    codes = [finding.code for finding in report.findings]
    assert "low_information_overlays" in codes


def test_semantic_script_qa_fails_on_cta_heavy_weak_script() -> None:
    script = _strong_script()
    script["spoken_script"] = [
        {
            "start_seconds": 0,
            "end_seconds": 4,
            "narration": "Follow us for more.",
        },
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
    ]

    report = evaluate_semantic_script(
        SemanticScriptQARequest(script=script, scene_plan=_strong_scene_plan())
    )

    assert report.verdict == QAVerdict.FAIL
    codes = [finding.code for finding in report.findings]
    assert "cta_heavy_script" in codes
    assert any(
        "cta" in reason.lower() and "content" in reason.lower() for reason in report.failure_reasons
    )


def test_semantic_script_qa_flags_scene_plan_without_hook_opening() -> None:
    scene_plan = _strong_scene_plan()
    scene_plan["scenes"][0]["purpose"] = "setup"

    report = evaluate_semantic_script(
        SemanticScriptQARequest(
            script=_strong_script(),
            scene_plan=scene_plan,
            brief=_strong_brief(),
        )
    )

    assert report.verdict == QAVerdict.FAIL
    codes = [finding.code for finding in report.findings]
    assert "scene_plan_starts_without_hook" in codes


def test_semantic_script_qa_warns_on_sparse_scene_plan_with_no_cta_close() -> None:
    script = _strong_script()
    script["overlay_timeline"] = [
        {
            "start_seconds": 0,
            "end_seconds": 6,
            "text": "Tight hips? Try 45 seconds.",
            "emphasis": "hook",
        },
        {
            "start_seconds": 6,
            "end_seconds": 12,
            "text": "Three controlled rotations",
            "emphasis": "value",
        },
    ]
    scene_plan = {
        "duration_seconds": 12,
        "scenes": [
            {
                "scene_id": "s1",
                "purpose": "hook",
                "start_seconds": 0,
                "end_seconds": 6,
                "visual_intent": "Tight close-up of rotation.",
                "shot_guidance": "Close-up on hips.",
                "overlay_role": "hook",
                "overlay_text": "Tight hips? Try 45 seconds.",
            },
            {
                "scene_id": "s2",
                "purpose": "close",
                "start_seconds": 6,
                "end_seconds": 12,
                "visual_intent": "End with the proof of improvement.",
                "shot_guidance": "Hold the wider rotation.",
                "overlay_role": "context",
            },
        ],
    }

    report = evaluate_semantic_script(
        SemanticScriptQARequest(
            script=script,
            scene_plan=scene_plan,
            brief=_strong_brief(),
        )
    )

    assert report.verdict == QAVerdict.WARN
    codes = [finding.code for finding in report.findings]
    assert "sparse_scene_plan" in codes
    assert "scene_missing_cta_close" in codes


def test_semantic_script_qa_as_qa_result_flattens_findings() -> None:
    script = _strong_script()
    script["hook_text"] = "Quick tip:"

    report = evaluate_semantic_script(
        SemanticScriptQARequest(script=script, scene_plan=_strong_scene_plan())
    )
    qa_result = report.as_qa_result()

    assert qa_result.gate_name == SEMANTIC_SCRIPT_GATE_NAME
    assert qa_result.verdict == QAVerdict.FAIL
    findings = qa_result.details["findings"]
    assert isinstance(findings, list)
    assert any(item["code"] == "incomplete_hook" for item in findings)
    assert qa_result.details["failure_reasons"] == report.failure_reasons


def test_semantic_script_qa_reports_missing_hook_when_empty() -> None:
    script = _strong_script()
    script["hook_text"] = "   "

    report = evaluate_semantic_script(SemanticScriptQARequest(script=script))

    assert report.verdict == QAVerdict.FAIL
    codes = [finding.code for finding in report.findings]
    assert "missing_hook" in codes


def test_semantic_script_qa_handles_empty_spoken_script() -> None:
    script = _strong_script()
    script["spoken_script"] = []

    report = evaluate_semantic_script(SemanticScriptQARequest(script=script))

    assert report.verdict == QAVerdict.FAIL
    codes = [finding.code for finding in report.findings]
    assert "empty_spoken_script" in codes
