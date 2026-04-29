from __future__ import annotations

from typing import Any, cast

import pytest

from content_lab_core.types import QAVerdict
from content_lab_editing.overlays import OverlayLayoutError

from content_lab_qa.overlay import default_overlay_stack_policy_for_template, evaluate_overlay_text_fidelity_qa


def _script_with_overlays() -> dict[str, Any]:
    return {
        "duration_seconds": 12,
        "overlay_timeline": [
            {
                "start_seconds": 0,
                "end_seconds": 4,
                "text": "One thing you can do today",
                "emphasis": "hook",
            },
            {
                "start_seconds": 4,
                "end_seconds": 12,
                "text": "Move before your meeting",
                "emphasis": "value",
            },
        ],
    }


def _matching_manifest_for_script(script: dict[str, Any]) -> list[dict[str, Any]]:
    from content_lab_editing.overlay_layout import build_overlay_render_manifest_for_qa
    from content_lab_editing.overlays import normalize_overlay_timeline

    overlays = normalize_overlay_timeline(
        script["overlay_timeline"],
        clip_duration_seconds=float(script["duration_seconds"]),
    )
    rows, _safe = build_overlay_render_manifest_for_qa(
        overlays,
        frame_width=1080,
        frame_height=1920,
    )
    return rows


def _editing_stub(script: dict[str, Any]) -> dict[str, Any]:
    from content_lab_editing.overlay_layout import build_overlay_render_manifest_for_qa
    from content_lab_editing.overlays import normalize_overlay_timeline
    from content_lab_qa.overlay import default_overlay_stack_policy_for_template

    overlays = normalize_overlay_timeline(
        script["overlay_timeline"],
        clip_duration_seconds=float(script["duration_seconds"]),
    )
    rows, safe = build_overlay_render_manifest_for_qa(
        overlays,
        frame_width=1080,
        frame_height=1920,
    )
    return {
        "duration_seconds": float(script["duration_seconds"]),
        "editorial_template_id": None,
        "overlay_stack_policy": default_overlay_stack_policy_for_template(None),
        "overlay_render_manifest": rows,
        "overlay_safe_area": safe,
    }


def test_overlay_fidelity_passes_when_manifest_matches_plan() -> None:
    script = _script_with_overlays()
    report = evaluate_overlay_text_fidelity_qa(
        script=script,
        editing=_editing_stub(script),
    )
    assert report.verdict == QAVerdict.PASS
    assert not report.blocks_readiness


def test_overlay_fidelity_fails_when_planned_hook_missing_from_manifest() -> None:
    script = _script_with_overlays()
    editing = _editing_stub(script)
    editing["overlay_render_manifest"] = _matching_manifest_for_script(script)[1:]
    report = evaluate_overlay_text_fidelity_qa(
        script=script,
        editing=editing,
    )
    assert report.verdict == QAVerdict.FAIL
    codes = {f.code for f in report.findings}
    assert "overlay_text_count_mismatch" in codes


def test_overlay_fidelity_fails_on_substituted_word() -> None:
    script = _script_with_overlays()
    editing = _editing_stub(script)
    manifest = cast(list[dict[str, Any]], editing["overlay_render_manifest"])
    manifest[1] = {
        **manifest[1],
        "text": "Meeting before your move",
    }
    report = evaluate_overlay_text_fidelity_qa(
        script=script,
        editing=editing,
    )
    assert report.verdict == QAVerdict.FAIL
    assert any(f.code == "overlay_text_mismatch" for f in report.findings)
    detail = cast(dict[str, Any], report.findings[0].details)
    assert detail.get("planned_text") == "Move before your meeting"
    assert detail.get("rendered_text") == "Meeting before your move"
    assert detail.get("planned_role") == "value"


def test_overlay_fidelity_fails_when_manifest_emitted_but_none_planned() -> None:
    script: dict[str, Any] = {"duration_seconds": 12, "overlay_timeline": []}
    report = evaluate_overlay_text_fidelity_qa(
        script=script,
        editing={
            "duration_seconds": 12.0,
            "overlay_render_manifest": [{"text": "orphan", "start_seconds": 0.0, "end_seconds": 2.0}],
        },
    )
    assert report.verdict == QAVerdict.FAIL


def test_overlay_fidelity_requires_manifest_when_overlays_planned() -> None:
    script = _script_with_overlays()
    report = evaluate_overlay_text_fidelity_qa(
        script=script,
        editing={"duration_seconds": 12.0},
    )
    assert report.verdict == QAVerdict.FAIL
    assert any(f.code == "overlay_manifest_missing" for f in report.findings)


def test_overlay_qa_fails_when_safe_area_metadata_missing() -> None:
    script = _script_with_overlays()
    editing = _editing_stub(script)
    del editing["overlay_safe_area"]
    report = evaluate_overlay_text_fidelity_qa(script=script, editing=editing)
    assert report.verdict == QAVerdict.FAIL
    assert any(f.code == "overlay_safe_area_missing" for f in report.findings)


def test_overlay_qa_fails_when_hook_layout_reports_safe_area_violation() -> None:
    script = _script_with_overlays()
    editing = _editing_stub(script)
    manifest = cast(list[dict[str, Any]], editing["overlay_render_manifest"])
    layout = cast(dict[str, Any], manifest[0]["layout"])
    layout["layout_verified"] = True
    layout["out_of_bounds"] = False
    layout["fits_safe_area"] = False
    layout["did_not_fit_horizontally"] = False
    layout["font_unreadably_small"] = False
    report = evaluate_overlay_text_fidelity_qa(script=script, editing=editing)
    assert report.verdict == QAVerdict.FAIL
    violated = [f for f in report.findings if f.code == "overlay_safe_area_violation"]
    assert violated
    assert cast(dict[str, Any], violated[0].details).get("planned_role") == "hook"


def test_overlay_qa_fails_on_extremely_wide_hook_text() -> None:
    wide = "WORD " * 40
    script: dict[str, Any] = {
        "duration_seconds": 12,
        "overlay_timeline": [
            {
                "start_seconds": 0,
                "end_seconds": 4,
                "text": wide,
                "emphasis": "hook",
            },
        ],
    }
    with pytest.raises(OverlayLayoutError) as exc:
        _editing_stub(script)
    assert exc.value.code == "hook_unreadable"


def _overlapping_script_both_bottom() -> dict[str, Any]:
    return {
        "duration_seconds": 12,
        "overlay_timeline": [
            {
                "start_seconds": 0,
                "end_seconds": 8,
                "text": "First beat",
                "emphasis": "hook",
                "vertical_align": "bottom",
            },
            {
                "start_seconds": 4,
                "end_seconds": 12,
                "text": "Second beat",
                "emphasis": "value",
                "vertical_align": "bottom",
            },
        ],
    }


def test_overlay_qa_fails_on_temporal_overlap() -> None:
    script = _overlapping_script_both_bottom()
    report = evaluate_overlay_text_fidelity_qa(script=script, editing=_editing_stub(script))
    assert report.verdict == QAVerdict.FAIL
    assert any(f.code == "overlay_time_collision" for f in report.findings)
    collision = next(f for f in report.findings if f.code == "overlay_time_collision")
    detail = cast(dict[str, Any], collision.details)
    assert detail.get("stack_policy_mode") == "no_time_overlap"
    assert "overlay_a" in detail and "overlay_b" in detail


def test_overlay_qa_allows_top_bottom_overlap_with_separate_vertical_policy() -> None:
    script: dict[str, Any] = {
        "duration_seconds": 12,
        "overlay_timeline": [
            {
                "start_seconds": 0,
                "end_seconds": 8,
                "text": "Top cue",
                "emphasis": "hook",
                "vertical_align": "top",
            },
            {
                "start_seconds": 4,
                "end_seconds": 12,
                "text": "Bottom cue",
                "emphasis": "value",
                "vertical_align": "bottom",
            },
        ],
    }
    editing = _editing_stub(script)
    editing["overlay_stack_policy"] = {"mode": "separate_vertical_regions", "source": "test"}
    report = evaluate_overlay_text_fidelity_qa(script=script, editing=editing)
    assert report.verdict == QAVerdict.PASS


def test_overlay_qa_same_vertical_overlap_fails_even_with_separate_vertical_policy() -> None:
    script = _overlapping_script_both_bottom()
    editing = _editing_stub(script)
    editing["overlay_stack_policy"] = {"mode": "separate_vertical_regions", "source": "test"}
    report = evaluate_overlay_text_fidelity_qa(script=script, editing=editing)
    assert report.verdict == QAVerdict.FAIL
    assert any(f.code == "overlay_time_collision" for f in report.findings)


def test_default_stack_policy_maps_cta_templates() -> None:
    policy = default_overlay_stack_policy_for_template("hook_plus_payoff_v1")
    assert policy["mode"] == "separate_vertical_regions"
    policy_default = default_overlay_stack_policy_for_template("hook_first_v1")
    assert policy_default["mode"] == "no_time_overlap"
