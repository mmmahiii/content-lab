"""Narrative guidance for cinematic reel planning prompts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NarrativeBeat(BaseModel):
    """One expected visual-first narrative beat."""

    model_config = ConfigDict(extra="forbid")

    beat: str = Field(min_length=1)
    start_time: float = Field(ge=0)
    end_time: float = Field(gt=0)
    purpose: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_span(self) -> NarrativeBeat:
        if self.end_time <= self.start_time:
            raise ValueError("narrative beat end_time must be greater than start_time")
        return self


def default_narrative_arc(duration_seconds: float) -> list[NarrativeBeat]:
    """Return deterministic narrative beat guidance for a short vertical reel."""

    duration = max(4.0, float(duration_seconds))
    hook_end = round(min(duration * 0.22, 1.4), 2)
    development_end = round(min(duration * 0.58, hook_end + 2.4), 2)
    payoff_end = round(min(duration * 0.86, development_end + 2.2), 2)
    return [
        NarrativeBeat(
            beat="hook",
            start_time=0.0,
            end_time=hook_end,
            purpose="Open on visual motion or tactile evidence before text explains it.",
        ),
        NarrativeBeat(
            beat="development",
            start_time=hook_end,
            end_time=development_end,
            purpose="Let selected assets interact as one coherent filmed moment.",
        ),
        NarrativeBeat(
            beat="reveal_payoff",
            start_time=development_end,
            end_time=payoff_end,
            purpose="Reveal the main result, object, or reason for the scene.",
        ),
        NarrativeBeat(
            beat="closing_retention_loop",
            start_time=payoff_end,
            end_time=round(duration, 2),
            purpose="End on a clean frame that can loop into the opening.",
        ),
    ]


def narrative_arc_prompt_text(duration_seconds: float) -> str:
    """Format the default arc as prompt-readable guidance."""

    return "\n".join(
        f"- {beat.start_time:.2f}-{beat.end_time:.2f}s: {beat.beat} - {beat.purpose}"
        for beat in default_narrative_arc(duration_seconds)
    )


__all__ = ["NarrativeBeat", "default_narrative_arc", "narrative_arc_prompt_text"]
