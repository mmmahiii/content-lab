"""Backward-compatible imports for persona schema models."""

from content_lab_creative.persona.schema import (
    PageConstraints,
    PageMetadata,
    PersonaProfile,
    validate_page_metadata,
    validate_persona_profile,
)

__all__ = [
    "PageConstraints",
    "PageMetadata",
    "PersonaProfile",
    "validate_page_metadata",
    "validate_persona_profile",
]
