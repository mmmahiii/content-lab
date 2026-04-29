from __future__ import annotations

from content_lab_creative.trace import build_alignment_context, build_creative_trace
from tests.fixtures.bad_reels.loader import load_bad_reel_case


def test_creative_trace_alignment_context_accepts_baseline_fixture() -> None:
    """Creative layer stays compatible with the shared golden payload shape."""

    bundle = load_bad_reel_case("well_aligned_baseline")
    creative = {
        "brief": bundle["brief"],
        "script": bundle["script"],
        "scene_plan": bundle["scene_plan"],
        "compiled_prompt": bundle["compiled_prompt"],
    }
    ctx = build_alignment_context(creative, editing_output=bundle.get("editing"))
    assert "lead_message" in ctx
    assert "hook_text" in ctx
    assert ctx.get("duration_seconds") == 12.0


def test_latest_trace_golden_fixture_matches_exported_creative_trace_shape() -> None:
    """Regression anchor for packages/qa/tests/fixtures/.../latest_trace_smoke_operations.json."""

    bundle = load_bad_reel_case("latest_trace_smoke_operations")
    creative = {
        "brief": bundle["brief"],
        "script": bundle["script"],
        "script_lint": bundle.get("script_lint", {}),
        "scene_plan": bundle["scene_plan"],
        "compiled_prompt": bundle["compiled_prompt"],
    }
    ctx = build_alignment_context(creative, editing_output=bundle.get("editing"))
    assert ctx["hook_text"] == "The operations reset busy founders can do today"

    trace = build_creative_trace(
        reel_id="reel-latest-trace-fixture",
        run_id="run-latest-trace-fixture",
        creative_output=creative,
    )
    payload = trace.model_dump(mode="json")
    assert payload["artifact_type"] == "creative_trace"
    overlays = payload["script"]["overlay_timeline"]
    assert [o["text"] for o in overlays] == [
        "The operations reset busy founders can do today",
        "operations",
        "One repeatable move",
        "Save this reset",
    ]
    std_cap = next(
        v for v in payload["script"]["caption_variants"] if v.get("variant") == "standard"
    )
    assert "Create a explore" in std_cap["text"]
    assert "Smoke Test Page" in std_cap["text"]
    assert str(bundle["compiled_prompt"]["provider"]) == "fixture"
