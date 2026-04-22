"""Provider-agnostic script generation with explicit production and fallback paths."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from content_lab_creative.brief import CreativeBrief
from content_lab_creative.persona import PageConstraints
from content_lab_creative.types import (
    CaptionVariant,
    CaptionVariantName,
    GeneratedScriptOutput,
    OverlayCue,
    PinnedComment,
    PinnedCommentPurpose,
    PlannedCreativeBrief,
    ScriptBeat,
    ScriptGeneratorPath,
    ScriptOverlayEmphasis,
)

BriefLike = CreativeBrief | PlannedCreativeBrief
ScriptGeneratorPathLike = ScriptGeneratorPath | str
_SCRIPT_GENERATOR_ENV = "CONTENT_LAB_SCRIPT_GENERATOR"


@dataclass(frozen=True)
class ScriptBriefContext:
    """Normalized brief data used by script generators."""

    title: str
    description: str
    duration_seconds: int
    tone: str
    tags: tuple[str, ...]
    page_name: str | None
    audience: str | None
    content_pillar: str | None
    narrative_goal: str | None
    primary_call_to_action: str | None
    constraints: PageConstraints


class ScriptGenerator(Protocol):
    """Provider-agnostic interface for structured script generation."""

    provider_name: str

    def generate(self, brief: BriefLike) -> GeneratedScriptOutput:
        """Return a structured script package for a reel brief."""


class DeterministicScriptGenerator:
    """Stable fallback generator for smoke, fixture, and deterministic regression tests."""

    provider_name = "deterministic_stub"
    generator_path = ScriptGeneratorPath.DETERMINISTIC_STUB.value

    def generate(self, brief: BriefLike) -> GeneratedScriptOutput:
        context = _normalize_brief(brief)
        hook_text = _build_hook(context)
        spoken_script = _build_spoken_script(context, hook_text)
        overlay_timeline = _build_overlay_timeline(
            context,
            hook_text=hook_text,
            spoken_script=spoken_script,
        )
        hashtags = _build_hashtags(context)
        caption_variants = _build_caption_variants(
            context,
            hook_text=hook_text,
            hashtags=hashtags,
        )
        pinned_comments = _build_pinned_comments(context)
        return GeneratedScriptOutput(
            provider_name=self.provider_name,
            generator_path=self.generator_path,
            generation_metadata={
                "generator_path": self.generator_path,
                "fallback": True,
                "strategy": "deterministic_phase_1_stub",
            },
            brief_title=context.title,
            duration_seconds=context.duration_seconds,
            hook_text=hook_text,
            spoken_script=spoken_script,
            overlay_timeline=overlay_timeline,
            caption_variants=caption_variants,
            hashtags=hashtags,
            pinned_comments=pinned_comments,
        )


class RulesPlusProviderScriptGenerator:
    """Production script path that combines provider selection with local script rules."""

    provider_name = "rules_provider"
    generator_path = ScriptGeneratorPath.RULES_PLUS_PROVIDER.value

    def __init__(self, *, provider_name: str | None = None) -> None:
        if provider_name is not None:
            self.provider_name = provider_name

    def generate(self, brief: BriefLike) -> GeneratedScriptOutput:
        context = _normalize_brief(brief)
        hook_text = _build_provider_hook(context)
        spoken_script = _build_provider_spoken_script(context, hook_text)
        hashtags = _build_hashtags(context)
        return GeneratedScriptOutput(
            provider_name=self.provider_name,
            generator_path=self.generator_path,
            generation_metadata={
                "generator_path": self.generator_path,
                "fallback": False,
                "strategy": "rules_plus_provider_v1",
                "provider_name": self.provider_name,
            },
            brief_title=context.title,
            duration_seconds=context.duration_seconds,
            hook_text=hook_text,
            spoken_script=spoken_script,
            overlay_timeline=_build_overlay_timeline(
                context,
                hook_text=hook_text,
                spoken_script=spoken_script,
            ),
            caption_variants=_build_provider_caption_variants(
                context,
                hook_text=hook_text,
                hashtags=hashtags,
            ),
            hashtags=hashtags,
            pinned_comments=_build_pinned_comments(context),
        )


def generate_script_output(
    brief: BriefLike,
    *,
    generator: ScriptGenerator | None = None,
    generator_path: ScriptGeneratorPathLike | None = None,
) -> GeneratedScriptOutput:
    """Generate structured script output with a swappable provider implementation."""

    active_generator = generator or build_script_generator(generator_path)
    return active_generator.generate(brief)


def build_script_generator(
    generator_path: ScriptGeneratorPathLike | None = None,
) -> ScriptGenerator:
    """Build a named script generator path from runtime config."""

    path = normalize_script_generator_path(generator_path)
    if path is ScriptGeneratorPath.DETERMINISTIC_STUB:
        return DeterministicScriptGenerator()
    if path is ScriptGeneratorPath.RULES_PLUS_PROVIDER:
        return RulesPlusProviderScriptGenerator()
    raise ValueError(f"Unsupported script generator path {path.value!r}")


def normalize_script_generator_path(
    generator_path: ScriptGeneratorPathLike | None = None,
) -> ScriptGeneratorPath:
    """Resolve the configured script generation path.

    The production path is the default; tests and smoke runs can opt into the
    deterministic stub by passing ``deterministic_stub`` or setting the env var.
    """

    if generator_path is None:
        raw_path = os.getenv(_SCRIPT_GENERATOR_ENV, ScriptGeneratorPath.RULES_PLUS_PROVIDER.value)
    elif isinstance(generator_path, ScriptGeneratorPath):
        raw_path = generator_path.value
    else:
        raw_path = generator_path
    normalized = raw_path.strip().lower()
    try:
        return ScriptGeneratorPath(normalized)
    except ValueError as exc:
        allowed = ", ".join(path.value for path in ScriptGeneratorPath)
        raise ValueError(
            f"Unknown script generator path {raw_path!r}; expected one of: {allowed}"
        ) from exc


def _normalize_brief(brief: BriefLike) -> ScriptBriefContext:
    if isinstance(brief, PlannedCreativeBrief):
        return ScriptBriefContext(
            title=brief.title,
            description=brief.description,
            duration_seconds=brief.duration_seconds,
            tone=brief.tone,
            tags=tuple(brief.tags),
            page_name=brief.page_name,
            audience=brief.audience,
            content_pillar=brief.content_pillar,
            narrative_goal=brief.narrative_goal,
            primary_call_to_action=brief.primary_call_to_action,
            constraints=brief.constraints,
        )

    return ScriptBriefContext(
        title=brief.title,
        description=brief.description,
        duration_seconds=brief.duration_seconds,
        tone=brief.tone,
        tags=tuple(brief.tags),
        page_name=None,
        audience=None,
        content_pillar=None,
        narrative_goal=None,
        primary_call_to_action=None,
        constraints=PageConstraints(),
    )


def _build_hook(context: ScriptBriefContext) -> str:
    if context.content_pillar and context.audience:
        audience = _trim_phrase(context.audience, max_words=4).lower()
        return f"{context.content_pillar.title()} reset for {audience}"
    if context.content_pillar:
        return f"{context.content_pillar.title()} reset in one reel"
    return f"{context.title}: fast hook"


def _build_spoken_script(
    context: ScriptBriefContext,
    hook_text: str,
) -> list[ScriptBeat]:
    lines = [
        hook_text,
        _setup_line(context),
        _value_line(context),
        _close_line(context),
    ]
    max_words = context.constraints.max_script_words
    if max_words is not None:
        lines = _cap_line_words(lines, max_words=max_words)

    shots = [
        "Open tight on the first frame and land the hook immediately.",
        "Cut to the core setup with a clean visual demonstration.",
        "Show the payoff beat with one concrete example on screen.",
        "End on a simple resolution card with room for captions.",
    ]
    boundaries = _segment_boundaries(context.duration_seconds, len(lines))
    return [
        ScriptBeat(
            start_seconds=boundaries[index],
            end_seconds=boundaries[index + 1],
            narration=line,
            shot_direction=shots[index],
        )
        for index, line in enumerate(lines)
    ]


def _build_provider_hook(context: ScriptBriefContext) -> str:
    if context.narrative_goal:
        goal = _trim_phrase(context.narrative_goal, max_words=7)
        return f"Stop guessing: {goal}"
    if context.content_pillar and context.audience:
        audience = _trim_phrase(context.audience, max_words=5).lower()
        return f"{context.content_pillar.title()} that finally works for {audience}"
    if context.content_pillar:
        return f"The {context.content_pillar.lower()} move worth saving"
    return f"{context.title}: the part viewers need first"


def _build_provider_spoken_script(
    context: ScriptBriefContext,
    hook_text: str,
) -> list[ScriptBeat]:
    audience = context.audience or "the viewer"
    pillar = context.content_pillar or context.title
    lines = [
        hook_text,
        f"Name the {pillar.lower()} problem in the words {audience.lower()} already use.",
        _provider_value_line(context),
        _close_line(context),
    ]
    max_words = context.constraints.max_script_words
    if max_words is not None:
        lines = _cap_line_words(lines, max_words=max_words)

    shots = [
        "Open on the clearest visual proof, with motion already in frame.",
        "Show the before-state or common mistake without adding extra exposition.",
        "Demonstrate the useful step with a tight cutaway and readable hands.",
        "Hold the final frame long enough for the CTA or disclosure to land.",
    ]
    boundaries = _segment_boundaries(context.duration_seconds, len(lines))
    return [
        ScriptBeat(
            start_seconds=boundaries[index],
            end_seconds=boundaries[index + 1],
            narration=line,
            shot_direction=shots[index],
        )
        for index, line in enumerate(lines)
    ]


def _provider_value_line(context: ScriptBriefContext) -> str:
    if context.narrative_goal:
        return f"Make the payoff concrete: {_trim_phrase(context.narrative_goal, max_words=10)}."
    return "Make the payoff concrete with one action the viewer can repeat today."


def _build_overlay_timeline(
    context: ScriptBriefContext,
    *,
    hook_text: str,
    spoken_script: list[ScriptBeat],
) -> list[OverlayCue]:
    overlays = [
        OverlayCue(
            start_seconds=spoken_script[0].start_seconds,
            end_seconds=spoken_script[0].end_seconds,
            text=hook_text,
            emphasis=ScriptOverlayEmphasis.HOOK,
        ),
        OverlayCue(
            start_seconds=spoken_script[1].start_seconds,
            end_seconds=spoken_script[1].end_seconds,
            text=_short_overlay_text(context.content_pillar or context.title),
            emphasis=ScriptOverlayEmphasis.VALUE,
        ),
        OverlayCue(
            start_seconds=spoken_script[2].start_seconds,
            end_seconds=spoken_script[2].end_seconds,
            text=_short_overlay_text(context.narrative_goal or "Show the payoff"),
            emphasis=ScriptOverlayEmphasis.VALUE,
        ),
    ]
    final_emphasis = ScriptOverlayEmphasis.CTA
    final_text = _short_overlay_text(_close_overlay_text(context))
    if context.constraints.required_disclosures:
        final_emphasis = ScriptOverlayEmphasis.DISCLOSURE
        final_text = context.constraints.required_disclosures[0]
    overlays.append(
        OverlayCue(
            start_seconds=spoken_script[3].start_seconds,
            end_seconds=spoken_script[3].end_seconds,
            text=final_text,
            emphasis=final_emphasis,
        )
    )
    return overlays


def _build_caption_variants(
    context: ScriptBriefContext,
    *,
    hook_text: str,
    hashtags: list[str],
) -> list[CaptionVariant]:
    disclosure = _disclosure_suffix(context)
    standard_cta = _caption_close(context)
    return [
        CaptionVariant(
            variant=CaptionVariantName.SHORT,
            text=f"{hook_text}. {standard_cta}{disclosure}".strip(),
        ),
        CaptionVariant(
            variant=CaptionVariantName.STANDARD,
            text=(
                f"{_base_caption(context)} {standard_cta} "
                f"Hashtags ready: {' '.join(hashtags)}{disclosure}"
            ).strip(),
        ),
        CaptionVariant(
            variant=CaptionVariantName.ENGAGEMENT,
            text=f"{hook_text}. What would you add to this workflow?{disclosure}".strip(),
        ),
    ]


def _build_provider_caption_variants(
    context: ScriptBriefContext,
    *,
    hook_text: str,
    hashtags: list[str],
) -> list[CaptionVariant]:
    disclosure = _disclosure_suffix(context)
    standard_cta = _caption_close(context)
    pillar = context.content_pillar or context.title
    return [
        CaptionVariant(
            variant=CaptionVariantName.SHORT,
            text=f"{hook_text}. Save this for your next {pillar.lower()} pass.{disclosure}".strip(),
        ),
        CaptionVariant(
            variant=CaptionVariantName.STANDARD,
            text=(
                f"{_base_caption(context)} Built around one clear hook, one proof beat, "
                f"and one action. {standard_cta} {' '.join(hashtags)}{disclosure}"
            ).strip(),
        ),
        CaptionVariant(
            variant=CaptionVariantName.ENGAGEMENT,
            text=f"{hook_text}. Which beat should become the next reel?{disclosure}".strip(),
        ),
    ]


def _build_hashtags(context: ScriptBriefContext) -> list[str]:
    limit = context.constraints.max_hashtags if context.constraints.max_hashtags is not None else 6
    candidates = [
        context.content_pillar,
        context.page_name,
        *context.tags,
        context.tone,
    ]
    hashtags: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate is None:
            continue
        slug = _slugify(candidate)
        if not slug:
            continue
        hashtag = f"#{slug}"
        lowered = hashtag.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        hashtags.append(hashtag)
        if len(hashtags) >= limit:
            break
    return hashtags


def _build_pinned_comments(context: ScriptBriefContext) -> list[PinnedComment]:
    comments: list[PinnedComment] = []
    if context.primary_call_to_action and context.constraints.allow_direct_cta:
        comments.append(
            PinnedComment(
                text=f"{context.primary_call_to_action} What should we cover next?",
                purpose=PinnedCommentPurpose.ENGAGEMENT,
            )
        )
    if context.constraints.required_disclosures:
        comments.append(
            PinnedComment(
                text=context.constraints.required_disclosures[0],
                purpose=PinnedCommentPurpose.DISCLOSURE,
            )
        )
    return comments


def _setup_line(context: ScriptBriefContext) -> str:
    audience = context.audience or "your audience"
    pillar = context.content_pillar or context.title
    return f"Set up the core {pillar.lower()} idea for {audience.lower()} with one plain-language step."


def _value_line(context: ScriptBriefContext) -> str:
    if context.narrative_goal:
        return _trim_phrase(context.narrative_goal, max_words=12)
    return "Show the useful proof point before the viewer can scroll away."


def _close_line(context: ScriptBriefContext) -> str:
    if context.primary_call_to_action and context.constraints.allow_direct_cta:
        return context.primary_call_to_action
    if context.constraints.required_disclosures:
        return context.constraints.required_disclosures[0]
    return "End with one practical takeaway the editor can hold on screen."


def _close_overlay_text(context: ScriptBriefContext) -> str:
    if context.primary_call_to_action and context.constraints.allow_direct_cta:
        return context.primary_call_to_action
    return "Clean ending beat"


def _base_caption(context: ScriptBriefContext) -> str:
    if context.description:
        return context.description
    if context.content_pillar and context.page_name:
        return f"{context.page_name} breaks down {context.content_pillar} in a practical short-form reel."
    return f"{context.title} is packaged as a practical short-form reel."


def _caption_close(context: ScriptBriefContext) -> str:
    if context.primary_call_to_action and context.constraints.allow_direct_cta:
        return context.primary_call_to_action
    return "Keep the ending clean and useful."


def _disclosure_suffix(context: ScriptBriefContext) -> str:
    if not context.constraints.required_disclosures:
        return ""
    return f" Disclosure: {context.constraints.required_disclosures[0]}"


def _cap_line_words(lines: list[str], *, max_words: int) -> list[str]:
    if max_words <= 0:
        return lines
    remaining_words = max_words
    remaining_lines = len(lines)
    capped_lines: list[str] = []
    for line in lines:
        words = line.split()
        budget = max(3, remaining_words // remaining_lines) if remaining_lines else len(words)
        used_budget = min(len(words), budget)
        capped_line = " ".join(words[:used_budget]).strip()
        capped_lines.append(capped_line or words[0])
        remaining_words = max(0, remaining_words - len(capped_line.split()))
        remaining_lines -= 1
    return capped_lines


def _segment_boundaries(duration_seconds: int, segment_count: int) -> list[int]:
    base_length, remainder = divmod(duration_seconds, segment_count)
    lengths = [base_length + (1 if index < remainder else 0) for index in range(segment_count)]
    boundaries = [0]
    elapsed = 0
    for length in lengths[:-1]:
        elapsed += length
        boundaries.append(elapsed)
    boundaries.append(duration_seconds)
    return boundaries


def _short_overlay_text(value: str) -> str:
    return _trim_phrase(value, max_words=6)


def _trim_phrase(value: str, *, max_words: int) -> str:
    words = value.split()
    if len(words) <= max_words:
        return value.strip()
    return " ".join(words[:max_words]).strip()


def _slugify(value: str) -> str:
    normalized = []
    for character in value.strip().lower():
        normalized.append(character if character.isalnum() else "-")
    return "".join(part for part in "".join(normalized).split("-"))


__all__ = [
    "BriefLike",
    "DeterministicScriptGenerator",
    "RulesPlusProviderScriptGenerator",
    "ScriptGeneratorPathLike",
    "ScriptGenerator",
    "build_script_generator",
    "generate_script_output",
    "normalize_script_generator_path",
]
