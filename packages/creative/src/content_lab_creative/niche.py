"""Niche profiles: the one place niche-specific creative rules live.

Planner heuristics and QA guards that only make sense for some content (for example,
"at most one pan-shaped cut-out per scene" for cooking) read their settings from a
``NicheProfile`` instead of hard-coding them. Register extra niches with
``register_niche_profile``.

When no niche can be resolved, the ``general`` profile applies every registered
single-instance guard, so unknown content never loses a safeguard; a resolved niche
applies only its own.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

GENERAL_NICHE_KEY = "general"
_SINGLE_INSTANCE_SUFFIX = re.compile(
    r"^(?:\d+[a-z0-9]{0,24}|[a-z]{1,16}\d[a-z0-9]{0,24})$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NicheProfile:
    key: str
    label: str
    keywords: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    prompt_paths: tuple[str, ...] = ()
    # Object classes allowed at most once per scene (matched against asset label tokens).
    single_instance_objects: tuple[str, ...] = ()
    creative_guidance: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)

    def matches_text(self, text: str) -> bool:
        lowered = text.lower()
        return any(term in lowered for term in self.keywords)


_BUILTIN_PROFILES: tuple[NicheProfile, ...] = (
    NicheProfile(
        key="cooking",
        label="Cooking & food",
        keywords=("food", "kitchen", "cook", "steak", "sizzle", "steam", "recipe", "baking"),
        aliases=("food", "recipes", "baking", "faceless cooking"),
        prompt_paths=("sensory_hook", "satisfying_process", "cinematic_closeup"),
        single_instance_objects=("pan",),
        creative_guidance=(
            "Lead with texture, colour and visible process. Name real ingredients and steps. "
            "Never claim sizzling, steam or pouring unless the assets show that motion."
        ),
    ),
    NicheProfile(
        key="luxury",
        label="Luxury & premium products",
        keywords=("luxury", "premium", "high end", "jewelry", "watch"),
        aliases=("premium", "jewellery", "watches"),
        prompt_paths=("luxury_reveal", "cinematic_closeup", "product_as_background_payoff"),
        creative_guidance="Slow, confident reveals. Specific materials and craft details.",
    ),
    NicheProfile(
        key="business",
        label="Business & operations",
        keywords=("business", "saas", "service", "founder", "operations"),
        aliases=("startups", "productivity", "saas"),
        prompt_paths=("problem_solution", "educational_overlay", "social_proof"),
        creative_guidance=(
            "One concrete, copyable move per reel. Specific numbers only if they are given."
        ),
    ),
    NicheProfile(
        key="fitness",
        label="Fitness & movement",
        keywords=("fitness", "workout", "gym", "mobility", "exercise", "training plan"),
        aliases=("workouts", "gym", "mobility"),
        prompt_paths=("transformation", "routine_sequence", "educational_overlay"),
        creative_guidance=(
            "Clear form cues and rep counts. No medical claims or guaranteed results."
        ),
    ),
    NicheProfile(
        key="personal_finance",
        label="Personal finance",
        keywords=("finance", "budget", "investing", "savings", "debt"),
        aliases=("finance", "money", "investing"),
        prompt_paths=("problem_solution", "contrast_hook", "educational_overlay"),
        creative_guidance=(
            "Educational framing only: no personalised advice, no promised returns."
        ),
    ),
    NicheProfile(
        key="beauty",
        label="Beauty & skincare",
        keywords=("skincare", "makeup", "beauty", "haircare"),
        aliases=("skincare", "makeup"),
        prompt_paths=("before_after", "cinematic_closeup", "routine_sequence"),
        creative_guidance="Honest before/after framing. No medical or permanent-result claims.",
    ),
    NicheProfile(
        key="travel",
        label="Travel & places",
        keywords=("travel", "destination", "itinerary", "hotel", "city guide"),
        aliases=("destinations",),
        prompt_paths=("curiosity_gap", "ambient_lifestyle", "cinematic_closeup"),
        creative_guidance="Specific places and moments. Avoid generic 'hidden gem' filler.",
    ),
)

GENERAL_PROFILE = NicheProfile(
    key=GENERAL_NICHE_KEY,
    label="General",
    creative_guidance="Be specific to the topic; avoid generic filler that fits any page.",
)

_REGISTRY: dict[str, NicheProfile] = {profile.key: profile for profile in _BUILTIN_PROFILES}


def register_niche_profile(profile: NicheProfile, *, replace: bool = False) -> None:
    key = _normalize_key(profile.key)
    if key == GENERAL_NICHE_KEY:
        raise ValueError("the general profile cannot be replaced")
    if key in _REGISTRY and not replace:
        raise ValueError(f"niche profile {key!r} is already registered")
    _REGISTRY[key] = profile


def registered_niche_profiles() -> tuple[NicheProfile, ...]:
    return tuple(_REGISTRY.values())


def resolve_niche_profile(niche: str | None = None, *, text: str = "") -> NicheProfile:
    """Explicit niche (key or alias) wins; otherwise the first profile whose keywords match."""

    if niche and niche.strip():
        key = _normalize_key(niche)
        if key == GENERAL_NICHE_KEY:
            return GENERAL_PROFILE
        if key in _REGISTRY:
            return _REGISTRY[key]
        lowered = niche.strip().lower()
        for profile in _REGISTRY.values():
            if lowered in profile.aliases:
                return profile
        text = f"{niche} {text}"
    for profile in _REGISTRY.values():
        if profile.matches_text(text):
            return profile
    return GENERAL_PROFILE


def niche_from_mapping(context: Mapping[str, Any]) -> str | None:
    """Read an explicit niche from a page/planner context dict, if one is set."""

    for key in ("niche", "niche_key"):
        value = context.get(key)
        if isinstance(value, str) and value.strip():
            return value
    for nested_key in ("page", "page_metadata", "metadata"):
        nested = context.get(nested_key)
        if isinstance(nested, Mapping):
            found = niche_from_mapping(nested)
            if found:
                return found
    return None


def keyword_ranked_prompt_paths(text: str) -> list[str]:
    """Prompt paths from every profile whose keywords appear in ``text``, in registry order."""

    ranked: list[str] = []
    for profile in _REGISTRY.values():
        if profile.matches_text(text):
            ranked.extend(profile.prompt_paths)
    return ranked


def single_instance_objects_for(profile: NicheProfile) -> tuple[str, ...]:
    if profile.key != GENERAL_NICHE_KEY:
        return profile.single_instance_objects
    merged: list[str] = []
    for registered in _REGISTRY.values():
        for name in registered.single_instance_objects:
            if name not in merged:
                merged.append(name)
    return tuple(merged)


def is_single_instance_token(token: str, object_name: str) -> bool:
    """``pan``, ``pan2`` or ``pan1test`` match ``pan``; plurals and ``panorama`` do not."""

    trimmed = token.strip().lower()
    base = object_name.strip().lower()
    if not base or not trimmed.startswith(base):
        return False
    if trimmed == base:
        return True
    remainder = trimmed.removeprefix(base)
    if remainder == "s":
        return False
    return bool(_SINGLE_INSTANCE_SUFFIX.fullmatch(remainder))


def matching_single_instance_object(
    label_tokens: Iterable[str], objects: Iterable[str]
) -> str | None:
    tokens = list(label_tokens)
    for name in objects:
        if any(is_single_instance_token(token, name) for token in tokens):
            return name
    return None


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


__all__ = [
    "GENERAL_NICHE_KEY",
    "GENERAL_PROFILE",
    "NicheProfile",
    "is_single_instance_token",
    "keyword_ranked_prompt_paths",
    "matching_single_instance_object",
    "niche_from_mapping",
    "register_niche_profile",
    "registered_niche_profiles",
    "resolve_niche_profile",
    "single_instance_objects_for",
]
