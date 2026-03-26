from __future__ import annotations

from content_lab_core.types import Platform
from content_lab_creative.persona import PageConstraints, PageMetadata, PersonaProfile
from content_lab_creative.posting_plan import build_posting_plan, serialize_posting_plan_json
from content_lab_creative.types import CreativeMode, PolicyStateDocument


def _page() -> dict[str, object]:
    return {
        "page_id": "page-123",
        "page_name": "Northwind Fitness",
        "page_metadata": PageMetadata(
            persona=PersonaProfile(
                label="Coach-next-door",
                audience="Busy professionals",
                brand_tone=["direct", "optimistic"],
                content_pillars=["mobility", "strength"],
                differentiators=["Simple progressions"],
                primary_call_to_action="Follow for the next routine",
            ),
            constraints=PageConstraints(
                required_disclosures=["Results vary"],
                prohibited_claims=["Guaranteed transformation"],
                blocked_phrases=["miracle result"],
                allow_direct_cta=False,
                max_hashtags=5,
            ),
        ),
        "target_platforms": [Platform.TIKTOK, Platform.INSTAGRAM],
        "timezone": "America/New_York",
        "locale": "en-US",
    }


def test_build_posting_plan_is_deterministic_and_json_stable() -> None:
    plan_one = build_posting_plan(
        policy=PolicyStateDocument(),
        page=_page(),
        family={
            "family_id": "family-007",
            "family_name": "Mobility Reset",
            "content_pillar": "mobility",
            "metadata": {"series": "weekday", "theme": "desk recovery"},
        },
        mode=CreativeMode.EXPLORE,
        variant={
            "variant_id": "variant-001",
            "variant_label": "A",
            "variant_index": 0,
            "duration_seconds": 30,
        },
    )
    plan_two = build_posting_plan(
        policy=PolicyStateDocument(),
        page={
            **_page(),
            "target_platforms": [Platform.INSTAGRAM, Platform.TIKTOK],
        },
        family={
            "family_id": "family-007",
            "family_name": "Mobility Reset",
            "content_pillar": "mobility",
            "metadata": {"theme": "desk recovery", "series": "weekday"},
        },
        mode="explore",
        variant={
            "variant_id": "variant-001",
            "variant_label": "A",
            "variant_index": 0,
            "duration_seconds": 30,
        },
    )

    assert plan_one.model_dump(mode="json") == plan_two.model_dump(mode="json")
    assert serialize_posting_plan_json(plan_one) == serialize_posting_plan_json(plan_two)
    assert plan_one.publication.posting_method == "manual"
    assert plan_one.publication.approval_required is True
    assert [platform.value for platform in plan_one.publication.target_platforms] == [
        "instagram",
        "tiktok",
    ]
    assert plan_one.compliance.required_disclosures == ["Results vary"]
    assert plan_one.publication.review_focus[-1] == (
        "Avoid direct calls to action in the final posting copy."
    )


def test_build_posting_plan_changes_fingerprint_when_variant_changes() -> None:
    first = build_posting_plan(
        policy=PolicyStateDocument(),
        page=_page(),
        family={
            "family_id": "family-007",
            "family_name": "Mobility Reset",
            "content_pillar": "mobility",
        },
        mode=CreativeMode.EXPLOIT,
        variant={
            "variant_id": "variant-001",
            "variant_label": "A",
            "variant_index": 0,
        },
    )
    second = build_posting_plan(
        policy=PolicyStateDocument(),
        page=_page(),
        family={
            "family_id": "family-007",
            "family_name": "Mobility Reset",
            "content_pillar": "mobility",
        },
        mode=CreativeMode.EXPLOIT,
        variant={
            "variant_id": "variant-002",
            "variant_label": "B",
            "variant_index": 1,
        },
    )

    assert first.plan_fingerprint != second.plan_fingerprint
    assert first.trace.seed_material != second.trace.seed_material
