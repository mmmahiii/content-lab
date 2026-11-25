"""Quick Reel branches: 'what happens next' options after a chosen hook.

Three choice moments, each with 2-3 options:

- ``structure`` - where the reel goes after the hook (its middle beats)
- ``energy`` - pacing: chill, punchy or dramatic (timing, music mood)
- ``ending`` - how it lands (the final beat)

Any one option from each moment composes (``compose_reel``) into the pipeline's
``overlay_timeline`` / ``spoken_script`` / scene shape, which
``packages/reel-templates`` renders directly.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from content_lab_creative.generation.context import (
    BEAT_OVERLAY_MAX_CHARS,
    BEAT_OVERLAY_MAX_WORDS,
    VIEWER_COPY_RULES,
    CreativePageContext,
    check_viewer_copy,
    check_word_budget,
    render_page_brief,
)
from content_lab_creative.generation.hooks import HookCandidate
from content_lab_creative.persona import PageConstraints
from content_lab_creative.types import OverlayCue, ScriptBeat, ScriptOverlayEmphasis
from content_lab_intelligence import LLMClient, LLMError, StructuredRequest

logger = logging.getLogger(__name__)

MIN_REEL_SECONDS = 8
MAX_REEL_SECONDS = 60
MIN_BEAT_SECONDS = 2


class ChoiceMoment(str, Enum):
    STRUCTURE = "structure"
    ENERGY = "energy"
    ENDING = "ending"


class Pace(str, Enum):
    CHILL = "chill"
    PUNCHY = "punchy"
    DRAMATIC = "dramatic"


class EndingStyle(str, Enum):
    REVEAL = "reveal"
    BEFORE_AFTER = "before_after"
    CLIFFHANGER = "cliffhanger"
    CALL_TO_ACTION = "call_to_action"
    PUNCHLINE = "punchline"


class ContinuationBeat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    narration: str = Field(min_length=1, max_length=220, description="Spoken line.")
    overlay_text: str = Field(
        min_length=1,
        max_length=BEAT_OVERLAY_MAX_CHARS,
        description=f"On-screen text, at most {BEAT_OVERLAY_MAX_WORDS} words.",
    )
    shot_direction: str = Field(
        min_length=1, max_length=220, description="Creator-facing: what this beat shows."
    )
    seconds: int = Field(ge=1, le=10)

    @field_validator("narration")
    @classmethod
    def _narration(cls, value: str, info: ValidationInfo) -> str:
        return check_viewer_copy(value.strip(), info)

    @field_validator("overlay_text")
    @classmethod
    def _overlay(cls, value: str, info: ValidationInfo) -> str:
        check_word_budget(value, max_words=BEAT_OVERLAY_MAX_WORDS)
        return check_viewer_copy(value.strip(), info, overlay=True)


class _OptionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_id: str = Field(
        min_length=1, max_length=40, description="Short slug, unique per moment."
    )
    label: str = Field(min_length=1, max_length=28, description="Choice card title.")
    teaser: str = Field(min_length=1, max_length=80, description="Choice card subtitle.")


class StructureOption(_OptionBase):
    beats: list[ContinuationBeat] = Field(min_length=2, max_length=4)


class EnergyOption(_OptionBase):
    pace: Pace
    duration_scale: float = Field(ge=0.7, le=1.4, description="Multiplies beat lengths.")
    music_mood: str = Field(min_length=1, max_length=60)


class EndingOption(_OptionBase):
    style: EndingStyle
    beat: ContinuationBeat


class BranchSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    structure: list[StructureOption] = Field(min_length=2, max_length=3)
    energy: list[EnergyOption] = Field(min_length=2, max_length=3)
    ending: list[EndingOption] = Field(min_length=2, max_length=3)

    @model_validator(mode="after")
    def _distinct(self, info: ValidationInfo) -> BranchSet:
        expected = (info.context or {}).get("options_per_moment")
        groups: dict[str, list[_OptionBase]] = {
            "structure": list(self.structure),
            "energy": list(self.energy),
            "ending": list(self.ending),
        }
        for name, options in groups.items():
            if expected is not None and len(options) != expected:
                raise ValueError(f"{name} needs exactly {expected} options, got {len(options)}")
            ids = [option.option_id for option in options]
            if len(set(ids)) != len(ids):
                raise ValueError(f"{name} option_ids must be unique")
            labels = [option.label.casefold() for option in options]
            if len(set(labels)) != len(labels):
                raise ValueError(f"{name} labels must be different")
        if len({option.pace for option in self.energy}) != len(self.energy):
            raise ValueError("each energy option needs a different pace")
        max_words = (info.context or {}).get("max_script_words")
        hook_words = int((info.context or {}).get("hook_words") or 0)
        if max_words:
            for structure in self.structure:
                for ending in self.ending:
                    words = hook_words
                    words += sum(len(beat.narration.split()) for beat in structure.beats)
                    words += len(ending.beat.narration.split())
                    if words > max_words:
                        raise ValueError(
                            f"structure {structure.option_id!r} with ending "
                            f"{ending.option_id!r} has {words} spoken words; limit {max_words}"
                        )
        return self

    def option(self, moment: ChoiceMoment, option_id: str) -> _OptionBase:
        options: list[_OptionBase] = list(getattr(self, moment.value))
        for option in options:
            if option.option_id == option_id:
                return option
        known = ", ".join(option.option_id for option in options)
        raise ValueError(f"unknown {moment.value} option {option_id!r}; expected one of: {known}")


class BranchSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    structure: str = Field(min_length=1, max_length=40)
    energy: str = Field(min_length=1, max_length=40)
    ending: str = Field(min_length=1, max_length=40)

    @classmethod
    def first_of(cls, branches: BranchSet) -> BranchSelection:
        return cls(
            structure=branches.structure[0].option_id,
            energy=branches.energy[0].option_id,
            ending=branches.ending[0].option_id,
        )


class ComposedScene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str
    purpose: Literal["hook", "setup", "value", "payoff", "close"]
    start_seconds: int
    end_seconds: int
    narration: str
    overlay_text: str
    overlay_role: Literal["hook", "emphasis", "cta", "disclosure"]
    shot_guidance: str


class ComposedReel(BaseModel):
    """One fully chosen Quick Reel, in the shapes editing, QA and reel-templates consume."""

    model_config = ConfigDict(extra="forbid")

    selection: BranchSelection
    duration_seconds: int
    pace: Pace
    music_mood: str
    ending_style: EndingStyle
    overlay_timeline: list[OverlayCue]
    spoken_script: list[ScriptBeat]
    scenes: list[ComposedScene]


class BranchGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: CreativePageContext
    hook: HookCandidate
    topic: str | None = Field(default=None, max_length=200)
    asset_labels: list[str] = Field(default_factory=list, max_length=60)
    duration_seconds: int = Field(default=15, ge=MIN_REEL_SECONDS, le=MAX_REEL_SECONDS)
    moments: list[ChoiceMoment] = Field(
        default_factory=lambda: list(ChoiceMoment), min_length=1, max_length=3
    )
    options_per_moment: int = Field(default=3, ge=2, le=3)

    @field_validator("moments")
    @classmethod
    def _unique_moments(cls, value: list[ChoiceMoment]) -> list[ChoiceMoment]:
        if len(set(value)) != len(value):
            raise ValueError("moments must be unique")
        return value


class BranchGenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hook: HookCandidate
    moments: list[ChoiceMoment]
    branches: BranchSet
    default_selection: BranchSelection
    preview: ComposedReel
    source: Literal["llm", "fallback"]
    niche: str
    usage: dict[str, Any] | None = None
    fallback_reason: str | None = None


_SYSTEM_PROMPT = f"""\
You design interactive short vertical videos. The viewer has just watched the hook. \
You write what can happen next as choice cards, and each choice must make the rest of \
the reel genuinely different.

{VIEWER_COPY_RULES}

Return three moments:
- structure: 2-4 middle beats each, a different narrative route (e.g. step-by-step \
breakdown, mistake-then-fix, secret reveal, myth vs truth).
- energy: one option per pace (chill, punchy, dramatic) with a duration_scale and a music mood.
- ending: one final beat each, different styles (reveal, before_after, cliffhanger, \
call_to_action, punchline).

Every structure option must pay off the hook's payoff_promise and work with every ending.
Labels are 1-3 words that make someone want to tap; teasers are one short line.
Beat overlay_text: at most {BEAT_OVERLAY_MAX_WORDS} words and {BEAT_OVERLAY_MAX_CHARS} \
characters."""


def build_branch_prompt(request: BranchGenerationRequest) -> str:
    niche = request.page.niche_profile(topic=request.topic)
    brief = render_page_brief(
        request.page, topic=request.topic, asset_labels=request.asset_labels, niche=niche
    )
    hook = request.hook
    return (
        f"{brief}\n\n"
        "Chosen hook:\n"
        f"- mechanism: {hook.mechanism.value}\n"
        f"- on screen: {hook.overlay_text}\n"
        f"- spoken: {hook.spoken_line}\n"
        f"- first frame: {hook.visual_direction}\n"
        f"- must pay off: {hook.payoff_promise}\n\n"
        f"Target length about {request.duration_seconds} seconds including a 3-second hook. "
        f"Return exactly {request.options_per_moment} options for each moment."
    )


def generate_branches(
    request: BranchGenerationRequest, *, client: LLMClient | None
) -> BranchGenerationResult:
    niche = request.page.niche_profile(topic=request.topic)
    if client is None:
        return _result(request, fallback_branches(request), niche.key, reason="llm_not_configured")
    context = {
        **request.page.validation_context(),
        "options_per_moment": request.options_per_moment,
        "hook_words": len(request.hook.spoken_line.split()),
    }
    try:
        result = client.generate_structured(
            StructuredRequest(
                purpose="quick_reel_branches",
                system=_SYSTEM_PROMPT,
                prompt=build_branch_prompt(request),
                output_model=BranchSet,
                max_tokens=8_000,
                validation_context=context,
            )
        )
    except LLMError as exc:
        logger.warning("branch generation fell back: %s", exc)
        return _result(request, fallback_branches(request), niche.key, reason=type(exc).__name__)
    return _result(request, result.output, niche.key, usage=result.usage.as_dict())


def compose_reel(
    *,
    hook: HookCandidate,
    branches: BranchSet,
    selection: BranchSelection,
    duration_seconds: int | None = None,
    constraints: PageConstraints | None = None,
) -> ComposedReel:
    structure = branches.option(ChoiceMoment.STRUCTURE, selection.structure)
    energy = branches.option(ChoiceMoment.ENERGY, selection.energy)
    ending = branches.option(ChoiceMoment.ENDING, selection.ending)
    assert isinstance(structure, StructureOption)
    assert isinstance(energy, EnergyOption)
    assert isinstance(ending, EndingOption)

    hook_seconds = 2 if energy.pace is Pace.PUNCHY else 3
    body = [*structure.beats, ending.beat]
    body_seconds = _scaled_seconds(
        [beat.seconds for beat in body],
        scale=energy.duration_scale,
        # The requested length is the base; the energy choice stretches or tightens it.
        target_total=None if duration_seconds is None else duration_seconds - 3,
    )

    disclosures = list(constraints.required_disclosures) if constraints else []
    rows: list[tuple[str, str, str, int]] = [
        (hook.spoken_line, hook.overlay_text, hook.visual_direction, hook_seconds)
    ]
    rows.extend(
        (beat.narration, beat.overlay_text, beat.shot_direction, seconds)
        for beat, seconds in zip(body, body_seconds, strict=True)
    )

    overlays: list[OverlayCue] = []
    spoken: list[ScriptBeat] = []
    scenes: list[ComposedScene] = []
    cursor = 0
    last = len(rows) - 1
    for index, (narration, overlay_text, shot, seconds) in enumerate(rows):
        start, end = cursor, cursor + seconds
        cursor = end
        if index == 0:
            emphasis, role, purpose = ScriptOverlayEmphasis.HOOK, "hook", "hook"
        elif index == last:
            emphasis, role, purpose = ScriptOverlayEmphasis.CTA, "cta", "close"
            if disclosures:
                emphasis, role, overlay_text = (
                    ScriptOverlayEmphasis.DISCLOSURE,
                    "disclosure",
                    disclosures[0],
                )
        else:
            emphasis, role = ScriptOverlayEmphasis.VALUE, "emphasis"
            purpose = "setup" if index == 1 else ("payoff" if index == last - 1 else "value")
        overlays.append(
            OverlayCue(start_seconds=start, end_seconds=end, text=overlay_text, emphasis=emphasis)
        )
        spoken.append(
            ScriptBeat(
                start_seconds=start,
                end_seconds=end,
                narration=narration[:280],
                shot_direction=shot[:280],
            )
        )
        scenes.append(
            ComposedScene(
                scene_id=f"scene_{index + 1}_{purpose}",
                purpose=purpose,  # type: ignore[arg-type]
                start_seconds=start,
                end_seconds=end,
                narration=narration,
                overlay_text=overlay_text,
                overlay_role=role,  # type: ignore[arg-type]
                shot_guidance=shot,
            )
        )

    return ComposedReel(
        selection=selection,
        duration_seconds=cursor,
        pace=energy.pace,
        music_mood=energy.music_mood,
        ending_style=ending.style,
        overlay_timeline=overlays,
        spoken_script=spoken,
        scenes=scenes,
    )


def fallback_branches(request: BranchGenerationRequest) -> BranchSet:
    """Deterministic, topic-aware branch set used when no LLM is available."""

    subject = request.page.subject(request.topic).lower()
    n = request.options_per_moment

    def beat(narration: str, overlay: str, shot: str, seconds: int = 3) -> ContinuationBeat:
        return ContinuationBeat(
            narration=narration, overlay_text=overlay, shot_direction=shot, seconds=seconds
        )

    structures = [
        StructureOption(
            option_id="breakdown",
            label="Quick breakdown",
            teaser="Three clear steps, no fluff",
            beats=[
                beat(f"First, get your {subject} ready.", "Step 1: get ready", "Wide setup"),
                beat("Then do the one move that matters most.", "Step 2: the key move", "Close-up"),
                beat("Finish it with care, not speed.", "Step 3: finish clean", "Result detail"),
            ],
        ),
        StructureOption(
            option_id="mistake_fix",
            label="Mistake, then fix",
            teaser="The common slip and how to dodge it",
            beats=[
                beat(f"Most people rush this part of {subject}.", "The common mistake", "Before"),
                beat("Slow down here and it all changes.", "The simple fix", "After"),
            ],
        ),
        StructureOption(
            option_id="secret_reveal",
            label="Secret reveal",
            teaser="Build up to the one thing that matters",
            beats=[
                beat("It's not the obvious part.", "Not what you think", "Tease the detail"),
                beat(f"It's this small {subject} detail.", "This is the secret", "Hero close-up"),
            ],
        ),
    ]
    energies = [
        EnergyOption(
            option_id="chill",
            label="Chill & satisfying",
            teaser="Slow, smooth, easy to watch",
            pace=Pace.CHILL,
            duration_scale=1.2,
            music_mood="warm lo-fi",
        ),
        EnergyOption(
            option_id="punchy",
            label="Fast & punchy",
            teaser="Quick cuts, big energy",
            pace=Pace.PUNCHY,
            duration_scale=0.8,
            music_mood="upbeat percussive",
        ),
        EnergyOption(
            option_id="dramatic",
            label="Dramatic",
            teaser="Slow build, big moment",
            pace=Pace.DRAMATIC,
            duration_scale=1.1,
            music_mood="cinematic build",
        ),
    ]
    endings = [
        EndingOption(
            option_id="reveal",
            label="Big reveal",
            teaser="End on the finished result",
            style=EndingStyle.REVEAL,
            beat=beat("And that's the result.", "The finished result", "Hold on the result", 3),
        ),
        EndingOption(
            option_id="part_two",
            label="Part 2?",
            teaser="Leave them wanting more",
            style=EndingStyle.CLIFFHANGER,
            beat=beat("But there's one more trick.", "Part 2 next?", "Freeze on a tease", 3),
        ),
        EndingOption(
            option_id="save_it",
            label="Save it",
            teaser="A clean takeaway to keep",
            style=EndingStyle.CALL_TO_ACTION,
            beat=beat("Save this for next time.", "Save this one", "End card", 3),
        ),
    ]
    return BranchSet(structure=structures[:n], energy=energies[:n], ending=endings[:n])


def _result(
    request: BranchGenerationRequest,
    branches: BranchSet,
    niche_key: str,
    *,
    usage: dict[str, Any] | None = None,
    reason: str | None = None,
) -> BranchGenerationResult:
    selection = BranchSelection.first_of(branches)
    return BranchGenerationResult(
        hook=request.hook,
        moments=request.moments,
        branches=branches,
        default_selection=selection,
        preview=compose_reel(
            hook=request.hook,
            branches=branches,
            selection=selection,
            duration_seconds=request.duration_seconds,
            constraints=request.page.constraints,
        ),
        source="fallback" if reason else "llm",
        niche=niche_key,
        usage=usage,
        fallback_reason=reason,
    )


def _scaled_seconds(seconds: list[int], *, scale: float, target_total: int | None) -> list[int]:
    scaled = [max(MIN_BEAT_SECONDS, round(value * scale)) for value in seconds]
    if target_total is None:
        return scaled
    target = max(round(target_total * scale), MIN_BEAT_SECONDS * len(scaled))
    target = min(target, MAX_REEL_SECONDS - 3)
    current = sum(scaled)
    factor = target / current
    fitted = [max(MIN_BEAT_SECONDS, round(value * factor)) for value in scaled]
    # Absorb rounding error one second at a time, spread from the longest beats, so the
    # total is exact and no beat drops below the floor.
    drift = target - sum(fitted)
    while drift != 0:
        step = 1 if drift > 0 else -1
        candidates = [i for i in range(len(fitted)) if step > 0 or fitted[i] > MIN_BEAT_SECONDS]
        if not candidates:
            break
        index = max(candidates, key=lambda i: (fitted[i] * -step, i))
        fitted[index] += step
        drift -= step
    return fitted


__all__ = [
    "BranchGenerationRequest",
    "BranchGenerationResult",
    "BranchSelection",
    "BranchSet",
    "ChoiceMoment",
    "ComposedReel",
    "ComposedScene",
    "ContinuationBeat",
    "EndingOption",
    "EndingStyle",
    "EnergyOption",
    "Pace",
    "StructureOption",
    "compose_reel",
    "fallback_branches",
    "generate_branches",
]
