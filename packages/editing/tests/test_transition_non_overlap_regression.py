"""TEST-G003: adjacent overlays + fades must never compete for the same screen time."""

from __future__ import annotations

import pytest

from content_lab_editing.overlays import (
    TextOverlay,
    build_drawtext_filters,
    normalize_overlay_timeline,
    overlay_opaque_plateau_interval,
    require_adjacent_overlay_intervals_non_overlapping,
)

_TRANSITION_FADE_SECONDS = 0.12


def _four_beat_timeline_template_fades() -> tuple[TextOverlay, ...]:
    overlays: list[TextOverlay] = []
    for index in range(4):
        start = float(index * 3)
        overlays.append(
            TextOverlay.from_mapping(
                {
                    "text": f"beat_{index}",
                    "start_seconds": start,
                    "end_seconds": start + 3.0,
                    "fade_in_seconds": _TRANSITION_FADE_SECONDS,
                    "fade_out_seconds": _TRANSITION_FADE_SECONDS,
                },
                clip_duration_seconds=12.0,
            )
        )
    return tuple(overlays)


def test_adjacent_overlays_with_fades_have_no_nominal_or_plateau_overlap() -> None:
    timeline = _four_beat_timeline_template_fades()
    require_adjacent_overlay_intervals_non_overlapping(timeline)

    for overlay in timeline:
        plateau = overlay_opaque_plateau_interval(overlay)
        assert plateau is not None
        start, end = plateau
        assert end - start >= 3.0 - (2 * _TRANSITION_FADE_SECONDS) - 1e-6

    clauses = build_drawtext_filters(timeline, clip_duration_seconds=12.0)
    assert len(clauses) == 4
    for clause in clauses:
        assert "alpha='" in clause
        assert "enable='" in clause
        assert "*lt(t," in clause


def test_split_second_nominal_bleed_fails() -> None:
    bad = (
        TextOverlay(
            text="a",
            start_seconds=0.0,
            end_seconds=3.0005,
            fade_in_seconds=0.0,
            fade_out_seconds=0.0,
        ),
        TextOverlay(
            text="b",
            start_seconds=3.0,
            end_seconds=6.0,
            fade_in_seconds=0.0,
            fade_out_seconds=0.0,
        ),
    )
    with pytest.raises(ValueError, match="nominal overlay timeline overlap"):
        require_adjacent_overlay_intervals_non_overlapping(bad)


def test_crossing_cues_fail_nominal_overlap_guard() -> None:
    bad = (
        TextOverlay(text="a", start_seconds=0.0, end_seconds=4.0),
        TextOverlay(text="b", start_seconds=3.0, end_seconds=6.0),
    )
    with pytest.raises(ValueError, match="nominal overlay timeline overlap"):
        require_adjacent_overlay_intervals_non_overlapping(bad)


def test_relaxed_nominal_slop_still_catches_plateau_collision() -> None:
    """When nominal windows cross but the caller skips strict timing, opaque cores must still disagree."""

    bad = (
        TextOverlay(text="a", start_seconds=0.0, end_seconds=4.0),
        TextOverlay(text="b", start_seconds=3.0, end_seconds=6.0),
    )
    with pytest.raises(ValueError, match="opaque plateau overlap"):
        require_adjacent_overlay_intervals_non_overlapping(
            bad,
            nominal_slop_seconds=10.0,
        )


def test_normalized_mapping_timeline_matches_four_beat_story() -> None:
    payload = [
        {
            "text": f"cue_{i}",
            "start_seconds": float(i * 3),
            "duration_seconds": 3.0,
            "fade_in": _TRANSITION_FADE_SECONDS,
            "fade_out": _TRANSITION_FADE_SECONDS,
        }
        for i in range(4)
    ]
    normalized = normalize_overlay_timeline(payload, clip_duration_seconds=12.0)
    require_adjacent_overlay_intervals_non_overlapping(normalized)
