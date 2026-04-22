from __future__ import annotations

from content_lab_core.types import QAVerdict
from content_lab_qa.alignment import AlignmentQAConstraints, evaluate_alignment_qa


def _base_scene_plan(*, with_hook: bool = True) -> dict:
    if with_hook:
        return {
            "schema_version": "phase_1",
            "compiler_name": "test",
            "brief_title": "Test",
            "duration_seconds": 12,
            "scenes": [
                {
                    "scene_id": "s1",
                    "purpose": "hook",
                    "start_seconds": 0,
                    "end_seconds": 3,
                    "visual_intent": "macro coffee beans and steam in warm light",
                    "shot_guidance": "close handheld dolly in",
                    "overlay_role": "hook",
                    "overlay_text": "Fresh roast",
                    "narration_refs": [0],
                },
                {
                    "scene_id": "s2",
                    "purpose": "value",
                    "start_seconds": 3,
                    "end_seconds": 12,
                    "visual_intent": "barista hand pours latte art",
                    "shot_guidance": "slow top-down",
                    "overlay_role": "emphasis",
                    "overlay_text": "Learn the pour",
                    "narration_refs": [1],
                },
            ],
        }
    return {
        "schema_version": "phase_1",
        "compiler_name": "test",
        "brief_title": "Test",
        "duration_seconds": 12,
        "scenes": [],
    }


def _script(
    *, hook: str, narrations: list[str], captions: list[tuple[str, str]], prompt_text: str
) -> dict:
    spoken = [
        {
            "start_seconds": index * 2,
            "end_seconds": index * 2 + 2,
            "narration": text,
        }
        for index, text in enumerate(narrations)
    ]
    caption_variants = [{"variant": name, "text": body} for name, body in captions]
    return {
        "schema_version": "phase_1",
        "provider_name": "test",
        "generator_path": "test",
        "brief_title": "Test",
        "duration_seconds": 12,
        "hook_text": hook,
        "spoken_script": spoken,
        "overlay_timeline": [
            {
                "start_seconds": 0,
                "end_seconds": 2,
                "text": "Fresh roast",
                "emphasis": "hook",
            }
        ],
        "caption_variants": caption_variants,
        "hashtags": [],
    }


def test_alignment_passes_when_copy_prompt_and_hook_align() -> None:
    lead = "Highlight artisan roastery barista workflows for morning customers."
    prompt = (
        "macro coffee beans, steam, warm roastery light, then barista hand pours latte art "
        "in slow top-down; cinematic, vertical 9:16"
    )
    brief = {
        "title": "Roastery workflow",
        "narrative_goal": lead,
        "content_pillar": "roastery",
        "tags": ["#coffee", "#roastery"],
    }
    script = _script(
        hook="The roastery barista workflow starts with fresh beans and steam",
        narrations=["We film the barista in action for morning service"],
        captions=[
            ("short", "Morning roastery barista workflow in one reel."),
            ("standard", "See how the barista steams, pours, and serves morning customers."),
        ],
        prompt_text=prompt,
    )
    report = evaluate_alignment_qa(
        brief=brief,
        script=script,
        scene_plan=_base_scene_plan(),
        compiled_prompt={"prompt": prompt},
        editing={"cover_frame_timestamp_seconds": 0.4, "duration_seconds": 12.0},
    )
    assert report.verdict in (QAVerdict.PASS, QAVerdict.WARN)
    assert not report.blocks_readiness


def test_alignment_fails_on_mismatched_messaging() -> None:
    brief = {
        "title": "Coffee ritual",
        "narrative_goal": "artisan roastery and barista morning ritual",
        "content_pillar": "coffee",
    }
    off_topic = "tax credits and rooftop solar panel installation for homeowners"
    script = _script(
        hook=off_topic,
        narrations=[off_topic],
        captions=[("short", off_topic), ("standard", off_topic)],
        prompt_text=off_topic,
    )
    report = evaluate_alignment_qa(
        brief=brief,
        script=script,
        scene_plan=_base_scene_plan(),
        compiled_prompt={"prompt": off_topic},
        editing=None,
    )
    assert report.verdict == QAVerdict.FAIL
    assert report.blocks_readiness
    codes = {f.code for f in report.findings}
    assert "messaging_drift" in codes
    assert "asset_prompt_drift" in codes


def test_alignment_skips_on_thin_brief() -> None:
    report = evaluate_alignment_qa(
        brief={"title": "ab", "narrative_goal": "so"},
        script=_script(
            hook="any text",
            narrations=["more"],
            captions=[("short", "x y z unrelated story")],
            prompt_text="unrelated",
        ),
        scene_plan=_base_scene_plan(),
        compiled_prompt={"prompt": "x"},
    )
    assert report.skipped
    assert report.verdict == QAVerdict.SKIP


def test_alignment_warns_on_cover_frame_outside_hook() -> None:
    lead = "Showcase artisan roastery barista workflows for community coffee lovers"
    on_topic = "roastery barista steams and pours in warm morning service"
    prompt = "macro coffee roastery barista and latte art, cinematic vertical 9:16"
    brief = {
        "title": "Roastery",
        "narrative_goal": lead,
        "content_pillar": "coffee",
    }
    script = _script(
        hook=on_topic,
        narrations=[on_topic],
        captions=[("short", on_topic), ("standard", on_topic)],
        prompt_text=prompt,
    )
    report = evaluate_alignment_qa(
        brief=brief,
        script=script,
        scene_plan=_base_scene_plan(),
        compiled_prompt={"prompt": prompt},
        editing={"cover_frame_timestamp_seconds": 7.0, "duration_seconds": 12.0},
        constraints=AlignmentQAConstraints(hook_cover_slack_seconds=0.5),
    )
    assert report.verdict == QAVerdict.WARN
    assert any(f.code == "cover_framing_outside_hook" for f in report.findings)


def test_caption_intent_warn_when_captions_lag() -> None:
    lead = "roastery barista training pour workflow for morning rush"
    prompt = "barista at roastery trains pour workflow, steam and espresso close ups"
    brief = {
        "title": "Barista",
        "narrative_goal": lead,
        "content_pillar": "coffee",
    }
    on_script = "roastery barista training pour for morning bar rush service"
    solar_caption = "solar install discounts and home battery incentives"
    script = _script(
        hook=on_script,
        narrations=[on_script],
        captions=[("short", solar_caption), ("standard", solar_caption)],
        prompt_text=prompt,
    )
    report = evaluate_alignment_qa(
        brief=brief,
        script=script,
        scene_plan=_base_scene_plan(),
        compiled_prompt={"prompt": prompt},
    )
    assert any(f.code == "caption_intent_gap" and f.severity == "warn" for f in report.findings)
