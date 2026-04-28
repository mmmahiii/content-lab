from __future__ import annotations

from typing import cast

import pytest

from content_lab_editing.instructions import EditInstruction, EditOperation, EditPlan
from content_lab_editing.layout import SafeAreaInsets9_16
from content_lab_editing.overlays import (
    OverlayLayoutError,
    OverlayTextPolicyError,
    TextOverlay,
    build_drawtext_filters,
    build_overlay_safe_area_report,
    build_overlay_video_filter,
    normalize_overlay_source_text,
    normalize_overlay_timeline,
    validate_overlay_fits_frame,
)


def test_build_drawtext_filters_uses_safe_defaults_for_edit_plan() -> None:
    timeline = EditPlan(
        run_id="run-overlay",
        instructions=[
            EditInstruction(operation=EditOperation.TRIM, params={"start": 0, "end": 1}),
            EditInstruction(
                operation=EditOperation.OVERLAY_TEXT,
                params={
                    "text": "Hello: world",
                    "start": 0.25,
                    "duration": 0.5,
                },
            ),
        ],
    )

    filters = build_drawtext_filters(timeline, clip_duration_seconds=1.5)

    assert len(filters) == 1
    assert "drawtext=" in filters[0]
    assert "text='Hello\\: world'" in filters[0]
    assert "x=(w-text_w)/2" in filters[0]
    assert "y=h-text_h-160" in filters[0]
    assert "box=1" in filters[0]
    assert "enable='between(t,0.250,0.750)'" in filters[0]


def test_normalize_overlay_timeline_clamps_open_ended_overlay_to_clip_duration() -> None:
    overlays = normalize_overlay_timeline(
        [TextOverlay(text="Later", start_seconds=0.9)],
        clip_duration_seconds=1.2,
    )

    assert overlays[0].start_seconds == 0.9
    assert overlays[0].end_seconds == 1.2


def test_build_overlay_video_filter_leaves_base_filter_untouched_without_overlays() -> None:
    assert (
        build_overlay_video_filter(base_filter="scale=1080:1920", timeline=None)
        == "scale=1080:1920"
    )


def test_overlay_phrase_is_exact_in_drawtext_after_layout_preflight() -> None:
    phrase = "The operations reset busy founders can do today"
    timeline = [
        TextOverlay(
            text=phrase,
            start_seconds=0.0,
            end_seconds=1.0,
            font_size=28,
        ),
    ]
    validate_overlay_fits_frame(timeline[0])
    filters = build_drawtext_filters(
        timeline,
        clip_duration_seconds=2.0,
        frame_width=1080,
        frame_height=1920,
    )
    assert len(filters) == 1
    assert filters[0].startswith("drawtext=")
    assert f"text='{phrase}" in filters[0]


def test_build_drawtext_filters_raises_overlay_layout_error_for_overflowing_line() -> None:
    long_text = "X" * 200
    overlay = TextOverlay(
        text=long_text,
        start_seconds=0.0,
        end_seconds=1.0,
        font_size=64,
    )
    with pytest.raises(OverlayLayoutError) as exc:
        build_drawtext_filters([overlay], clip_duration_seconds=2.0)
    err = exc.value
    assert err.code == "exceeds_frame"
    assert "details" in err.to_dict()
    assert err.text == long_text


def test_normalize_overlay_source_text_strips_ends_only() -> None:
    assert normalize_overlay_source_text("  The operations  reset  \n") == "The operations  reset"


def test_validate_overlay_raises_exceeds_safe_area_with_tight_insets() -> None:
    overlay = TextOverlay(
        text="Not in the safe box",
        start_seconds=0.0,
        end_seconds=1.0,
        font_size=64,
    )
    tight = SafeAreaInsets9_16(left=500, right=500, top=0, bottom=0)
    with pytest.raises(OverlayLayoutError) as exc:
        validate_overlay_fits_frame(
            overlay,
            frame_width=1080,
            frame_height=1920,
            safe_insets=tight,
        )
    assert exc.value.code == "exceeds_safe_area"


def test_build_overlay_safe_area_report_describes_timeline() -> None:
    phrase = "The operations reset busy founders can do today"
    report = build_overlay_safe_area_report(
        [
            TextOverlay(
                text=phrase,
                start_seconds=0.0,
                end_seconds=1.0,
                font_size=28,
            )
        ],
        clip_duration_seconds=2.0,
    )
    assert report["status"] == "pass"
    assert report["frame"] == {"width": 1080, "height": 1920}
    assert "safe_insets_px" in report
    ovl = report["overlays"]
    assert isinstance(ovl, list) and len(ovl) == 1
    o0 = cast(dict[str, object], ovl[0])
    assert o0["fits_safe_area"] is True
    assert o0["overlay_role"] == "other"


def test_emphasis_overlay_preset_applies_when_style_omitted() -> None:
    timeline = EditPlan(
        run_id="run-emphasis",
        instructions=[
            EditInstruction(
                operation=EditOperation.OVERLAY_TEXT,
                params={
                    "text": "Short punchy line",
                    "start": 0.0,
                    "duration": 1.0,
                    "role": "emphasis",
                },
            ),
        ],
    )
    overlays = normalize_overlay_timeline(timeline, clip_duration_seconds=2.0)
    assert len(overlays) == 1
    assert overlays[0].overlay_role == "emphasis"
    assert overlays[0].font_size == 56
    assert overlays[0].margin_y == 150


def test_emphasis_overlay_rejects_too_many_words() -> None:
    eleven = " ".join(f"w{i}" for i in range(11))
    with pytest.raises(OverlayTextPolicyError) as exc:
        build_drawtext_filters(
            [
                TextOverlay(
                    text=eleven,
                    overlay_role="emphasis",
                    start_seconds=0.0,
                    end_seconds=1.0,
                )
            ],
            clip_duration_seconds=2.0,
        )
    assert exc.value.code == "role_text_too_long"
    d = exc.value.to_dict()
    assert d["type"] == "overlay_text_policy"
    assert d["max_word_count"] == 10


def test_cta_overlay_rejects_ninth_word() -> None:
    eight = " ".join(f"c{i}" for i in range(8))
    nine = eight + " extra"
    normalize_overlay_timeline(
        [TextOverlay(text=eight, overlay_role="cta", start_seconds=0.0, end_seconds=1.0)],
        clip_duration_seconds=2.0,
    )
    with pytest.raises(OverlayTextPolicyError) as exc:
        normalize_overlay_timeline(
            [TextOverlay(text=nine, overlay_role="cta", start_seconds=0.0, end_seconds=1.0)],
            clip_duration_seconds=2.0,
        )
    assert exc.value.code == "role_text_too_long"
    assert exc.value.to_dict()["max_word_count"] == 8


def test_from_mapping_resolves_script_emphasis_value_to_emphasis() -> None:
    overlay = TextOverlay.from_mapping(
        {
            "text": "Punchy",
            "start": 0.0,
            "duration": 1.0,
            "emphasis": "value",
        }
    )
    assert overlay.overlay_role == "emphasis"
    assert overlay.font_size == 56
    assert overlay.margin_y == 150


def test_from_mapping_resolves_plan_overlay_role_cta() -> None:
    overlay = TextOverlay.from_mapping(
        {
            "text": "Subscribe",
            "start": 0.0,
            "duration": 1.0,
            "plan_overlay_role": "cta",
        }
    )
    assert overlay.overlay_role == "cta"
    assert overlay.margin_y == 200


def test_emphasis_rejects_multiline_text() -> None:
    with pytest.raises(OverlayTextPolicyError):
        build_drawtext_filters(
            [
                TextOverlay(
                    text="one\ntwo",
                    overlay_role="emphasis",
                    start_seconds=0.0,
                    end_seconds=1.0,
                )
            ],
            clip_duration_seconds=2.0,
        )


def test_hook_overlay_wraps_to_two_lines_and_records_manifest_fields() -> None:
    phrase = "The operations reset busy founders can do today"
    hook = TextOverlay(
        text=phrase,
        overlay_role="hook",
        start_seconds=0.0,
        end_seconds=1.0,
        font_size=64,
    )
    filters = build_drawtext_filters([hook], clip_duration_seconds=2.0)
    assert len(filters) == 1
    flat = filters[0].replace("\\n", " ")
    for w in phrase.split():
        assert w in flat
    assert "fontsize=" in filters[0]

    report = build_overlay_safe_area_report([hook], clip_duration_seconds=2.0)
    raw_ovl = report["overlays"]
    assert isinstance(raw_ovl, list) and len(raw_ovl) >= 1
    o0 = cast(dict[str, object], raw_ovl[0])
    assert o0["overlay_role"] == "hook"
    assert o0.get("hook_autofit") is not None
    ha = o0["hook_autofit"]
    assert isinstance(ha, dict)
    assert "final_font_size" in ha
    assert "base_font_size" in ha
    assert ha.get("line_count") in (1, 2)
    assert isinstance(ha.get("lines"), list)


def test_hook_overlay_raises_when_token_cannot_fit() -> None:
    token = "X" * 400
    hook = TextOverlay(
        text=token,
        overlay_role="hook",
        start_seconds=0.0,
        end_seconds=1.0,
        font_size=64,
    )
    with pytest.raises(OverlayLayoutError) as exc:
        build_drawtext_filters([hook], clip_duration_seconds=2.0)
    assert exc.value.code == "hook_unreadable"
