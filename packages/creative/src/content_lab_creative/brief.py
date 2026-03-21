"""Creative brief model for reel content generation."""

from __future__ import annotations

from pydantic import Field

from content_lab_core.models import DomainModel
from content_lab_core.types import Platform


class CreativeBrief(DomainModel):
    """A creative brief describing a single reel to produce."""

    title: str
    description: str = ""
    target_platforms: list[Platform] = Field(default_factory=list)
    tone: str = "neutral"
    duration_seconds: int = 30
    tags: list[str] = Field(default_factory=list)

    @property
    def is_short_form(self) -> bool:
        return self.duration_seconds <= 60
