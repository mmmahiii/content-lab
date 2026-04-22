"""Deterministic scene-plan compilation for generated reel scripts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from content_lab_creative.types import (
    GeneratedScriptOutput,
    OverlayCue,
    PlannedCreativeBrief,
    SceneOverlayRole,
    ScenePlanOutput,
    ScenePlanScene,
    ScenePurpose,
    ScriptBeat,
    ScriptOverlayEmphasis,
)

BriefSceneContext = PlannedCreativeBrief | Mapping[str, Any]

_SCENE_PURPOSES = (
    ScenePurpose.HOOK,
    ScenePurpose.SETUP,
    ScenePurpose.VALUE,
    ScenePurpose.PAYOFF,
    ScenePurpose.CLOSE,
)


def compile_scene_plan(
    *,
    brief: BriefSceneContext,
    script: GeneratedScriptOutput,
) -> ScenePlanOutput:
    """Compile a deterministic scene plan from a brief and generated script."""

    brief_title = _brief_value(brief, "title", fallback=script.brief_title)
    content_pillar = _brief_value(brief, "content_pillar", fallback=brief_title)
    audience = _brief_value(brief, "audience", fallback="the viewer")
    cta = _brief_value(brief, "primary_call_to_action", fallback=None)
    boundaries = _segment_boundaries(script.duration_seconds, len(_SCENE_PURPOSES))
    scenes = [
        _build_scene(
            purpose=purpose,
            index=index,
            start_seconds=boundaries[index],
            end_seconds=boundaries[index + 1],
            brief_title=brief_title,
            content_pillar=content_pillar,
            audience=audience,
            cta=cta,
            script=script,
        )
        for index, purpose in enumerate(_SCENE_PURPOSES)
    ]
    return ScenePlanOutput(
        brief_title=brief_title,
        duration_seconds=script.duration_seconds,
        scenes=scenes,
        metadata={
            "source": "script_and_brief",
            "scene_count": len(scenes),
            "script_provider_name": script.provider_name,
            "script_generator_path": script.generator_path,
        },
    )


def compile_scene_prompt(scene_plan: ScenePlanOutput) -> str:
    """Build a compact provider-facing prompt from the structured scene plan."""

    fragments = [
        f"{scene.purpose.value}: {scene.visual_intent} Shot: {scene.shot_guidance}"
        + (f" Overlay: {scene.overlay_text}" if scene.overlay_text else "")
        for scene in scene_plan.scenes
    ]
    return " | ".join(fragments)


def _build_scene(
    *,
    purpose: ScenePurpose,
    index: int,
    start_seconds: int,
    end_seconds: int,
    brief_title: str,
    content_pillar: str,
    audience: str,
    cta: str | None,
    script: GeneratedScriptOutput,
) -> ScenePlanScene:
    overlay = _overlay_for_scene(script.overlay_timeline, start_seconds, end_seconds, purpose)
    return ScenePlanScene(
        scene_id=f"scene_{index + 1}_{purpose.value}",
        purpose=purpose,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        visual_intent=_visual_intent(
            purpose=purpose,
            brief_title=brief_title,
            content_pillar=content_pillar,
            audience=audience,
            cta=cta,
        ),
        shot_guidance=_shot_guidance(purpose=purpose, script=script, scene_index=index),
        overlay_role=_overlay_role(purpose=purpose, overlay=overlay),
        overlay_text=overlay.text if overlay is not None else None,
        narration_refs=_narration_refs(script.spoken_script, start_seconds, end_seconds),
    )


def _visual_intent(
    *,
    purpose: ScenePurpose,
    brief_title: str,
    content_pillar: str,
    audience: str,
    cta: str | None,
) -> str:
    if purpose is ScenePurpose.HOOK:
        return f"Create immediate visual proof for {content_pillar} so {audience} understands the payoff."
    if purpose is ScenePurpose.SETUP:
        return f"Show the everyday context or friction behind {brief_title}."
    if purpose is ScenePurpose.VALUE:
        return f"Demonstrate the useful {content_pillar} action clearly enough to copy."
    if purpose is ScenePurpose.PAYOFF:
        return f"Reveal the concrete improvement or result from the {content_pillar} action."
    if cta:
        return f"Resolve the reel with a clean final frame that supports: {cta}."
    return "Resolve the reel with one memorable final takeaway."


def _shot_guidance(
    *,
    purpose: ScenePurpose,
    script: GeneratedScriptOutput,
    scene_index: int,
) -> str:
    beat = _nearest_beat(script.spoken_script, scene_index)
    if beat is not None and beat.shot_direction:
        return beat.shot_direction
    if purpose is ScenePurpose.HOOK:
        return "Open tight on the most legible action, with motion already happening."
    if purpose is ScenePurpose.SETUP:
        return "Use a medium shot that makes the problem or context instantly readable."
    if purpose is ScenePurpose.VALUE:
        return "Cut closer to the hands, object, or movement that carries the useful detail."
    if purpose is ScenePurpose.PAYOFF:
        return "Hold long enough for the result to register without adding visual clutter."
    return "Finish on a stable final frame with room for the last overlay."


def _overlay_role(
    *,
    purpose: ScenePurpose,
    overlay: OverlayCue | None,
) -> SceneOverlayRole:
    if overlay is not None:
        if overlay.emphasis is ScriptOverlayEmphasis.HOOK:
            return SceneOverlayRole.HOOK
        if overlay.emphasis is ScriptOverlayEmphasis.CTA:
            return SceneOverlayRole.CTA
        if overlay.emphasis is ScriptOverlayEmphasis.DISCLOSURE:
            return SceneOverlayRole.DISCLOSURE
        return SceneOverlayRole.EMPHASIS
    if purpose is ScenePurpose.HOOK:
        return SceneOverlayRole.HOOK
    if purpose is ScenePurpose.CLOSE:
        return SceneOverlayRole.CTA
    return SceneOverlayRole.CONTEXT


def _overlay_for_scene(
    overlays: list[OverlayCue],
    start_seconds: int,
    end_seconds: int,
    purpose: ScenePurpose,
) -> OverlayCue | None:
    overlaps = [
        overlay
        for overlay in overlays
        if overlay.start_seconds < end_seconds and overlay.end_seconds > start_seconds
    ]
    if overlaps:
        return overlaps[0]
    if purpose is ScenePurpose.HOOK:
        return overlays[0] if overlays else None
    if purpose is ScenePurpose.CLOSE:
        return overlays[-1] if overlays else None
    return None


def _narration_refs(
    beats: list[ScriptBeat],
    start_seconds: int,
    end_seconds: int,
) -> list[int]:
    refs = [
        index
        for index, beat in enumerate(beats)
        if beat.start_seconds < end_seconds and beat.end_seconds > start_seconds
    ]
    if refs:
        return refs
    return [min(len(beats) - 1, max(0, start_seconds))] if beats else []


def _nearest_beat(beats: list[ScriptBeat], scene_index: int) -> ScriptBeat | None:
    if not beats:
        return None
    if len(beats) == 1:
        return beats[0]
    mapped_index = round(scene_index * (len(beats) - 1) / (len(_SCENE_PURPOSES) - 1))
    return beats[mapped_index]


def _brief_value(
    brief: BriefSceneContext,
    field_name: str,
    *,
    fallback: str | None,
) -> str:
    if isinstance(brief, PlannedCreativeBrief):
        value = getattr(brief, field_name)
    else:
        value = brief.get(field_name)
    if value is None:
        return "" if fallback is None else fallback
    normalized = str(value).strip()
    return normalized or ("" if fallback is None else fallback)


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


__all__ = ["compile_scene_plan", "compile_scene_prompt"]
