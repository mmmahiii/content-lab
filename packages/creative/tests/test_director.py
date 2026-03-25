from __future__ import annotations

from content_lab_core.types import Platform
from content_lab_creative.director import (
    PhaseOneDirector,
    resolve_policy_state,
    select_mode_from_bucket,
)
from content_lab_creative.persona import PageConstraints, PageMetadata, PersonaProfile
from content_lab_creative.types import (
    CreativeMode,
    DirectorPlanInput,
    PolicyBudgetGuardrails,
    PolicyModeRatios,
    PolicyStateDocument,
    PolicyStatePatch,
)


def _request(
    *,
    brief_index: int = 0,
    global_policy: PolicyStateDocument | None = None,
    page_policy: PolicyStatePatch | PolicyStateDocument | None = None,
) -> DirectorPlanInput:
    return DirectorPlanInput(
        page_name="Northwind Fitness",
        brief_index=brief_index,
        target_platforms=[Platform.INSTAGRAM],
        page_metadata=PageMetadata(
            persona=PersonaProfile(
                label="Coach-next-door",
                audience="Busy professionals who want practical routines",
                brand_tone=["direct", "optimistic"],
                content_pillars=["mobility", "strength"],
                differentiators=["Simple progressions"],
                primary_call_to_action="Follow for the next routine",
            ),
            constraints=PageConstraints(
                required_disclosures=["Results vary"],
                prohibited_claims=["Guaranteed transformation"],
                allow_direct_cta=False,
            ),
        ),
        global_policy=global_policy or PolicyStateDocument(),
        page_policy=page_policy,
    )


def test_phase_one_director_is_deterministic() -> None:
    director = PhaseOneDirector()
    request = _request(
        global_policy=PolicyStateDocument(
            mode_ratios=PolicyModeRatios(
                exploit=0.0,
                explore=1.0,
                mutation=0.0,
                chaos=0.0,
            )
        )
    )

    first = director.plan(request)
    second = director.plan(request)

    assert first.model_dump() == second.model_dump()
    assert first.selected_mode is CreativeMode.EXPLORE
    assert first.content_pillar == "mobility"
    assert first.persona_label == "Coach-next-door"
    assert first.primary_call_to_action is None
    assert first.constraints.required_disclosures == ["Results vary"]
    assert first.policy.effective_policy.mode_ratios.explore == 1.0


def test_phase_one_director_rotates_content_pillar_by_brief_index() -> None:
    director = PhaseOneDirector()

    first = director.plan(_request(brief_index=0))
    second = director.plan(_request(brief_index=1))

    assert first.content_pillar == "mobility"
    assert second.content_pillar == "strength"
    assert first.selection_trace.seed_material != second.selection_trace.seed_material


def test_select_mode_from_bucket_respects_policy_weights() -> None:
    mode_ratios = PolicyModeRatios(
        exploit=0.1,
        explore=0.2,
        mutation=0.3,
        chaos=0.4,
    )

    assert select_mode_from_bucket(mode_ratios, bucket=0.05) is CreativeMode.EXPLOIT
    assert select_mode_from_bucket(mode_ratios, bucket=0.25) is CreativeMode.EXPLORE
    assert select_mode_from_bucket(mode_ratios, bucket=0.55) is CreativeMode.MUTATION
    assert select_mode_from_bucket(mode_ratios, bucket=0.95) is CreativeMode.CHAOS


def test_resolve_policy_state_applies_page_override_without_losing_global_budget() -> None:
    global_policy = PolicyStateDocument(
        mode_ratios=PolicyModeRatios(
            exploit=1.0,
            explore=0.0,
            mutation=0.0,
            chaos=0.0,
        ),
        budget=PolicyBudgetGuardrails(
            per_run_usd_limit=7.0,
            daily_usd_limit=20.0,
            monthly_usd_limit=100.0,
        ),
    )
    page_policy = PolicyStatePatch(
        mode_ratios=PolicyModeRatios(
            exploit=0.0,
            explore=0.0,
            mutation=1.0,
            chaos=0.0,
        )
    )

    effective = resolve_policy_state(global_policy=global_policy, page_policy=page_policy)

    assert effective.effective_policy.mode_ratios.mutation == 1.0
    assert effective.effective_policy.budget.per_run_usd_limit == 7.0
