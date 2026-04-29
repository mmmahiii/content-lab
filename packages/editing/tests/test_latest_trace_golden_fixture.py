"""Golden latest-trace fixture: caption + overlays used in editing/QA/creative regression tests."""

from __future__ import annotations

import json
from pathlib import Path

from content_lab_editing.overlays import normalize_overlay_timeline

_PACKAGES_ROOT = Path(__file__).resolve().parents[2]


def _load_latest_trace_smoke_bundle() -> dict:
    path = (
        _PACKAGES_ROOT
        / "qa"
        / "tests"
        / "fixtures"
        / "bad_reels"
        / "cases"
        / "latest_trace_smoke_operations.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def test_latest_trace_overlays_round_trip_through_normalize() -> None:
    bundle = _load_latest_trace_smoke_bundle()
    overlays = bundle["script"]["overlay_timeline"]
    normalized = normalize_overlay_timeline(overlays, clip_duration_seconds=12.0)
    assert [o.text for o in normalized] == [
        "The operations reset busy\nfounders can do today",
        "operations",
        "One repeatable move",
        "Save this reset",
    ]
    assert normalized[-1].end_seconds == 12.0


def test_latest_trace_scene_plan_duplicates_repeatable_move_overlay() -> None:
    bundle = _load_latest_trace_smoke_bundle()
    texts = [str(s.get("overlay_text", "")) for s in bundle["scene_plan"]["scenes"]]
    assert texts.count("One repeatable move") == 2
