from __future__ import annotations

import pytest

from content_lab_editing.edit_plan import SceneAwareEditPlan, SceneEditPlanSegment
from content_lab_editing.overlays import OverlayTransitionSettings
from content_lab_editing.templates import (
    CALM_EXPLAINER_V1,
    DEFAULT_EDITORIAL_TEMPLATE,
    EDITORIAL_TEMPLATE_METADATA_KEY,
    EDITORIAL_TEMPLATE_VERSION_METADATA_KEY,
    EDITORIAL_TEMPLATES,
    FAST_CUTS_V1,
    HOOK_FIRST_V1,
    HOOK_PLUS_PAYOFF_V1,
    EditorialTemplate,
    apply_editorial_template,
    apply_overlay_density_cap,
    get_editorial_template,
    overlay_transition_settings,
    select_and_apply_editorial_template,
    select_editorial_template,
)


def _make_plan(
    *,
    segments: list[dict[str, object]],
) -> SceneAwareEditPlan:
    built: list[SceneEditPlanSegment] = []
    cursor = 0.0
    for index, spec in enumerate(segments, start=1):
        duration = float(spec["duration_seconds"])  # type: ignore[arg-type]
        built.append(
            SceneEditPlanSegment(
                segment_id=str(spec.get("segment_id") or f"segment-{index:03d}"),
                scene_id=str(spec["scene_id"]),
                purpose=str(spec["purpose"]),
                source_uri=str(spec["source_uri"]),
                duration_seconds=duration,
                timeline_start_seconds=cursor,
            )
        )
        cursor += duration
    return SceneAwareEditPlan(segments=built)


def test_default_template_identity() -> None:
    assert DEFAULT_EDITORIAL_TEMPLATE is HOOK_FIRST_V1
    assert HOOK_FIRST_V1.template_id == "hook_first_v1"
    assert HOOK_FIRST_V1.template_version.startswith("hook_first_v1")
    assert HOOK_FIRST_V1 in EDITORIAL_TEMPLATES


def test_overlay_transition_settings_matches_cross_fade_template() -> None:
    settings = overlay_transition_settings(CALM_EXPLAINER_V1)
    assert settings.allow_crossfade_overlap is True
    assert settings.enter_duration_ms == 220.0
    assert settings.exit_duration_ms == 220.0


def test_overlay_transition_settings_defaults_for_hard_cut() -> None:
    settings = overlay_transition_settings(HOOK_FIRST_V1)
    assert settings == OverlayTransitionSettings()


def test_editorial_template_metadata_roundtrip() -> None:
    payload = HOOK_FIRST_V1.as_metadata()

    assert payload[EDITORIAL_TEMPLATE_METADATA_KEY] == HOOK_FIRST_V1.template_id
    assert payload[EDITORIAL_TEMPLATE_VERSION_METADATA_KEY] == HOOK_FIRST_V1.template_version
    assert payload["transition_style"] == HOOK_FIRST_V1.transition_style
    assert payload["end_card_treatment"] == HOOK_FIRST_V1.end_card_treatment


def test_editorial_template_rejects_invalid_windows() -> None:
    with pytest.raises(ValueError, match="hook_max_seconds"):
        EditorialTemplate(
            template_id="bad",
            template_version="bad.v1",
            hook_min_seconds=1.2,
            hook_max_seconds=0.8,
            end_card_min_seconds=0.5,
            end_card_max_seconds=1.0,
            overlay_density_per_second=1.0,
            transition_style="hard_cut",
            end_card_treatment="hold_final_frame",
        )


def test_get_editorial_template_returns_registered_entry() -> None:
    assert get_editorial_template("hook_first_v1") is HOOK_FIRST_V1
    assert get_editorial_template("FAST_CUTS_V1") is FAST_CUTS_V1  # normalized


def test_get_editorial_template_raises_for_unknown_id() -> None:
    with pytest.raises(KeyError, match="Unknown editorial template"):
        get_editorial_template("nope_v0")


def test_select_editorial_template_defaults_to_hook_first() -> None:
    assert select_editorial_template() is HOOK_FIRST_V1


def test_select_editorial_template_picks_calm_explainer_for_long_low_density() -> None:
    script = {"duration_seconds": 60, "overlay_timeline": [{}, {}]}
    chosen = select_editorial_template(
        scene_plan={"duration_seconds": 60, "scenes": [{"purpose": "hook"}]},
        script=script,
    )
    assert chosen is CALM_EXPLAINER_V1


def test_select_editorial_template_picks_fast_cuts_for_high_overlay_density() -> None:
    script = {
        "duration_seconds": 15,
        "overlay_timeline": [{}] * 30,
    }
    chosen = select_editorial_template(script=script)
    assert chosen is FAST_CUTS_V1


def test_select_editorial_template_picks_fast_cuts_for_many_scenes() -> None:
    scene_plan = {
        "duration_seconds": 20,
        "scenes": [{"purpose": "scene"}] * 6,
    }
    chosen = select_editorial_template(scene_plan=scene_plan)
    assert chosen is FAST_CUTS_V1


def test_select_editorial_template_picks_hook_plus_payoff_when_payoff_exists() -> None:
    scene_plan = {
        "duration_seconds": 20,
        "scenes": [
            {"purpose": "hook"},
            {"purpose": "value"},
            {"purpose": "payoff"},
            {"purpose": "close"},
        ],
    }
    chosen = select_editorial_template(scene_plan=scene_plan)
    assert chosen is HOOK_PLUS_PAYOFF_V1


def test_select_editorial_template_is_deterministic() -> None:
    scene_plan = {
        "duration_seconds": 20,
        "scenes": [
            {"purpose": "hook"},
            {"purpose": "payoff"},
        ],
    }
    first = select_editorial_template(scene_plan=scene_plan)
    second = select_editorial_template(scene_plan=scene_plan)
    assert first is second


def test_apply_editorial_template_reorders_segments_hook_first() -> None:
    plan = _make_plan(
        segments=[
            {
                "segment_id": "segment-001",
                "scene_id": "scene-value",
                "purpose": "value",
                "source_uri": "file:///value.mp4",
                "duration_seconds": 2.0,
            },
            {
                "segment_id": "segment-002",
                "scene_id": "scene-hook",
                "purpose": "hook",
                "source_uri": "file:///hook.mp4",
                "duration_seconds": 2.0,
            },
            {
                "segment_id": "segment-003",
                "scene_id": "scene-close",
                "purpose": "close",
                "source_uri": "file:///close.mp4",
                "duration_seconds": 2.0,
            },
        ],
    )

    applied = apply_editorial_template(plan=plan, template=HOOK_FIRST_V1)

    assert [segment.scene_id for segment in applied.segments] == [
        "scene-hook",
        "scene-value",
        "scene-close",
    ]
    # hook clamps into [0.6, 1.4], so 2.0 -> 1.4
    assert applied.segments[0].duration_seconds == pytest.approx(1.4)
    # close clamps into [0.5, 1.2], so 2.0 -> 1.2
    assert applied.segments[-1].duration_seconds == pytest.approx(1.2)
    # value segment retains duration
    assert applied.segments[1].duration_seconds == pytest.approx(2.0)


def test_apply_editorial_template_produces_contiguous_timeline() -> None:
    plan = _make_plan(
        segments=[
            {
                "scene_id": "scene-hook",
                "purpose": "hook",
                "source_uri": "file:///hook.mp4",
                "duration_seconds": 0.2,
            },
            {
                "scene_id": "scene-value",
                "purpose": "value",
                "source_uri": "file:///value.mp4",
                "duration_seconds": 1.0,
            },
            {
                "scene_id": "scene-close",
                "purpose": "close",
                "source_uri": "file:///close.mp4",
                "duration_seconds": 0.1,
            },
        ],
    )

    applied = apply_editorial_template(plan=plan, template=HOOK_FIRST_V1)

    assert applied.segments[0].duration_seconds == pytest.approx(HOOK_FIRST_V1.hook_min_seconds)
    assert applied.segments[-1].duration_seconds == pytest.approx(
        HOOK_FIRST_V1.end_card_min_seconds
    )

    cursor = 0.0
    for segment in applied.segments:
        assert segment.timeline_start_seconds == pytest.approx(cursor)
        assert segment.timeline_end_seconds is not None
        assert segment.timeline_end_seconds == pytest.approx(cursor + segment.duration_seconds)
        cursor = segment.timeline_end_seconds


def test_apply_editorial_template_records_template_version_in_metadata() -> None:
    plan = _make_plan(
        segments=[
            {
                "scene_id": "scene-hook",
                "purpose": "hook",
                "source_uri": "file:///hook.mp4",
                "duration_seconds": 0.8,
            },
            {
                "scene_id": "scene-close",
                "purpose": "close",
                "source_uri": "file:///close.mp4",
                "duration_seconds": 0.8,
            },
        ],
    )

    applied = apply_editorial_template(plan=plan, template=HOOK_PLUS_PAYOFF_V1)

    assert applied.metadata[EDITORIAL_TEMPLATE_METADATA_KEY] == (HOOK_PLUS_PAYOFF_V1.template_id)
    assert applied.metadata[EDITORIAL_TEMPLATE_VERSION_METADATA_KEY] == (
        HOOK_PLUS_PAYOFF_V1.template_version
    )
    assert applied.metadata["transition_style"] == HOOK_PLUS_PAYOFF_V1.transition_style
    assert applied.metadata["end_card_treatment"] == (HOOK_PLUS_PAYOFF_V1.end_card_treatment)


def test_apply_editorial_template_is_deterministic() -> None:
    plan = _make_plan(
        segments=[
            {
                "scene_id": "scene-hook",
                "purpose": "hook",
                "source_uri": "file:///hook.mp4",
                "duration_seconds": 1.8,
            },
            {
                "scene_id": "scene-value",
                "purpose": "value",
                "source_uri": "file:///value.mp4",
                "duration_seconds": 2.5,
            },
            {
                "scene_id": "scene-close",
                "purpose": "close",
                "source_uri": "file:///close.mp4",
                "duration_seconds": 1.7,
            },
        ],
    )

    first = apply_editorial_template(plan=plan, template=HOOK_FIRST_V1)
    second = apply_editorial_template(plan=plan, template=HOOK_FIRST_V1)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_select_and_apply_editorial_template_uses_selected_template() -> None:
    plan = _make_plan(
        segments=[
            {
                "scene_id": "scene-hook",
                "purpose": "hook",
                "source_uri": "file:///hook.mp4",
                "duration_seconds": 1.0,
            },
            {
                "scene_id": "scene-payoff",
                "purpose": "payoff",
                "source_uri": "file:///payoff.mp4",
                "duration_seconds": 1.5,
            },
            {
                "scene_id": "scene-close",
                "purpose": "close",
                "source_uri": "file:///close.mp4",
                "duration_seconds": 1.0,
            },
        ],
    )
    scene_plan = {
        "duration_seconds": 12,
        "scenes": [
            {"purpose": "hook"},
            {"purpose": "payoff"},
            {"purpose": "close"},
        ],
    }

    applied, chosen = select_and_apply_editorial_template(
        plan=plan,
        scene_plan=scene_plan,
    )

    assert chosen is HOOK_PLUS_PAYOFF_V1
    assert applied.metadata[EDITORIAL_TEMPLATE_METADATA_KEY] == "hook_plus_payoff_v1"


def test_apply_overlay_density_cap_trims_trailing_overlays() -> None:
    overlays = ["a", "b", "c", "d", "e"]

    capped = apply_overlay_density_cap(
        overlays,
        clip_duration_seconds=1.2,
        template=HOOK_FIRST_V1,
    )

    # 1.5 * 1.2 = 1.8 -> ceil = 2
    assert capped == ("a", "b")


def test_apply_overlay_density_cap_preserves_when_under_limit() -> None:
    overlays = ["a", "b"]

    capped = apply_overlay_density_cap(
        overlays,
        clip_duration_seconds=2.0,
        template=HOOK_FIRST_V1,
    )

    assert capped == ("a", "b")


def test_apply_overlay_density_cap_returns_empty_for_zero_duration() -> None:
    assert (
        apply_overlay_density_cap(
            ["a"],
            clip_duration_seconds=0.0,
            template=HOOK_FIRST_V1,
        )
        == ()
    )
