"""Deterministic scene-plan compilation for generated reel scripts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

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
    visual_style_lock = _visual_style_lock(content_pillar)
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
            visual_style_lock=visual_style_lock,
        )
        for index, purpose in enumerate(_SCENE_PURPOSES)
    ]
    return ScenePlanOutput(
        brief_title=brief_title,
        duration_seconds=script.duration_seconds,
        scenes=scenes,
        visual_style_lock=visual_style_lock,
        metadata={
            "source": "script_and_brief",
            "scene_count": len(scenes),
            "script_provider_name": script.provider_name,
            "script_generator_path": script.generator_path,
            "visual_style_lock": visual_style_lock,
            "enriched_scene_fields": [
                "subject",
                "setting",
                "action",
                "key_visual_object",
                "camera_framing",
                "camera_motion",
                "lighting",
                "palette",
                "continuity_anchor",
                "visual_purpose",
                "forbidden_visual_elements",
            ],
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
    visual_style_lock: dict[str, object],
) -> ScenePlanScene:
    overlay = _overlay_for_scene(script.overlay_timeline, start_seconds, end_seconds, purpose)
    motif = _visual_motif(purpose=purpose, content_pillar=content_pillar)
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
        subject=str(motif["subject"]),
        setting=str(motif["setting"]),
        action=str(motif["action"]),
        key_visual_object=str(motif["key_visual_object"]),
        camera_framing=str(motif["camera_framing"]),
        camera_motion=str(motif["camera_motion"]),
        lighting=str(visual_style_lock["lighting"]),
        palette=str(visual_style_lock["palette"]),
        continuity_anchor=str(visual_style_lock["continuity"]),
        visual_purpose=str(motif["visual_purpose"]),
        forbidden_visual_elements=list(cast(list[str], visual_style_lock["avoid"])),
        overlay_role=_overlay_role(purpose=purpose, overlay=overlay),
        overlay_text=overlay.text if overlay is not None else None,
        narration_refs=_narration_refs(script.spoken_script, start_seconds, end_seconds),
    )


def _visual_style_lock(content_pillar: str) -> dict[str, object]:
    if _is_operations(content_pillar):
        return {
            "setting": "modern desk workspace",
            "subject": "busy founder",
            "lighting": "soft natural daylight",
            "palette": "neutral business tones",
            "camera_language": "close-up and medium desk shots",
            "continuity": "same founder, same laptop, same desk across scenes",
            "avoid": [
                "legible UI text",
                "floating text",
                "watermarks",
                "captions baked into video",
            ],
        }
    return {
        "setting": "clean practical workspace",
        "subject": "focused person",
        "lighting": "soft natural daylight",
        "palette": "natural realistic tones",
        "camera_language": "vertical close-ups and medium action shots",
        "continuity": "same person, same location, same main object across scenes",
        "avoid": ["legible UI text", "floating text", "watermarks", "captions baked into video"],
    }


def _visual_motif(*, purpose: ScenePurpose, content_pillar: str) -> dict[str, str]:
    if _is_operations(content_pillar):
        base = {
            "subject": "busy founder",
            "setting": "modern desk workspace",
            "camera_motion": "slow push-in",
        }
        by_purpose = {
            ScenePurpose.HOOK: (
                "sorting a messy backlog into clear groups",
                "laptop task board with abstract task-board cards without legible text",
                "close-up over-the-shoulder",
                "show the operations reset beginning immediately",
            ),
            ScenePurpose.SETUP: (
                "pausing over repeated notification blocks and a cluttered calendar",
                "blurred dashboard shapes and inbox-style notification blocks",
                "medium desk shot",
                "make the operational friction visible without readable UI text",
            ),
            ScenePurpose.VALUE: (
                "dragging overdue tasks into three priority columns",
                "laptop task board with non-readable interface blocks",
                "close-up over-the-shoulder",
                "show the operations reset being performed",
            ),
            ScenePurpose.PAYOFF: (
                "checking a simplified checklist beside an organized workflow board",
                "clean kanban-style workflow with unlabeled cards",
                "steady close-up",
                "reveal the workflow becoming calmer and easier to scan",
            ),
            ScenePurpose.CLOSE: (
                "closing the laptop beside neatly arranged sticky notes",
                "desk with organized sticky notes and a calm laptop screen",
                "stable medium shot",
                "end on a clear calm final frame",
            ),
        }
        action, obj, framing, visual_purpose = by_purpose[purpose]
        return {
            **base,
            "action": action,
            "key_visual_object": obj,
            "camera_framing": framing,
            "visual_purpose": visual_purpose,
        }
    return {
        "subject": "focused person",
        "setting": "clean practical workspace",
        "action": "performing the main practical step",
        "key_visual_object": "hands and primary object used in the demonstration",
        "camera_framing": "vertical close-up",
        "camera_motion": "subtle handheld move",
        "visual_purpose": f"make the {content_pillar} idea concrete and easy to follow",
    }


def _is_operations(content_pillar: str) -> bool:
    return "operation" in content_pillar.strip().lower()


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
