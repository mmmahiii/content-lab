from __future__ import annotations

from content_lab_creative.trace import build_alignment_context
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
