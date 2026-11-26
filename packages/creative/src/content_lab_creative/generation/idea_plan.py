"""Idea plans for a page: LLM-written, with the original template as the fallback.

Plan beats keep creator directions in ``text`` and viewer copy in ``overlay_text`` /
``narration``; the orchestrator renders only the viewer fields.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from content_lab_creative.generation.context import (
    BEAT_OVERLAY_MAX_CHARS,
    BEAT_OVERLAY_MAX_WORDS,
    HOOK_OVERLAY_MAX_CHARS,
    HOOK_OVERLAY_MAX_WORDS,
    VIEWER_COPY_RULES,
    CreativePageContext,
    check_viewer_copy,
    check_word_budget,
    render_page_brief,
)
from content_lab_intelligence import LLMClient, LLMError, StructuredRequest

logger = logging.getLogger(__name__)


SPEAKING_WORDS_PER_SECOND = 2.5


def narration_word_range(seconds: int) -> tuple[int, int]:
    """Words a beat of ``seconds`` can carry without dead air or rushing (generous bounds)."""

    return max(2, int(seconds * 1.5)), max(4, int(seconds * 3.5))


class IdeaBeatDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=24, description="Beat name, e.g. Proof.")
    direction: str = Field(
        min_length=1, max_length=220, description="Creator-facing: what to show."
    )
    narration: str = Field(min_length=1, max_length=220, description="Spoken line.")
    overlay_text: str = Field(
        min_length=1,
        max_length=BEAT_OVERLAY_MAX_CHARS,
        description=f"On-screen text, at most {BEAT_OVERLAY_MAX_WORDS} words.",
    )
    seconds: int = Field(ge=2, le=8)

    @model_validator(mode="after")
    def _narration_fits_beat(self) -> IdeaBeatDraft:
        # Narration is voiced and laid on the beat: too few words leaves dead air, too many
        # gets sped up and cut. ~2.5 words/s is a natural reading pace.
        words = len(self.narration.split())
        low, high = narration_word_range(self.seconds)
        if not low <= words <= high:
            raise ValueError(
                f"narration for a {self.seconds}s beat should be {low}-{high} words "
                f"(about {SPEAKING_WORDS_PER_SECOND} words per second); it has {words}"
            )
        return self

    @field_validator("narration")
    @classmethod
    def _narration(cls, value: str, info: ValidationInfo) -> str:
        return check_viewer_copy(value.strip(), info)

    @field_validator("overlay_text")
    @classmethod
    def _overlay(cls, value: str, info: ValidationInfo) -> str:
        check_word_budget(value, max_words=BEAT_OVERLAY_MAX_WORDS)
        return check_viewer_copy(value.strip(), info, overlay=True)


class IdeaPlanDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=80, description="Internal plan title.")
    angle: str = Field(
        min_length=1, max_length=220, description="Creator-facing one-line idea summary."
    )
    hook_overlay: str = Field(
        min_length=1,
        max_length=HOOK_OVERLAY_MAX_CHARS,
        description=f"On-screen hook, at most {HOOK_OVERLAY_MAX_WORDS} words.",
    )
    hook_spoken: str = Field(min_length=1, max_length=200)
    hook_direction: str = Field(
        min_length=1, max_length=220, description="Creator-facing: the first frame."
    )
    beats: list[IdeaBeatDraft] = Field(min_length=2, max_length=3)
    caption_angles: list[str] = Field(
        min_length=3, max_length=3, description="Three ready-to-post caption lines."
    )

    @field_validator("hook_overlay")
    @classmethod
    def _hook_overlay(cls, value: str, info: ValidationInfo) -> str:
        check_word_budget(value, max_words=HOOK_OVERLAY_MAX_WORDS)
        return check_viewer_copy(value.strip(), info, overlay=True)

    @field_validator("hook_spoken")
    @classmethod
    def _hook_spoken(cls, value: str, info: ValidationInfo) -> str:
        return check_viewer_copy(value.strip(), info)

    @field_validator("caption_angles")
    @classmethod
    def _captions(cls, value: list[str], info: ValidationInfo) -> list[str]:
        cleaned = []
        for caption in value:
            if not caption.strip() or len(caption) > 220:
                raise ValueError("each caption must be 1-220 characters")
            cleaned.append(check_viewer_copy(caption.strip(), info, caption=True))
        return cleaned

    @model_validator(mode="after")
    def _word_budget(self, info: ValidationInfo) -> IdeaPlanDraft:
        max_words = (info.context or {}).get("max_script_words")
        if max_words:
            words = len(self.hook_spoken.split()) + sum(
                len(beat.narration.split()) for beat in self.beats
            )
            if words > max_words:
                raise ValueError(f"spoken script has {words} words; limit is {max_words}")
        return self


class IdeaPlanResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: dict[str, Any]
    source: Literal["llm", "template"]


_SYSTEM_PROMPT = f"""\
You plan short vertical videos (10-20 seconds) for one social media page. A plan is a \
hook plus 2-3 beats that pay it off, and three caption lines.

{VIEWER_COPY_RULES}

Hook overlay: at most {HOOK_OVERLAY_MAX_WORDS} words. Beat overlay: at most \
{BEAT_OVERLAY_MAX_WORDS} words. Beat seconds: 2-8 each. Each beat's narration is read \
aloud over that beat, so size it to the beat: about {SPEAKING_WORDS_PER_SECOND} words per \
second (a 6 second beat is about 15 words)."""


def generate_idea_plan(
    page: CreativePageContext,
    *,
    plan_number: int,
    topic: str | None = None,
    asset_labels: list[str] | None = None,
    client: LLMClient | None,
) -> IdeaPlanResult:
    niche = page.niche_profile(topic=topic)
    if client is None:
        return _template_result(page, plan_number, niche.key, reason="llm_not_configured")
    brief = render_page_brief(page, topic=topic, asset_labels=asset_labels or [], niche=niche)
    prompt = (
        f"{brief}\n\n"
        f"This is plan #{plan_number} for the page; make it a fresh angle, not a generic intro."
    )
    try:
        result = client.generate_structured(
            StructuredRequest(
                purpose="idea_plan",
                system=_SYSTEM_PROMPT,
                prompt=prompt,
                output_model=IdeaPlanDraft,
                max_tokens=4_000,
                validation_context=page.validation_context(),
            )
        )
    except LLMError as exc:
        logger.warning("idea plan generation fell back to template: %s", exc)
        return _template_result(page, plan_number, niche.key, reason=type(exc).__name__)

    draft = result.output
    plan: dict[str, Any] = {
        "title": draft.title,
        "hook": draft.hook_overlay,
        "angle": draft.angle,
        "beats": [
            {
                "label": "Hook",
                "text": draft.hook_direction,
                "narration": draft.hook_spoken,
                "overlay_text": draft.hook_overlay,
                "seconds": 3,
            },
            *(
                {
                    "label": beat.label,
                    "text": beat.direction,
                    "narration": beat.narration,
                    "overlay_text": beat.overlay_text,
                    "seconds": beat.seconds,
                }
                for beat in draft.beats
            ),
        ],
        "caption_angles": list(draft.caption_angles),
        "generation": {
            "source": "llm",
            "niche": niche.key,
            "usage": result.usage.as_dict(),
        },
    }
    return IdeaPlanResult(plan=plan, source="llm")


def template_idea_plan(page: CreativePageContext, *, plan_number: int) -> dict[str, Any]:
    """The original canned plan, now with explicit viewer copy for every beat."""

    handle = page.handle or page.page_name
    hook = f"What would make {handle} worth following this week?"
    return {
        "title": f"{page.page_name} plan {plan_number}",
        "hook": hook,
        "angle": "Turn one practical page insight into a clear short-form reel.",
        "beats": [
            {
                "label": "Hook",
                "text": "Open with the exact problem the audience already feels.",
                "narration": hook,
                "overlay_text": hook,
                "seconds": 3,
            },
            {
                "label": "Proof",
                "text": "Show the useful shift, example, or operating principle.",
                # ~15 words: fills its 6 s beat when read aloud (~2.5 words/s).
                "narration": "Here is the one shift that makes this easier: try it once, then keep what works.",
                "overlay_text": "Useful shift",
                "seconds": 6,
            },
            {
                "label": "Action",
                "text": "Close with one concrete next step the viewer can try.",
                "narration": "Try one concrete next step today.",
                "overlay_text": "One concrete next step",
                "seconds": 3,
            },
        ],
        "caption_angles": [
            "Save this before your next content planning block.",
            "A simple way to turn page strategy into a reel.",
            "Use this as the spine for the next post.",
        ],
    }


def _template_result(
    page: CreativePageContext, plan_number: int, niche_key: str, *, reason: str
) -> IdeaPlanResult:
    plan = template_idea_plan(page, plan_number=plan_number)
    plan["generation"] = {"source": "template", "niche": niche_key, "fallback_reason": reason}
    return IdeaPlanResult(plan=plan, source="template")


__all__ = [
    "IdeaBeatDraft",
    "IdeaPlanDraft",
    "IdeaPlanResult",
    "generate_idea_plan",
    "template_idea_plan",
]
