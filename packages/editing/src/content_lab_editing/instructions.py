"""Edit instruction models for the video/image editing pipeline."""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from content_lab_core.models import DomainModel


class EditOperation(str, Enum):
    """Supported editing operations."""

    TRIM = "trim"
    CONCAT = "concat"
    OVERLAY_TEXT = "overlay_text"
    OVERLAY_IMAGE = "overlay_image"
    TRANSITION = "transition"
    RESIZE = "resize"


class EditInstruction(DomainModel):
    """A single editing instruction within a pipeline."""

    operation: EditOperation
    params: dict[str, object] = Field(default_factory=dict)
    source_uri: str = ""
    output_uri: str = ""


class EditPlan(DomainModel):
    """An ordered list of edit instructions that form a complete editing pipeline."""

    run_id: str
    instructions: list[EditInstruction] = Field(default_factory=list)

    @property
    def step_count(self) -> int:
        return len(self.instructions)
