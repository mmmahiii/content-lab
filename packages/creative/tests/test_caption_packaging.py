from __future__ import annotations

from content_lab_creative.caption_variants import (
    apply_caption_packaging,
    caption_copy_has_severity_fail,
)
from content_lab_creative.posting_plan import (
    PostingPlanFamilyContext,
    PostingPlanPageContext,
    PostingPlanVariantContext,
    build_posting_plan,
    resolve_recommended_caption_for_slots,
)
from content_lab_creative.types import (
    CaptionVariant,
    CaptionVariantName,
    CreativeMode,
    GeneratedScriptOutput,
    OverlayCue,
    PolicyStateDocument,
    ScriptBeat,
    ScriptOverlayEmphasis,
)


def _minimal_script(
    *, caption_texts: list[tuple[CaptionVariantName, str]]
) -> GeneratedScriptOutput:
    return GeneratedScriptOutput(
        provider_name="test",
        generator_path="test",
        brief_title="Mobility",
        duration_seconds=20,
        hook_text="Hook line that is not incomplete here",
        spoken_script=[
            ScriptBeat(
                start_seconds=0, end_seconds=20, narration="Narration line for the test beat only."
            )
        ],
        overlay_timeline=[
            OverlayCue(
                start_seconds=0,
                end_seconds=5,
                text="Hook line",
                emphasis=ScriptOverlayEmphasis.HOOK,
            ),
        ],
        caption_variants=[CaptionVariant(variant=slot, text=text) for slot, text in caption_texts],
    )


def test_filters_bad_caption_preserves_valid() -> None:
    good = "Save this for your next reset."
    bad = "Create a explore reel for Smoke Test Page focused on operations"
    out, meta = apply_caption_packaging(
        _minimal_script(
            caption_texts=[
                (CaptionVariantName.SHORT, good),
                (CaptionVariantName.STANDARD, bad),
            ]
        )
    )
    assert {c.variant for c in out.caption_variants} == {CaptionVariantName.SHORT}
    assert meta["dropped_count"] == 1
    assert "prefilter_caption_lint" in meta
    assert not caption_copy_has_severity_fail(out.caption_variants[0].text)


def test_all_bad_uses_deterministic_fallback() -> None:
    bad = "Create a explore reel for Smoke Test Page"
    out, meta = apply_caption_packaging(
        _minimal_script(
            caption_texts=[
                (CaptionVariantName.SHORT, bad),
                (CaptionVariantName.STANDARD, bad),
            ]
        )
    )
    assert len(out.caption_variants) == 1
    assert out.caption_variants[0].variant is CaptionVariantName.SHORT
    assert meta["used_fallback_caption"] is True
    assert not caption_copy_has_severity_fail(out.caption_variants[0].text)


def test_recommended_caption_falls_back_when_slot_missing() -> None:
    assert (
        resolve_recommended_caption_for_slots(CreativeMode.EXPLOIT, ["engagement", "short"])
        == "engagement"
    )
    assert resolve_recommended_caption_for_slots(CreativeMode.EXPLOIT, ["short"]) == "short"


def test_build_posting_plan_respects_available_slots() -> None:
    plan = build_posting_plan(
        policy=PolicyStateDocument(),
        page=PostingPlanPageContext(page_name="Test"),
        family=PostingPlanFamilyContext(family_name="F", content_pillar="p"),
        mode=CreativeMode.EXPLOIT,
        variant=PostingPlanVariantContext(variant_label="v1"),
        available_caption_variants=["short", "engagement"],
    )
    assert plan.publication.recommended_caption_variant in {"engagement", "short"}
    assert plan.publication.recommended_caption_variant != "standard"
