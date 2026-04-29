"""TEST-G001: golden creative_trace-derived bundle (caption + overlays)."""

from __future__ import annotations

from tests.fixtures.bad_reels.loader import load_bad_reel_case


def test_latest_trace_standard_caption_locks_smoke_run_regression() -> None:
    bundle = load_bad_reel_case("latest_trace_smoke_operations")
    std = next(c for c in bundle["script"]["caption_variants"] if c["variant"] == "standard")
    # Bad grammar + internal page name from traced rules_provider caption path (not Runway).
    assert "Create a explore" in std["text"]
    assert "Smoke Test Page" in std["text"]
