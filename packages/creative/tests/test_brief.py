from __future__ import annotations

from content_lab_core.types import Platform
from content_lab_creative.brief import CreativeBrief


class TestCreativeBrief:
    def test_defaults(self) -> None:
        brief = CreativeBrief(title="Summer Sale Reel")
        assert brief.title == "Summer Sale Reel"
        assert brief.tone == "neutral"
        assert brief.duration_seconds == 30
        assert brief.is_short_form

    def test_long_form(self) -> None:
        brief = CreativeBrief(title="Explainer", duration_seconds=120)
        assert not brief.is_short_form

    def test_platforms(self) -> None:
        brief = CreativeBrief(
            title="Multi-platform",
            target_platforms=[Platform.INSTAGRAM, Platform.TIKTOK],
        )
        assert len(brief.target_platforms) == 2
        assert Platform.INSTAGRAM in brief.target_platforms
