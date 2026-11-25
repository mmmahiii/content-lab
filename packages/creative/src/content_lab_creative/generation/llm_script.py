"""LLM script generator for the reel pipeline, with the rules generator as its fallback."""

from __future__ import annotations

import logging
from typing import Any

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
from content_lab_creative.script_generator import (
    BriefLike,
    RulesPlusProviderScriptGenerator,
    ScriptBriefContext,
    ScriptGenerator,
    _attach_lint_result,
    _build_pinned_comments,
    _disclosure_suffix,
    _hashtags_for_published_caption,
    _normalize_brief,
    _segment_boundaries,
    _slugify,
)
from content_lab_creative.types import (
    CaptionVariant,
    CaptionVariantName,
    GeneratedScriptOutput,
    OverlayCue,
    PinnedComment,
    PinnedCommentPurpose,
    ScriptBeat,
    ScriptGeneratorPath,
    ScriptOverlayEmphasis,
)
from content_lab_intelligence import LLMClient, LLMError, StructuredRequest, build_llm_client

logger = logging.getLogger(__name__)


class ScriptBeatDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    narration: str = Field(min_length=1, max_length=220)
    overlay_text: str = Field(
        min_length=1,
        max_length=BEAT_OVERLAY_MAX_CHARS,
        description=f"On-screen text, at most {BEAT_OVERLAY_MAX_WORDS} words.",
    )
    shot_direction: str = Field(min_length=1, max_length=220, description="Creator-facing.")

    @field_validator("narration")
    @classmethod
    def _narration(cls, value: str, info: ValidationInfo) -> str:
        return check_viewer_copy(value.strip(), info)

    @field_validator("overlay_text")
    @classmethod
    def _overlay(cls, value: str, info: ValidationInfo) -> str:
        check_word_budget(value, max_words=BEAT_OVERLAY_MAX_WORDS)
        return check_viewer_copy(value.strip(), info, overlay=True)


class ScriptDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hook_overlay: str = Field(
        min_length=1,
        max_length=HOOK_OVERLAY_MAX_CHARS,
        description=f"On-screen hook, at most {HOOK_OVERLAY_MAX_WORDS} words.",
    )
    hook_spoken: str = Field(min_length=1, max_length=200)
    hook_shot: str = Field(min_length=1, max_length=220, description="Creator-facing.")
    beats: list[ScriptBeatDraft] = Field(min_length=2, max_length=4)
    caption_short: str = Field(min_length=1, max_length=300)
    caption_standard: str = Field(min_length=1, max_length=1_200)
    caption_engagement: str = Field(min_length=1, max_length=300)
    hashtags: list[str] = Field(min_length=2, max_length=10)
    pinned_comment: str | None = Field(default=None, max_length=300)

    @field_validator("hook_overlay")
    @classmethod
    def _hook_overlay(cls, value: str, info: ValidationInfo) -> str:
        check_word_budget(value, max_words=HOOK_OVERLAY_MAX_WORDS)
        return check_viewer_copy(value.strip(), info, overlay=True)

    @field_validator("hook_spoken")
    @classmethod
    def _hook_spoken(cls, value: str, info: ValidationInfo) -> str:
        return check_viewer_copy(value.strip(), info)

    @field_validator("caption_short", "caption_standard", "caption_engagement", "pinned_comment")
    @classmethod
    def _caption(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        return check_viewer_copy(value.strip(), info, caption=True)

    @model_validator(mode="after")
    def _word_budget(self, info: ValidationInfo) -> ScriptDraft:
        max_words = (info.context or {}).get("max_script_words")
        if max_words:
            words = len(self.hook_spoken.split()) + sum(
                len(beat.narration.split()) for beat in self.beats
            )
            if words > max_words:
                raise ValueError(f"spoken script has {words} words; limit is {max_words}")
        return self


_SYSTEM_PROMPT = f"""\
You write complete scripts for short vertical videos: a hook, 2-4 beats and the \
publishing copy (three captions, hashtags, an optional pinned comment).

{VIEWER_COPY_RULES}

Hook overlay: at most {HOOK_OVERLAY_MAX_WORDS} words. Beat overlay: at most \
{BEAT_OVERLAY_MAX_WORDS} words. The last beat closes the reel (takeaway or soft CTA).
Hashtags: plain words without '#', specific to the topic."""


class LLMScriptGenerator:
    """Writes the script with an LLM; uses ``fallback`` when no LLM is available or it fails."""

    provider_name = "llm"
    generator_path = ScriptGeneratorPath.LLM.value

    def __init__(
        self,
        *,
        client: LLMClient | None = None,
        fallback: ScriptGenerator | None = None,
        use_env_client: bool = True,
    ) -> None:
        self._client = client
        self._fallback = fallback or RulesPlusProviderScriptGenerator()
        self._use_env_client = use_env_client

    def generate(self, brief: BriefLike) -> GeneratedScriptOutput:
        context = _normalize_brief(brief)
        client = self._client
        if client is None and self._use_env_client:
            client = build_llm_client()
        if client is None:
            return self._fall_back(brief, reason="llm_not_configured")

        page = _page_context(context)
        try:
            result = client.generate_structured(
                StructuredRequest(
                    purpose="reel_script",
                    system=_SYSTEM_PROMPT,
                    prompt=_prompt(context, page),
                    output_model=ScriptDraft,
                    max_tokens=6_000,
                    validation_context=page.validation_context(),
                )
            )
        except LLMError as exc:
            logger.warning("LLM script generation fell back: %s", exc)
            return self._fall_back(brief, reason=type(exc).__name__)

        output = _attach_lint_result(
            compile_script_draft(result.output, context, usage=result.usage.as_dict())
        )
        lint = output.generation_metadata.get("creative_lint")
        if isinstance(lint, dict) and lint.get("outcome") == "fail":
            return self._fall_back(brief, reason="creative_lint_failed")
        return output

    def _fall_back(self, brief: BriefLike, *, reason: str) -> GeneratedScriptOutput:
        output = self._fallback.generate(brief)
        metadata = dict(output.generation_metadata)
        metadata["llm_fallback_reason"] = reason
        return output.model_copy(update={"generation_metadata": metadata})


def compile_script_draft(
    draft: ScriptDraft,
    context: ScriptBriefContext,
    *,
    usage: dict[str, Any] | None = None,
) -> GeneratedScriptOutput:
    """Turn an LLM draft into the pipeline's ``GeneratedScriptOutput``."""

    lines = [draft.hook_spoken, *(beat.narration for beat in draft.beats)]
    shots = [draft.hook_shot, *(beat.shot_direction for beat in draft.beats)]
    overlay_texts = [draft.hook_overlay, *(beat.overlay_text for beat in draft.beats)]
    boundaries = _segment_boundaries(context.duration_seconds, len(lines))

    spoken = [
        ScriptBeat(
            start_seconds=boundaries[i],
            end_seconds=boundaries[i + 1],
            narration=line,
            shot_direction=shots[i],
        )
        for i, line in enumerate(lines)
    ]
    disclosures = context.constraints.required_disclosures
    overlays = []
    for i, text in enumerate(overlay_texts):
        if i == 0:
            emphasis = ScriptOverlayEmphasis.HOOK
        elif i == len(overlay_texts) - 1:
            emphasis = ScriptOverlayEmphasis.CTA
            if disclosures:
                emphasis, text = ScriptOverlayEmphasis.DISCLOSURE, disclosures[0]
        else:
            emphasis = ScriptOverlayEmphasis.VALUE
        overlays.append(
            OverlayCue(
                start_seconds=boundaries[i],
                end_seconds=boundaries[i + 1],
                text=text,
                emphasis=emphasis,
            )
        )

    hashtags = _normalize_hashtags(draft.hashtags, context)
    disclosure = _disclosure_suffix(context)
    published = " ".join(_hashtags_for_published_caption(hashtags))
    captions = [
        CaptionVariant(
            variant=CaptionVariantName.SHORT, text=f"{draft.caption_short}{disclosure}".strip()
        ),
        CaptionVariant(
            variant=CaptionVariantName.STANDARD,
            text=f"{draft.caption_standard} {published}{disclosure}".strip()[:2_200],
        ),
        CaptionVariant(
            variant=CaptionVariantName.ENGAGEMENT,
            text=f"{draft.caption_engagement}{disclosure}".strip(),
        ),
    ]
    pinned = _build_pinned_comments(context)
    if draft.pinned_comment and context.constraints.allow_direct_cta:
        pinned = [
            PinnedComment(text=draft.pinned_comment, purpose=PinnedCommentPurpose.ENGAGEMENT),
            *(c for c in pinned if c.purpose is PinnedCommentPurpose.DISCLOSURE),
        ]

    model = str((usage or {}).get("model") or "unknown")
    return GeneratedScriptOutput(
        provider_name=f"llm:{model}"[:80],
        generator_path=ScriptGeneratorPath.LLM.value,
        generation_metadata={
            "generator_path": ScriptGeneratorPath.LLM.value,
            "fallback": False,
            "strategy": "llm_structured_v1",
            "model": model,
            "usage": usage or {},
        },
        brief_title=context.title,
        duration_seconds=context.duration_seconds,
        hook_text=draft.hook_overlay,
        spoken_script=spoken,
        overlay_timeline=overlays,
        caption_variants=captions,
        hashtags=hashtags,
        pinned_comments=pinned,
    )


def _page_context(context: ScriptBriefContext) -> CreativePageContext:
    return CreativePageContext(
        page_name=(context.page_name or context.title)[:200],
        audience=context.audience,
        brand_tone=[context.tone] if context.tone else [],
        content_pillars=[context.content_pillar] if context.content_pillar else [],
        primary_call_to_action=context.primary_call_to_action,
        constraints=context.constraints,
    )


def _prompt(context: ScriptBriefContext, page: CreativePageContext) -> str:
    niche = page.niche_profile(topic=" ".join([context.title, *context.tags]))
    brief = render_page_brief(page, topic=context.title, asset_labels=[], niche=niche)
    details = [f"Reel length: {context.duration_seconds} seconds."]
    if context.description:
        details.append(f"Brief: {context.description}")
    if context.narrative_goal:
        details.append(f"Narrative goal: {context.narrative_goal}")
    if context.tags:
        details.append(f"Tags: {', '.join(context.tags)}")
    return f"{brief}\n" + "\n".join(details) + "\n\nWrite the complete script."


def _normalize_hashtags(raw: list[str], context: ScriptBriefContext) -> list[str]:
    limit = context.constraints.max_hashtags if context.constraints.max_hashtags is not None else 6
    seen: set[str] = set()
    hashtags: list[str] = []
    for candidate in raw:
        slug = _slugify(candidate.lstrip("#"))
        if not slug or slug in seen:
            continue
        seen.add(slug)
        hashtags.append(f"#{slug}")
        if len(hashtags) >= limit:
            break
    return hashtags


__all__ = [
    "LLMScriptGenerator",
    "ScriptBeatDraft",
    "ScriptDraft",
    "compile_script_draft",
]
