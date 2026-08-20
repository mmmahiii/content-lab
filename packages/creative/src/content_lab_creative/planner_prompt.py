"""Composable instruction blocks for the manual single-prompt cinematic planner."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from content_lab_creative.narrative_engine import narrative_arc_prompt_text
from content_lab_creative.planning_schema import (
    AUDIO_ROLES,
    CAMERA_MOVES,
    CINEMATIC_ROLES,
    CinematicReelPlan,
)
from content_lab_creative.prompt_paths import PROMPT_PATH_DESCRIPTIONS


def physical_relationship_rules_block() -> str:
    return """Physical relationship rules:
- For every visible non-background object, set spatial_relationship and relationship_reason.
- Set support_object_id (and contact_shadow_target_object_id when needed) whenever an object rests on,
  hangs from, or aligns to another object's geometry — not merely overlaps in frame space.
- Set relative_depth_rule, required_overlap_ratio, and max_overlap_ratio when objects occlude or touch.
- When a support asset has a registered support_surface_mask_uri, overlap is enforced against that surface
  region (not just bounding boxes); place dependents on visible contact pixels.
- Prefer stable enums (on_surface, inside, attached_to, overlay_on, behind, adjacent_to, atmospheric,
  independent); coordinates alone are never sufficient to explain placement.
- Transparent cut-outs must declare how they relate to environment_base or supporting surfaces."""


def duplicate_role_rules_block() -> str:
    return """Duplicate-role rule:
If multiple selected assets can serve the same cinematic role or narrative slot (two heroes, two pans,
duplicate payoff props), choose only the strongest asset for that role and list every weaker duplicate in
provenance.rejected_assets with a concise reason.
Do not stack redundant assets that fight for the same storytelling job unless the scene is explicitly a
comparison shot (then justify both)."""


def environment_base_quality_rules_block() -> str:
    return """Environment base quality rule:
- Inspect planner asset compatibility.asset_resolution_class, width/height when present, and labels that
  imply plates, tiles, wood grain, or sharp architectural detail.
- If the environment_base asset is LOW resolution, undersized versus canvas, or flagged as rough realism
  risk, treat it only as a softened/padded backdrop: generous blur, crop-safe framing, edge vignette,
  and reduced reliance on fine texture — foreground heroes carry readable detail instead.
- Never pretend a blurry backdrop is razor-sharp full-frame realism; encode honest limitation in
  realism_reason per object and bump realism_risk_score when bases are weak."""


def perspective_compatibility_rules_block() -> str:
    return """Perspective compatibility rule:
- Align each TimelineObject.view_angle and surface_plane with that asset's planner compatibility hints
  (compatible_view_angles, compatible_surface_planes, surface_plane metadata).
- Background bases and foreground subjects must agree on plausible horizon / surface continuity — avoid
  conflicting planes (e.g., overhead tabletop hero stacked on eye-level wall backdrop without narrative excuse).
- When angles disagree, downgrade layout complexity or reject/mute conflicting assets rather than forcing a
  collage that ignores geometry."""


def background_reveal_rules_block() -> str:
    return """Background reveal placement rule:
- background_reveal is a rear/side contextual accent, never a foreground prop.
- Default safe placement: z <= 0.45 AND z lower than the hero_subject in the same scene.
- Keep overlap with hero_subject <= max_overlap_ratio; when unsure use max_overlap_ratio = 0.10.
- Preferred screen regions must be rear/side regions such as upper_left, upper_right, background_left,
  background_right, rear, or side. Do not assign foreground, lower_third, center, or full_frame as preferred
  regions for a background_reveal.
- If a background_reveal cannot be placed behind and away from the hero, reject it in
  provenance.rejected_assets instead of using it."""


def sensory_path_eligibility_rules_block(eligibility_snapshot: Mapping[str, Any]) -> str:
    allowed = eligibility_snapshot.get("allowed_prompt_paths") or []
    blocked = eligibility_snapshot.get("blocked_prompt_paths") or []
    blocked_reasons = eligibility_snapshot.get("blocked_reasons") or {}
    reasons_lines = ""
    if isinstance(blocked_reasons, Mapping):
        reasons_lines = "\n".join(
            f"  - {path}: {reason}"
            for path, reason in sorted(blocked_reasons.items())
            if isinstance(reason, str)
        )
    allowed_txt = ", ".join(str(p) for p in allowed) if allowed else "(none)"
    blocked_txt = ", ".join(str(p) for p in blocked) if blocked else "(none)"
    blocked_expl = ""
    if reasons_lines:
        blocked_expl = "Blocked explanations:\n" + reasons_lines + "\n"
    return f"""Sensory path eligibility rule:
Use ONLY prompt paths from planner input allowed_prompt_paths or provenance-compatible subsets.
Eligibility snapshot for this session:
- Allowed paths: {allowed_txt}
- Blocked paths (do NOT select): {blocked_txt}
{blocked_expl}Do not claim sensory_hook, satisfying_process, or speed_ramp_showcase motion beats unless those paths are
allowed for this asset bank. If creative intent requires sensory language but paths are blocked, rely on
allowed paths or downgrade narrative intensity — never hallucinate footage/audio/overlays not selected."""


def static_asset_motion_rules_block() -> str:
    return """Static-asset motion rule:
When heroes/overlays are still images (PNG cut-outs, still props), derive motion ONLY from deterministic
renderer transforms: camera moves, easing on scale/opacity, parallax offsets, blur timing, caption rhythm,
contact shadow drift — never imply deformation, chopping, pouring liquid, bubbling boils, steam generation,
or cooking physics unless a selected motion-capable asset explicitly supports it (see planner capability flags)."""


def render_strategy_rules_block() -> str:
    return """Render strategy rule:
Set render_strategy explicitly and honestly:
- realistic_single_scene / realistic_sequence only when environment_base resolution + perspective continuity
  credibly support a lived scene with foreground readability.
- low_res_texture_backdrop when bases work texture-first but lack crisp geometry — explain blur/padding in
  render_notes.
- product_card_layout when showcasing isolated hero/catalog clarity beats spatial realism (preferred rescue if
  physics continuity fails).
- tabletop_layout or graphic_layout when typography, diagrams, or stacked cards outperform faux realism.
Prefer downgrade plus concise render_notes over impossible spatial realism."""


def realism_risk_score_rules_block() -> str:
    return """Realism risk scoring rule:
Increase provenance.realism_risk_score when assets lack dimensions, metadata is sparse, alphas look risky,
bases are LOW/MEDIUM resolution class, angles mismatch, or too many simultaneous foreground priorities remain.
Honest scores unblock QA teams — low-confidence compositions must carry visibly higher risk than pristine packs."""


def support_and_contact_instructions_block() -> str:
    return """Support objects and contacts:
Whenever an object visually rests on another surface or borrows shadow grounding, populate support_object_id,
spatial_relationship, relative_depth_rule, and contact_shadow_target_object_id exactly when contact_shadow_required
means contact shadows must anchor to a specific peer object — vague wording is insufficient for rendering."""


def render_strategy_downgrade_escape_block() -> str:
    return """Escalation / downgrade ladder:
If physical continuity, perspective compatibility, base sharpness, regulatory collage limits, or sensory evidence
cannot simultaneously be satisfied with ONLY selected assets, you MUST repair by rejecting cluttering assets OR
downgrading render_strategy toward product_card_layout or graphic_layout with frank render_notes — never invent
geometry, textures, or footage outside selected_asset_ids."""


def compose_master_planning_instruction_block(
    *,
    eligibility_snapshot: Mapping[str, Any],
    roles: str,
    camera_moves: str,
    audio_roles: str,
    duration_seconds: float,
) -> str:
    """Rich planner constraints aligned with deterministic validators."""

    prompt_paths_json = json.dumps(PROMPT_PATH_DESCRIPTIONS, indent=2, sort_keys=True)
    narrative_guidance = narrative_arc_prompt_text(duration_seconds)

    sections = [
        physical_relationship_rules_block(),
        duplicate_role_rules_block(),
        environment_base_quality_rules_block(),
        perspective_compatibility_rules_block(),
        background_reveal_rules_block(),
        sensory_path_eligibility_rules_block(eligibility_snapshot),
        static_asset_motion_rules_block(),
        render_strategy_rules_block(),
        support_and_contact_instructions_block(),
        realism_risk_score_rules_block(),
        render_strategy_downgrade_escape_block(),
        f"""Internal stages to perform before writing JSON:
1. Asset Understanding: assign cinematic roles using compatibility hints.
2. Creative Path Selection: obey allowed vs blocked prompt paths in planner input.
3. Narrative Engine: hook → development → payoff → retention loop matching chosen paths.
4. Scene Regulation: single focal dominance per scene; duplicate-role pruning via rejected_assets.
5. Coordinate Timeline Engine: normalized 9:16 timing, depth, motion, occlusion truthfulness.
6. Camera Engine: supported moves only ({camera_moves}).
7. Lighting & Shadow Engine: deterministic lights + grounded shadows referencing declared lights.
8. Caption Engine: editable renderer text inside safe areas only.
9. Audio Engine: selected IDs or placeholder_audio_* IDs — never invent registry IDs.
10. Risk calibration: realism_risk_score reflects weak metadata / mismatched perspectives.""",
        """Anti-collage composition rules:
- In each scene, no more than 3 visible foreground objects may have z greater than 0.65.
- Every scene opens with environment_base unless intentionally transition-only.
- Transparent cut-outs relate physically to bases/support surfaces — never float without justification.
- hero_subject stays visually dominant unless narrative explicitly compares subjects.""",
        f"""Enum discipline:
- TimelineObject.role / ScenePlan.dominant_focal_role ONLY from: {roles}
- At most one hero_subject and one narrative_payoff object per scene unless comparison justified.
- CameraMove.move_type ONLY from: {camera_moves}
- AudioLayer.role ONLY from: {audio_roles}
- Do not invent asset-specific roles such as hero_tomato, ingredient_step, music_bed, push_in, or payoff_lift.
- Replace tempting bespoke labels (hero_ingredient, tomato foreground texture, vegetable layer assembly,
  ambient rhythmic kitchen bed, tilt_down, lateral_slide, locked, …) with canonical enums before returning JSON.
- If no selected audio asset exists for an audio layer, set asset_id to null and make audio_id begin with
  placeholder_audio_; do not invent audio asset IDs.
- Every enabled shadow_spec.source_light_id and lighting_shadow_plan.per_object_shadow_specs[].source_light_id must
  reference one of lighting_shadow_plan.lights[].light_id — default to the first declared light_id when unsure.
- Asset-specific labels belong in object_id, asset_label, purpose, and realism_reason — never inside role enums,
  dominant_focal_role, camera_move.move_type, or audio role strings.
- width_normalised / height_normalised ∈ (0, 1]; numeric caption/light/shadow coordinates stay inside schema ranges.""",
        f"""Default narrative timing guidance for {duration_seconds:.2f}s:
{narrative_guidance}""",
        f"""Allowed stackable prompt paths and meanings:
{prompt_paths_json}""",
    ]
    return "\n\n".join(sections)


def build_master_planning_prompt_document(
    *,
    recommended_model: str,
    planning_prompt_version: str,
    eligibility_snapshot: Mapping[str, Any],
    planner_payload_json: str,
    roles: str,
    camera_moves: str,
    audio_roles: str,
    duration_seconds: float,
) -> str:
    """Full ChatGPT-ready planner prompt body."""

    schema_json = json.dumps(CinematicReelPlan.model_json_schema(), indent=2, sort_keys=True)
    instructions = compose_master_planning_instruction_block(
        eligibility_snapshot=eligibility_snapshot,
        roles=roles,
        camera_moves=camera_moves,
        audio_roles=audio_roles,
        duration_seconds=duration_seconds,
    )

    return f"""You are the Content Lab Procedural Cinematic Reel Planner.

Use model: {recommended_model}.
Return only valid JSON. Do not wrap it in Markdown. Do not explain the JSON.

Your only job is to produce one renderer-ready CinematicReelPlan.

CRITICAL MANUAL-MODE RULE:
Because this response will be pasted directly into a validator, every top-level field and every
nested required field must be present, even if empty arrays are needed. Do not omit scenes,
objects, captions, audio_layers, selected_prompt_paths, render_notes, canvas, fps, or
provenance.selected_asset_ids. If a field is optional in the schema but necessary for rendering,
still include it.

Explicit output rule:
Even if the JSON schema marks a field as optional or defaulted, include it explicitly whenever it
is part of the render plan. Do not rely on schema defaults.

Do not generate images. Do not generate video. Do not call external image/video APIs.
Do not request screenshots. Do not copy an existing reel. Do not hallucinate assets.
Do not mention uploaded text files, screenshots, or external generation tools in render_notes,
scene purpose, or realism_reason; describe only how stored selected assets should be arranged.
Use only selected asset_ids from the input. You may reject irrelevant selected assets, but every
unused selected asset must appear in provenance.rejected_assets with a reason.
Use the minimum number of selected assets required for one coherent reel. Do not use every asset
just because it is selected. A good plan may use only 4-7 assets and reject the rest. Rejecting
irrelevant assets is preferred over visual clutter.

Renderer-default rule:
Even if the JSON schema marks a field as optional or defaulted, include it explicitly whenever it is part of the render plan. Do not rely on schema defaults.

Coordinate system:
- x: 0.0 left to 1.0 right
- y: 0.0 top to 1.0 bottom
- z: 0.0 background to 1.0 foreground
- scale: relative multiplier
- rotation: degrees
- opacity: 0.0 to 1.0

{instructions}

Required JSON Schema:
{schema_json}

Planner input:
{planner_payload_json}

Before returning, silently check:
1. JSON parses.
2. No Markdown.
3. All asset_id values are from selected_asset_ids.
4. All roles use allowed enums.
5. Every scene has objects, captions, and audio_layers arrays.
6. Every object has coordinates, z-depth, scale, shadow_spec, blur_spec, and realism_reason.
7. Every unused selected asset appears in provenance.rejected_assets.
8. No scene looks like a floating collage.

Return exactly one JSON object matching CinematicReelPlan.
"""


def planner_roles_camera_audio_strings() -> tuple[str, str, str]:
    return (
        ", ".join(CINEMATIC_ROLES),
        ", ".join(CAMERA_MOVES),
        ", ".join(AUDIO_ROLES),
    )


__all__ = [
    "build_master_planning_prompt_document",
    "compose_master_planning_instruction_block",
    "background_reveal_rules_block",
    "duplicate_role_rules_block",
    "environment_base_quality_rules_block",
    "perspective_compatibility_rules_block",
    "physical_relationship_rules_block",
    "planner_roles_camera_audio_strings",
    "render_strategy_downgrade_escape_block",
    "render_strategy_rules_block",
    "realism_risk_score_rules_block",
    "sensory_path_eligibility_rules_block",
    "static_asset_motion_rules_block",
    "support_and_contact_instructions_block",
]
