from __future__ import annotations

from content_lab_qa.alignment import evaluate_alignment_qa


def test_intentionally_mismatched_brief_versus_packaging_copy_fails() -> None:
    """Regression guard: the QA payload must flag obvious brief vs caption/prompt drift."""

    brief = {
        "title": "Morning coffee barista ritual at the roastery",
        "narrative_goal": (
            "Walk through an artisan roastery and barista morning routine that celebrates "
            "fresh beans, steaming milk, and community coffee culture."
        ),
        "content_pillar": "roastery_coffee",
        "tags": ["#coffee", "#roastery", "#barista"],
    }
    # Everything downstream talks about a completely different vertical.
    off_topic = (
        "home rooftop solar tax credits, inverter sizing, and battery backup incentives for "
        "residential customers exploring electrification"
    )
    script = {
        "schema_version": "phase_1",
        "provider_name": "test",
        "generator_path": "test",
        "brief_title": brief["title"],
        "duration_seconds": 12,
        "hook_text": off_topic,
        "spoken_script": [
            {
                "start_seconds": 0,
                "end_seconds": 4,
                "narration": off_topic,
            }
        ],
        "overlay_timeline": [
            {
                "start_seconds": 0,
                "end_seconds": 2,
                "text": "Solar tax credits",
                "emphasis": "hook",
            }
        ],
        "caption_variants": [
            {"variant": "short", "text": "Solar and battery incentives explained."},
            {
                "variant": "standard",
                "text": "How homeowners claim rooftop solar tax credits and incentives.",
            },
        ],
        "hashtags": ["#solar", "#incentives"],
    }
    scene_plan = {
        "schema_version": "phase_1",
        "compiler_name": "test",
        "brief_title": brief["title"],
        "duration_seconds": 12,
        "scenes": [
            {
                "scene_id": "s1",
                "purpose": "hook",
                "start_seconds": 0,
                "end_seconds": 3,
                "visual_intent": "aerial view of roof solar array at sunset with inverter box",
                "shot_guidance": "slow drone pullback",
                "overlay_role": "hook",
                "overlay_text": "Solar made simple",
                "narration_refs": [0],
            },
            {
                "scene_id": "s2",
                "purpose": "value",
                "start_seconds": 3,
                "end_seconds": 12,
                "visual_intent": "installer explains battery incentives at kitchen table",
                "shot_guidance": "over-shoulder to documents",
                "overlay_role": "context",
                "overlay_text": "Credits and rebates",
                "narration_refs": [0],
            },
        ],
    }
    compiled_prompt = {
        "prompt": (
            "cinematic 9:16 vertical footage of home rooftop solar array at golden hour, "
            "inverter details, and installer reviewing incentive paperwork; photoreal, bright"
        )
    }
    report = evaluate_alignment_qa(
        brief=brief,
        script=script,
        scene_plan=scene_plan,
        compiled_prompt=compiled_prompt,
        editing={"cover_frame_timestamp_seconds": 0.4, "duration_seconds": 12.0},
    )
    assert report.blocks_readiness
    assert any("messaging" in f.code for f in report.findings)
    assert any("asset_prompt" in f.code for f in report.findings)
