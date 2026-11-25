"""LLM-backed creative generation: hooks, Quick Reel branches, idea plans and scripts.

Every generator takes an optional ``LLMClient`` and falls back to deterministic output
when it is ``None`` or the call fails, so the pipeline keeps working offline.
"""

from content_lab_creative.generation.branches import (
    BranchGenerationRequest,
    BranchGenerationResult,
    BranchSelection,
    BranchSet,
    ChoiceMoment,
    ComposedReel,
    ComposedScene,
    ContinuationBeat,
    EndingOption,
    EndingStyle,
    EnergyOption,
    Pace,
    StructureOption,
    compose_reel,
    fallback_branches,
    generate_branches,
)
from content_lab_creative.generation.context import (
    BEAT_OVERLAY_MAX_CHARS,
    BEAT_OVERLAY_MAX_WORDS,
    HOOK_OVERLAY_MAX_CHARS,
    HOOK_OVERLAY_MAX_WORDS,
    CreativePageContext,
    viewer_copy_problems,
)
from content_lab_creative.generation.hooks import (
    HookCandidate,
    HookGenerationRequest,
    HookGenerationResult,
    HookMechanism,
    HookSet,
    fallback_hooks,
    generate_hooks,
)
from content_lab_creative.generation.idea_plan import (
    IdeaPlanDraft,
    IdeaPlanResult,
    generate_idea_plan,
    template_idea_plan,
)

__all__ = [
    "BEAT_OVERLAY_MAX_CHARS",
    "BEAT_OVERLAY_MAX_WORDS",
    "HOOK_OVERLAY_MAX_CHARS",
    "HOOK_OVERLAY_MAX_WORDS",
    "BranchGenerationRequest",
    "BranchGenerationResult",
    "BranchSelection",
    "BranchSet",
    "ChoiceMoment",
    "ComposedReel",
    "ComposedScene",
    "ContinuationBeat",
    "CreativePageContext",
    "EndingOption",
    "EndingStyle",
    "EnergyOption",
    "HookCandidate",
    "HookGenerationRequest",
    "HookGenerationResult",
    "HookMechanism",
    "HookSet",
    "IdeaPlanDraft",
    "IdeaPlanResult",
    "Pace",
    "StructureOption",
    "compose_reel",
    "fallback_branches",
    "fallback_hooks",
    "generate_branches",
    "generate_hooks",
    "generate_idea_plan",
    "template_idea_plan",
    "viewer_copy_problems",
]
