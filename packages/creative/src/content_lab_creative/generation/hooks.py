"""Hook generator: several materially different opening hooks for one reel."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from content_lab_creative.generation.context import (
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


class HookMechanism(str, Enum):
    CURIOSITY_GAP = "curiosity_gap"
    BOLD_CLAIM = "bold_claim"
    VISUAL_FIRST = "visual_first"
    PROBLEM_AGITATION = "problem_agitation"
    CONTRARIAN = "contrarian"
    STORY_OPEN = "story_open"
    LIST_PROMISE = "list_promise"
    DIRECT_QUESTION = "direct_question"


HOOK_MECHANISM_GUIDE: dict[HookMechanism, str] = {
    HookMechanism.CURIOSITY_GAP: "Withhold one specific detail the reel pays off.",
    HookMechanism.BOLD_CLAIM: "A confident, specific claim the reel then proves.",
    HookMechanism.VISUAL_FIRST: "The first frame does the work; text names what we see.",
    HookMechanism.PROBLEM_AGITATION: "Name a frustration the audience already feels.",
    HookMechanism.CONTRARIAN: "Push back on common advice, then justify it.",
    HookMechanism.STORY_OPEN: "Drop into the middle of a small moment.",
    HookMechanism.LIST_PROMISE: "A countable promise (3 moves, 2 mistakes).",
    HookMechanism.DIRECT_QUESTION: "A question the audience wants answered.",
}


class HookCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mechanism: HookMechanism
    overlay_text: str = Field(
        min_length=1,
        max_length=HOOK_OVERLAY_MAX_CHARS,
        description=f"On-screen hook text, at most {HOOK_OVERLAY_MAX_WORDS} words.",
    )
    spoken_line: str = Field(min_length=1, max_length=200, description="Narrated opening line.")
    visual_direction: str = Field(
        min_length=1,
        max_length=220,
        description="Creator-facing: what the first 3 seconds show.",
    )
    payoff_promise: str = Field(
        min_length=1,
        max_length=180,
        description="Creator-facing: what the rest of the reel must deliver to pay this off.",
    )

    @field_validator("overlay_text")
    @classmethod
    def _overlay(cls, value: str, info: ValidationInfo) -> str:
        check_word_budget(value, max_words=HOOK_OVERLAY_MAX_WORDS)
        return check_viewer_copy(value.strip(), info, overlay=True)

    @field_validator("spoken_line")
    @classmethod
    def _spoken(cls, value: str, info: ValidationInfo) -> str:
        return check_viewer_copy(value.strip(), info)


class HookSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hooks: list[HookCandidate] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def _distinct(self, info: ValidationInfo) -> HookSet:
        expected = (info.context or {}).get("hook_count")
        if expected is not None and len(self.hooks) != expected:
            raise ValueError(f"return exactly {expected} hooks, got {len(self.hooks)}")
        mechanisms = [hook.mechanism for hook in self.hooks]
        if len(set(mechanisms)) != len(mechanisms):
            raise ValueError("each hook must use a different mechanism")
        texts = [hook.overlay_text.casefold() for hook in self.hooks]
        if len(set(texts)) != len(texts):
            raise ValueError("hook overlay texts must all be different")
        return self


class HookGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: CreativePageContext
    topic: str | None = Field(default=None, max_length=200)
    asset_labels: list[str] = Field(default_factory=list, max_length=60)
    count: int = Field(default=3, ge=2, le=5)


class HookGenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hooks: list[HookCandidate]
    source: Literal["llm", "fallback"]
    niche: str
    usage: dict[str, Any] | None = None
    fallback_reason: str | None = None


_SYSTEM_PROMPT = f"""\
You write scroll-stopping opening hooks for short vertical videos (Reels, TikTok, Shorts).
A hook is the first ~3 seconds: on-screen text, the spoken line and what the frame shows.

{VIEWER_COPY_RULES}

Hook mechanisms:
{chr(10).join(f"- {m.value}: {g}" for m, g in HOOK_MECHANISM_GUIDE.items())}

overlay_text: at most {HOOK_OVERLAY_MAX_WORDS} words and {HOOK_OVERLAY_MAX_CHARS} characters.
Every hook must be one the rest of the reel can honestly pay off."""


def build_hook_prompt(request: HookGenerationRequest) -> str:
    niche = request.page.niche_profile(topic=request.topic)
    brief = render_page_brief(
        request.page, topic=request.topic, asset_labels=request.asset_labels, niche=niche
    )
    return (
        f"{brief}\n\n"
        f"Write exactly {request.count} hooks for one reel on this topic. Each must use a "
        "different mechanism and feel materially different (not rewordings of one idea)."
    )


def generate_hooks(
    request: HookGenerationRequest, *, client: LLMClient | None
) -> HookGenerationResult:
    niche = request.page.niche_profile(topic=request.topic)
    if client is None:
        return _fallback_result(request, niche_key=niche.key, reason="llm_not_configured")
    context = {**request.page.validation_context(), "hook_count": request.count}
    try:
        result = client.generate_structured(
            StructuredRequest(
                purpose="hooks",
                system=_SYSTEM_PROMPT,
                prompt=build_hook_prompt(request),
                output_model=HookSet,
                max_tokens=4_000,
                validation_context=context,
            )
        )
    except LLMError as exc:
        logger.warning("hook generation fell back: %s", exc)
        return _fallback_result(request, niche_key=niche.key, reason=type(exc).__name__)
    return HookGenerationResult(
        hooks=result.output.hooks,
        source="llm",
        niche=niche.key,
        usage=result.usage.as_dict(),
    )


def fallback_hooks(request: HookGenerationRequest) -> list[HookCandidate]:
    """Deterministic, topic-aware hooks used when no LLM is available."""

    subject = request.page.subject(request.topic)
    lowered = subject.lower()
    templates: list[tuple[HookMechanism, str, str, str]] = [
        (
            HookMechanism.CURIOSITY_GAP,
            f"The {lowered} detail most people miss",
            f"There's one {lowered} detail almost everyone skips.",
            "Reveal the one detail clearly by the end.",
        ),
        (
            HookMechanism.BOLD_CLAIM,
            f"You're doing {lowered} the hard way",
            f"You're probably making {lowered} harder than it needs to be.",
            "Show the easier way with one concrete example.",
        ),
        (
            HookMechanism.VISUAL_FIRST,
            f"Watch this {lowered} come together",
            f"Watch this {lowered} come together.",
            "Show the finished result in the final beat.",
        ),
        (
            HookMechanism.DIRECT_QUESTION,
            f"What if {lowered} took half the time?",
            f"What if {lowered} took half the time?",
            "Answer the question with a faster method.",
        ),
        (
            HookMechanism.LIST_PROMISE,
            f"3 {lowered} moves worth saving",
            f"Three {lowered} moves worth saving.",
            "Deliver exactly three clear moves.",
        ),
    ]
    hooks = []
    for mechanism, overlay, spoken, payoff in templates[: request.count]:
        hooks.append(
            HookCandidate(
                mechanism=mechanism,
                overlay_text=_fit_words(overlay),
                spoken_line=spoken,
                visual_direction=f"Open on the clearest visual of {lowered}.",
                payoff_promise=payoff,
            )
        )
    return hooks


def _fallback_result(
    request: HookGenerationRequest, *, niche_key: str, reason: str
) -> HookGenerationResult:
    return HookGenerationResult(
        hooks=fallback_hooks(request),
        source="fallback",
        niche=niche_key,
        fallback_reason=reason,
    )


def _fit_words(text: str) -> str:
    """Drop whole trailing words until the hook fits; never cut a word in half."""

    words = text.split()[:HOOK_OVERLAY_MAX_WORDS]
    while len(words) > 1 and len(" ".join(words)) > HOOK_OVERLAY_MAX_CHARS:
        words.pop()
    return " ".join(words)


__all__ = [
    "HOOK_MECHANISM_GUIDE",
    "HookCandidate",
    "HookGenerationRequest",
    "HookGenerationResult",
    "HookMechanism",
    "HookSet",
    "build_hook_prompt",
    "fallback_hooks",
    "generate_hooks",
]
