"""Page context handed to every LLM generator, and the copy rules applied to its output."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo

from content_lab_creative.copy_lint import evaluate_user_facing_text
from content_lab_creative.niche import NicheProfile, resolve_niche_profile
from content_lab_creative.persona import PageConstraints, PageMetadata

# On-screen text budgets (fit the editing layout's two-line hook and the QA clip warning).
HOOK_OVERLAY_MAX_CHARS = 72
HOOK_OVERLAY_MAX_WORDS = 12
BEAT_OVERLAY_MAX_CHARS = 56
BEAT_OVERLAY_MAX_WORDS = 9

# Production instructions that must never be shown or spoken to viewers. Kept to phrasing
# that is about editing a video, so ordinary advice ("Start with the hardest task") passes.
_CREATOR_DIRECTION = re.compile(
    r"^\s*(open with|open on|close with|close on|cut to|cut away|show the|film|shoot|"
    r"b-roll|pan to|zoom (in|out)|demonstrate the)\b",
    re.IGNORECASE,
)
_AUDIENCE_REFERENCE = re.compile(r"\b(the viewer|the viewers|the audience)\b", re.IGNORECASE)


class CreativePageContext(BaseModel):
    """Everything a generator may know about the page it writes for."""

    model_config = ConfigDict(extra="forbid")

    page_name: str = Field(min_length=1, max_length=200)
    handle: str | None = Field(default=None, max_length=120)
    niche: str | None = Field(default=None, max_length=120)
    audience: str | None = Field(default=None, max_length=240)
    persona_label: str | None = Field(default=None, max_length=160)
    brand_tone: list[str] = Field(default_factory=list, max_length=12)
    content_pillars: list[str] = Field(default_factory=list, max_length=12)
    differentiators: list[str] = Field(default_factory=list, max_length=12)
    primary_call_to_action: str | None = Field(default=None, max_length=240)
    constraints: PageConstraints = Field(default_factory=PageConstraints)

    @classmethod
    def from_page(
        cls,
        *,
        display_name: str,
        handle: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        niche: str | None = None,
    ) -> CreativePageContext:
        raw = dict(metadata or {})
        explicit_niche = niche or _str_or_none(raw.get("niche"))
        try:
            page_metadata = PageMetadata.model_validate(
                {key: raw[key] for key in ("persona", "constraints") if key in raw}
            )
        except ValidationError:
            page_metadata = PageMetadata()
        persona = page_metadata.persona
        return cls(
            page_name=display_name.strip()[:200] or "Untitled page",
            handle=(handle or None),
            niche=explicit_niche,
            audience=persona.audience if persona else None,
            persona_label=persona.label if persona else None,
            brand_tone=list(persona.brand_tone) if persona else [],
            content_pillars=list(persona.content_pillars) if persona else [],
            differentiators=list(persona.differentiators) if persona else [],
            primary_call_to_action=persona.primary_call_to_action if persona else None,
            constraints=page_metadata.constraints,
        )

    def niche_profile(self, *, topic: str | None = None) -> NicheProfile:
        text = " ".join(
            part
            for part in (self.page_name, topic or "", *self.content_pillars, self.audience or "")
            if part
        )
        return resolve_niche_profile(self.niche, text=text)

    def subject(self, topic: str | None = None) -> str:
        """Short subject phrase for fallback copy."""

        raw = (topic or "").strip() or (self.content_pillars[0] if self.content_pillars else "")
        raw = raw or self.page_name
        words = raw.split()
        return " ".join(words[:4]).strip().rstrip(".!?,:;")

    def validation_context(self) -> dict[str, Any]:
        constraints = self.constraints
        return {
            "blocked_terms": [
                *constraints.blocked_phrases,
                *constraints.prohibited_claims,
                *constraints.banned_topics,
            ],
            "max_script_words": constraints.max_script_words,
        }


def render_page_brief(
    page: CreativePageContext,
    *,
    topic: str | None,
    asset_labels: Sequence[str],
    niche: NicheProfile,
) -> str:
    """Plain-text brief block shared by every generator prompt."""

    lines = [f"Page: {page.page_name}" + (f" (@{page.handle})" if page.handle else "")]
    lines.append(f"Niche: {niche.label}" + (f" ({page.niche})" if page.niche else ""))
    if topic:
        lines.append(f"Topic for this reel: {topic}")
    if page.audience:
        lines.append(f"Audience: {page.audience}")
    if page.persona_label:
        lines.append(f"Persona: {page.persona_label}")
    if page.brand_tone:
        lines.append(f"Brand tone: {', '.join(page.brand_tone)}")
    if page.content_pillars:
        lines.append(f"Content pillars: {', '.join(page.content_pillars)}")
    if page.differentiators:
        lines.append(f"What makes the page different: {', '.join(page.differentiators)}")
    if asset_labels:
        shown = ", ".join(asset_labels[:30])
        lines.append(f"Available visual assets (only promise what these can show): {shown}")
    constraints = page.constraints
    if constraints.banned_topics:
        lines.append(f"Never mention these topics: {', '.join(constraints.banned_topics)}")
    if constraints.blocked_phrases:
        lines.append(f"Never use these phrases: {', '.join(constraints.blocked_phrases)}")
    if constraints.prohibited_claims:
        lines.append(f"Never make these claims: {', '.join(constraints.prohibited_claims)}")
    if constraints.required_disclosures:
        lines.append(
            "A disclosure is added automatically at the end: "
            + "; ".join(constraints.required_disclosures)
        )
    if not constraints.allow_direct_cta:
        lines.append("No direct calls to action (no 'follow', 'buy', 'link in bio').")
    elif page.primary_call_to_action:
        lines.append(f"Preferred call to action: {page.primary_call_to_action}")
    if constraints.max_script_words:
        lines.append(f"Total spoken words must stay under {constraints.max_script_words}.")
    if niche.creative_guidance:
        lines.append(f"Niche guidance: {niche.creative_guidance}")
    return "\n".join(lines)


VIEWER_COPY_RULES = """\
Viewer-facing fields (overlay_text, narration, spoken_line, captions) are finished copy the \
audience reads or hears, in the page's own voice.
- Never write instructions to the creator in them ("Show...", "Open with...", "Cut to...", \
"the viewer..."). Put production directions only in direction fields \
(visual_direction, shot_direction, direction).
- Be concrete and specific to the topic. No generic filler that would fit any page.
- No hashtags or emojis in overlay_text. No mention of AI, prompts, plans, modes or \
internal labels.
- Only promise what the listed assets can actually show."""


def viewer_copy_problems(
    text: str,
    context: Mapping[str, Any] | None,
    *,
    caption: bool = False,
    overlay: bool = False,
) -> list[str]:
    problems: list[str] = []
    if _CREATOR_DIRECTION.search(text) or _AUDIENCE_REFERENCE.search(text):
        problems.append(
            "reads like an instruction to the creator; write finished viewer copy instead"
        )
    if overlay and "#" in text:
        problems.append("overlay text must not contain hashtags")
    lowered = text.casefold()
    for term in (context or {}).get("blocked_terms", ()) or ():
        if term and str(term).casefold() in lowered:
            problems.append(f"uses a blocked phrase or topic: {term!r}")
    for match in evaluate_user_facing_text(text, caption_scoped=caption):
        if match.severity == "fail":
            problems.append(f"{match.message} (matched {match.matched_text!r})")
    return problems


def check_viewer_copy(
    value: str, info: ValidationInfo, *, caption: bool = False, overlay: bool = False
) -> str:
    problems = viewer_copy_problems(value, info.context, caption=caption, overlay=overlay)
    if problems:
        raise ValueError("; ".join(problems))
    return value


def check_word_budget(value: str, *, max_words: int) -> str:
    if len(value.split()) > max_words:
        raise ValueError(f"must be at most {max_words} words")
    return value


def _str_or_none(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


__all__ = [
    "BEAT_OVERLAY_MAX_CHARS",
    "BEAT_OVERLAY_MAX_WORDS",
    "HOOK_OVERLAY_MAX_CHARS",
    "HOOK_OVERLAY_MAX_WORDS",
    "VIEWER_COPY_RULES",
    "CreativePageContext",
    "check_viewer_copy",
    "check_word_budget",
    "render_page_brief",
    "viewer_copy_problems",
]
