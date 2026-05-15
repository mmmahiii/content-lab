"""Manual single-prompt cinematic reel planner workflow."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from content_lab_creative.narrative_engine import narrative_arc_prompt_text
from content_lab_creative.planning_schema import (
    AUDIO_ROLES,
    CAMERA_MOVES,
    CINEMATIC_ROLES,
    CinematicReelPlan,
)
from content_lab_creative.prompt_paths import (
    PROMPT_PATH_DESCRIPTIONS,
    PROMPT_PATHS,
    normalize_prompt_paths,
    select_prompt_paths_for_context,
)
from content_lab_creative.scene_regulator import regulate_cinematic_plan

PLANNING_PROMPT_VERSION = "single_prompt_cinematic_reel_planner_v1"
RECOMMENDED_CHATGPT_MODEL = "gpt-5-mini"

ARTIFACT_FILENAMES: tuple[str, ...] = (
    "cinematic_reel_plan.json",
    "scene_graph.json",
    "reel_timeline.json",
    "asset_role_assignments.json",
    "caption_plan.json",
    "camera_plan.json",
    "lighting_shadow_plan.json",
    "audio_plan.json",
    "realism_constraints.json",
    "realism_qa.json",
    "provenance.json",
)

_JSON_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)

_ROLE_ALIASES: dict[str, str] = {
    "hero_tomato": "hero_subject",
    "hero_tomato_loop": "hero_subject",
    "loop_subject": "hero_subject",
    "prep_bowl_anchor": "supporting_subject",
    "ingredient_step": "supporting_subject",
    "finishing_garnish": "supporting_subject",
    "ratatouille_background_reveal": "background_reveal",
}
_CAMERA_MOVE_ALIASES: dict[str, str] = {
    "push_in": "slow_push_in",
    "pullback": "slow_pull_out",
    "pull_back": "slow_pull_out",
    "micro_pullback": "slow_pull_out",
    "pan_right_push": "parallax_push",
    "speed_ramp_push": "speed_ramp_focus",
    "pan_left": "slight_pan_left",
    "pan_right": "slight_pan_right",
    "static": "static_lockoff",
    "handheld": "handheld_micro_motion",
    "micro_motion": "handheld_micro_motion",
}
_AUDIO_ROLE_ALIASES: dict[str, str] = {
    "music_bed": "ambient_room",
    "foley_accents": "impact",
    "payoff_lift": "subtle_riser",
    "loop_tail": "soft_whoosh",
}

_NORMALIZED_OBJECT_FIELDS = ("x", "y", "z", "opacity", "width_normalised", "height_normalised")


class SinglePromptPlannerInput(BaseModel):
    """Inputs used to build the exact manual ChatGPT planning prompt."""

    model_config = ConfigDict(extra="forbid")

    page_context: dict[str, Any] = Field(default_factory=dict)
    selected_assets: list[dict[str, Any]] = Field(default_factory=list, min_length=1)
    content_goal: str | None = Field(default=None, max_length=1000)
    brand_persona_constraints: dict[str, Any] = Field(default_factory=dict)
    platform_constraints: dict[str, Any] = Field(default_factory=dict)
    duration_target_seconds: float | None = Field(default=None, gt=0.0, le=180.0)
    pinned_prompt_paths: list[str] = Field(default_factory=list)
    banned_prompt_paths: list[str] = Field(default_factory=list)

    @field_validator("pinned_prompt_paths", "banned_prompt_paths")
    @classmethod
    def _validate_paths(cls, value: list[str]) -> list[str]:
        return normalize_prompt_paths(value)

    @model_validator(mode="after")
    def _validate_path_sets(self) -> SinglePromptPlannerInput:
        overlap = set(self.pinned_prompt_paths).intersection(self.banned_prompt_paths)
        if overlap:
            raise ValueError(f"pinned and banned prompt paths overlap: {', '.join(sorted(overlap))}")
        return self

    @property
    def input_page_context_hash(self) -> str:
        return stable_json_hash(
            {
                "page_context": self.page_context,
                "content_goal": self.content_goal,
                "brand_persona_constraints": self.brand_persona_constraints,
                "platform_constraints": self.platform_constraints,
                "duration_target_seconds": self.duration_target_seconds,
            }
        )

    @property
    def selected_asset_ids(self) -> list[str]:
        ids: list[str] = []
        for asset in self.selected_assets:
            asset_id = str(asset.get("asset_id") or asset.get("id") or "").strip()
            if asset_id and asset_id not in ids:
                ids.append(asset_id)
        return ids

    @property
    def suggested_prompt_paths(self) -> list[str]:
        return select_prompt_paths_for_context(
            page_context=self.page_context,
            selected_assets=self.selected_assets,
            content_goal=self.content_goal,
            pinned_prompt_paths=self.pinned_prompt_paths,
            banned_prompt_paths=self.banned_prompt_paths,
        )


class MasterPromptPackage(BaseModel):
    """Exact prompt package shown to the operator."""

    model_config = ConfigDict(extra="forbid")

    recommended_model: str
    planning_prompt_version: str
    input_page_context_hash: str
    selected_asset_ids: list[str]
    suggested_prompt_paths: list[str]
    master_prompt: str


class ValidatedCinematicPlan(BaseModel):
    """Validated canonical plan plus derived JSON artifacts."""

    model_config = ConfigDict(extra="forbid")

    plan: CinematicReelPlan
    plan_hash: str
    validation_report: dict[str, Any]
    artifacts: dict[str, Any]


def build_master_planning_prompt(planner_input: SinglePromptPlannerInput) -> MasterPromptPackage:
    """Build the exact master prompt for a manual ChatGPT chat."""

    prompt_paths_json = json.dumps(PROMPT_PATH_DESCRIPTIONS, indent=2, sort_keys=True)
    schema_json = json.dumps(CinematicReelPlan.model_json_schema(), indent=2, sort_keys=True)
    payload_json = json.dumps(_prompt_payload(planner_input), indent=2, sort_keys=True)
    roles = ", ".join(CINEMATIC_ROLES)
    camera_moves = ", ".join(CAMERA_MOVES)
    audio_roles = ", ".join(AUDIO_ROLES)
    duration = planner_input.duration_target_seconds or 6.5
    prompt = f"""You are the Content Lab Procedural Cinematic Reel Planner.

Use model: {RECOMMENDED_CHATGPT_MODEL}.
Return only valid JSON. Do not wrap it in Markdown. Do not explain the JSON.

Your only job is to produce one renderer-ready CinematicReelPlan.
Do not generate images. Do not generate video. Do not call external image/video APIs.
Do not request screenshots. Do not copy an existing reel. Do not hallucinate assets.
Use only selected asset_ids from the input. You may reject irrelevant selected assets, but every
unused selected asset must appear in provenance.rejected_assets with a reason.

Coordinate system:
- x: 0.0 left to 1.0 right
- y: 0.0 top to 1.0 bottom
- z: 0.0 background to 1.0 foreground
- scale: relative multiplier
- rotation: degrees
- opacity: 0.0 to 1.0

Internal stages to perform before writing JSON:
1. Asset Understanding: assign cinematic roles by what each asset can do in the scene.
2. Creative Path Selection: choose stackable prompt paths; include pinned paths and exclude banned paths.
3. Narrative Engine: build hook, development, reveal/payoff, and closing retention loop.
4. Scene Regulation: one dominant focal priority per scene; no collage behavior.
5. Coordinate Timeline Engine: normalized 9:16 object timing, depth, scale, motion, occlusion.
6. Camera Engine: use only supported camera moves.
7. Lighting and Shadow Engine: deterministic lights and contact shadows.
8. Caption Engine: editable renderer text only, safe area compliant, never baked into images.
9. Audio Engine: use known selected audio assets or explicit placeholders only.
10. Realism QA Plan: encode constraints and risk score.

Enum discipline:
- Use ONLY these exact TimelineObject.role and ScenePlan.dominant_focal_role values: {roles}
- Use ONLY these exact CameraMove.move_type values: {camera_moves}
- Use ONLY these exact AudioLayer.role values: {audio_roles}
- Do not invent asset-specific roles such as hero_tomato, ingredient_step, music_bed,
  push_in, or payoff_lift.
- Asset-specific labels belong in object_id, asset_label, purpose, and realism_reason,
  never in role, dominant_focal_role, camera_move.move_type, or audio role fields.
- width_normalised and height_normalised must be greater than 0.0 and less than or equal to 1.0.
- x, y, z, opacity, caption x/y/max_width, light coordinates, and shadow values must stay in
  their schema ranges.

Default narrative timing guidance for {duration:.2f}s:
{narrative_arc_prompt_text(duration)}

Allowed stackable prompt paths and meanings:
{prompt_paths_json}

Required JSON Schema:
{schema_json}

Planner input:
{payload_json}

Return exactly one JSON object matching CinematicReelPlan.
"""
    return MasterPromptPackage(
        recommended_model=RECOMMENDED_CHATGPT_MODEL,
        planning_prompt_version=PLANNING_PROMPT_VERSION,
        input_page_context_hash=planner_input.input_page_context_hash,
        selected_asset_ids=planner_input.selected_asset_ids,
        suggested_prompt_paths=planner_input.suggested_prompt_paths,
        master_prompt=prompt,
    )


def validate_pasted_cinematic_plan(
    raw_plan_json: str | Mapping[str, Any],
    *,
    planner_input: SinglePromptPlannerInput,
) -> ValidatedCinematicPlan:
    """Parse, validate, hash, and split a pasted ChatGPT plan."""

    raw_payload = (
        parse_pasted_json(raw_plan_json) if isinstance(raw_plan_json, str) else dict(raw_plan_json)
    )
    normalized_payload, normalization_repairs = normalize_pasted_plan_payload(raw_payload)
    plan = CinematicReelPlan.model_validate(normalized_payload)
    _validate_against_prompt_request(plan, planner_input=planner_input)
    plan_hash = compute_plan_hash(plan)
    plan = attach_plan_hash(plan, plan_hash)
    regulation = regulate_cinematic_plan(plan)
    if not regulation.passed:
        failures = ", ".join(item.code for item in regulation.findings if item.severity == "fail")
        raise ValueError(f"scene regulation failed: {failures}")
    artifacts = build_plan_artifacts(plan, realism_qa=regulation.as_dict())
    return ValidatedCinematicPlan(
        plan=plan,
        plan_hash=plan_hash,
        validation_report={
            "schema_version": "cinematic_plan_validation_v1",
            "passed": True,
            "plan_hash": plan_hash,
            "normalization": {
                "applied": bool(normalization_repairs),
                "repairs": normalization_repairs,
            },
            "scene_regulation": regulation.as_dict(),
            "artifact_filenames": list(ARTIFACT_FILENAMES),
        },
        artifacts=artifacts,
    )


def parse_pasted_json(value: str) -> dict[str, Any]:
    """Parse raw JSON or a single fenced JSON block."""

    text = value.strip()
    match = _JSON_FENCE_RE.match(text)
    if match:
        text = match.group(1).strip()
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("pasted plan must be a JSON object")
    return payload


def normalize_pasted_plan_payload(payload: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Repair common ChatGPT alias drift before strict schema validation."""

    repaired = json.loads(json.dumps(payload))
    repairs: list[dict[str, Any]] = []

    def record(path: str, before: Any, after: Any, reason: str) -> None:
        if before != after:
            repairs.append({"path": path, "from": before, "to": after, "reason": reason})

    for scene_index, scene in enumerate(_iter_dicts(repaired.get("scenes"))):
        scene_path = f"scenes.{scene_index}"
        before_role = scene.get("dominant_focal_role")
        after_role = _normalize_cinematic_role(before_role)
        if after_role is not None:
            scene["dominant_focal_role"] = after_role
            record(f"{scene_path}.dominant_focal_role", before_role, after_role, "canonical_role_alias")

        camera_move = scene.get("camera_move")
        if isinstance(camera_move, dict):
            before_move = camera_move.get("move_type")
            after_move = _normalize_camera_move(before_move)
            if after_move is not None:
                camera_move["move_type"] = after_move
                record(f"{scene_path}.camera_move.move_type", before_move, after_move, "canonical_camera_alias")

        for object_index, timeline_object in enumerate(_iter_dicts(scene.get("objects"))):
            object_path = f"{scene_path}.objects.{object_index}"
            before_object_role = timeline_object.get("role")
            after_object_role = _normalize_cinematic_role(before_object_role)
            if after_object_role is not None:
                timeline_object["role"] = after_object_role
                record(f"{object_path}.role", before_object_role, after_object_role, "canonical_role_alias")
            for field_name in _NORMALIZED_OBJECT_FIELDS:
                _clamp_numeric_field(
                    timeline_object,
                    field_name,
                    lower=0.0 if field_name not in {"width_normalised", "height_normalised"} else 0.01,
                    upper=1.0,
                    path=f"{object_path}.{field_name}",
                    repairs=repairs,
                )
            _clamp_numeric_field(
                timeline_object,
                "scale",
                lower=0.01,
                upper=5.0,
                path=f"{object_path}.scale",
                repairs=repairs,
            )
            _clamp_numeric_field(
                timeline_object,
                "rotation",
                lower=-360.0,
                upper=360.0,
                path=f"{object_path}.rotation",
                repairs=repairs,
            )

        object_roles = {
            item.get("role") for item in _iter_dicts(scene.get("objects")) if item.get("role") in CINEMATIC_ROLES
        }
        if scene.get("dominant_focal_role") not in object_roles and object_roles:
            before = scene.get("dominant_focal_role")
            after = _preferred_dominant_role(scene)
            scene["dominant_focal_role"] = after
            record(f"{scene_path}.dominant_focal_role", before, after, "dominant_role_must_match_scene_object")

        for audio_index, audio_layer in enumerate(_iter_dicts(scene.get("audio_layers"))):
            _normalize_audio_layer(
                audio_layer,
                path=f"{scene_path}.audio_layers.{audio_index}.role",
                repairs=repairs,
            )

    audio_plan = repaired.get("audio_plan")
    if isinstance(audio_plan, dict):
        for audio_index, audio_layer in enumerate(_iter_dicts(audio_plan.get("layers"))):
            _normalize_audio_layer(
                audio_layer,
                path=f"audio_plan.layers.{audio_index}.role",
                repairs=repairs,
            )

    return repaired, repairs


def compute_plan_hash(plan: CinematicReelPlan) -> str:
    """Return a deterministic hash excluding the stored plan_hash field."""

    payload = plan.model_dump(mode="json")
    provenance = dict(payload["provenance"])
    provenance["plan_hash"] = ""
    payload["provenance"] = provenance
    return stable_json_hash(payload)


def attach_plan_hash(plan: CinematicReelPlan, plan_hash: str) -> CinematicReelPlan:
    payload = plan.model_dump(mode="json")
    payload["provenance"]["plan_hash"] = plan_hash
    return CinematicReelPlan.model_validate(payload)


def build_plan_artifacts(
    plan: CinematicReelPlan,
    *,
    realism_qa: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Split the canonical plan into named renderer/QA artifacts."""

    plan_json = plan.model_dump(mode="json")
    objects = [obj.model_dump(mode="json") for scene in plan.scenes for obj in scene.objects]
    captions = [
        caption.model_dump(mode="json") for scene in plan.scenes for caption in scene.captions
    ]
    scene_audio_layers = [
        layer.model_dump(mode="json") for scene in plan.scenes for layer in scene.audio_layers
    ]
    audio_assignments = [
        {
            "asset_id": layer.asset_id,
            "asset_label": layer.asset_id,
            "object_id": None,
            "audio_id": layer.audio_id,
            "role": "audio_layer",
            "audio_role": layer.role,
            "scene_id": None,
            "realism_reason": f"Selected audio asset supports the {layer.role} audio layer.",
        }
        for layer in [*plan.audio_plan.layers, *[audio for scene in plan.scenes for audio in scene.audio_layers]]
        if layer.asset_id is not None
    ]
    camera_moves = [scene.camera_move.model_dump(mode="json") for scene in plan.scenes]
    return {
        "cinematic_reel_plan.json": plan_json,
        "scene_graph.json": {
            "plan_id": plan.plan_id,
            "scenes": [
                {
                    "scene_id": scene.scene_id,
                    "start_time": scene.start_time,
                    "end_time": scene.end_time,
                    "purpose": scene.purpose,
                    "dominant_focal_role": scene.dominant_focal_role,
                    "object_ids": [obj.object_id for obj in scene.objects],
                    "occlusion_groups": sorted({obj.occlusion_group for obj in scene.objects}),
                }
                for scene in plan.scenes
            ],
        },
        "reel_timeline.json": {
            "plan_id": plan.plan_id,
            "total_duration_seconds": plan.total_duration_seconds,
            "fps": plan.fps,
            "canvas": plan.canvas.model_dump(mode="json"),
            "objects": objects,
            "captions": captions,
            "camera_moves": camera_moves,
            "audio_layers": [*plan.audio_plan.model_dump(mode="json")["layers"], *scene_audio_layers],
        },
        "asset_role_assignments.json": {
            "used_assets": [
                {
                    "asset_id": obj.asset_id,
                    "asset_label": obj.asset_label,
                    "object_id": obj.object_id,
                    "role": obj.role,
                    "scene_id": obj.scene_id,
                    "realism_reason": obj.realism_reason,
                }
                for scene in plan.scenes
                for obj in scene.objects
            ]
            + audio_assignments,
            "rejected_assets": [
                rejected.model_dump(mode="json") for rejected in plan.provenance.rejected_assets
            ],
        },
        "caption_plan.json": {"captions": captions, "caption_strategy": plan.caption_strategy},
        "camera_plan.json": {
            "global_camera_style": plan.global_camera_style,
            "camera_moves": camera_moves,
        },
        "lighting_shadow_plan.json": plan.lighting_shadow_plan.model_dump(mode="json"),
        "audio_plan.json": plan.audio_plan.model_dump(mode="json"),
        "realism_constraints.json": plan.realism_constraints.model_dump(mode="json"),
        "realism_qa.json": dict(realism_qa or {}),
        "provenance.json": plan.provenance.model_dump(mode="json"),
    }


def stable_json_hash(value: Mapping[str, Any]) -> str:
    material = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _iter_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _normalize_cinematic_role(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    lowered = value.strip().lower()
    if lowered in CINEMATIC_ROLES:
        return lowered
    if lowered in _ROLE_ALIASES:
        return _ROLE_ALIASES[lowered]
    if "transition" in lowered:
        return "transition_element"
    if "caption" in lowered:
        return "caption_support"
    if "logo" in lowered or "brand" in lowered:
        return "brand_marker"
    if "steam" in lowered or "atmosphere" in lowered or "overlay" in lowered:
        return "atmospheric_layer"
    if "background" in lowered or "reveal" in lowered:
        return "background_reveal"
    if "environment" in lowered or "base" in lowered:
        return "environment_base"
    if "texture" in lowered or "foreground" in lowered:
        return "foreground_texture"
    if "motion" in lowered:
        return "motion_layer"
    if "audio" in lowered or "sound" in lowered:
        return "audio_layer"
    if "payoff" in lowered or "final" in lowered:
        return "narrative_payoff"
    if "hero" in lowered or "main" in lowered or lowered.endswith("_subject"):
        return "hero_subject"
    if any(token in lowered for token in ("ingredient", "garnish", "bowl", "prop", "support")):
        return "supporting_subject"
    return None


def _normalize_camera_move(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    lowered = value.strip().lower()
    if lowered in CAMERA_MOVES:
        return lowered
    if lowered in _CAMERA_MOVE_ALIASES:
        return _CAMERA_MOVE_ALIASES[lowered]
    if "speed" in lowered and "ramp" in lowered:
        return "speed_ramp_focus"
    if "snap" in lowered or "reframe" in lowered:
        return "snap_reframe"
    if "parallax" in lowered:
        return "parallax_push"
    if "push" in lowered:
        return "slow_push_in"
    if "pull" in lowered or "back" in lowered:
        return "slow_pull_out"
    if "pan" in lowered and "left" in lowered:
        return "slight_pan_left"
    if "pan" in lowered and "right" in lowered:
        return "slight_pan_right"
    if "handheld" in lowered or "micro" in lowered:
        return "handheld_micro_motion"
    if "static" in lowered or "lock" in lowered:
        return "static_lockoff"
    return None


def _normalize_audio_role(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    lowered = value.strip().lower()
    if lowered in AUDIO_ROLES:
        return lowered
    if lowered in _AUDIO_ROLE_ALIASES:
        return _AUDIO_ROLE_ALIASES[lowered]
    if "sizzle" in lowered:
        return "sensory_sizzle"
    if "whoosh" in lowered or "loop" in lowered:
        return "soft_whoosh"
    if "transition" in lowered and "hit" in lowered:
        return "transition_hit"
    if "hit" in lowered or "accent" in lowered or "foley" in lowered or "impact" in lowered:
        return "impact"
    if "riser" in lowered or "lift" in lowered:
        return "subtle_riser"
    if "silence" in lowered:
        return "silence_gap"
    if "voice" in lowered:
        return "voiceover_placeholder"
    if "ambient" in lowered or "music" in lowered or "bed" in lowered or "room" in lowered:
        return "ambient_room"
    return None


def _normalize_audio_layer(
    audio_layer: dict[str, Any],
    *,
    path: str,
    repairs: list[dict[str, Any]],
) -> None:
    before = audio_layer.get("role")
    after = _normalize_audio_role(before)
    if after is not None and before != after:
        audio_layer["role"] = after
        repairs.append({"path": path, "from": before, "to": after, "reason": "canonical_audio_alias"})


def _preferred_dominant_role(scene: dict[str, Any]) -> str:
    roles = [
        item.get("role")
        for item in _iter_dicts(scene.get("objects"))
        if item.get("role") in CINEMATIC_ROLES
    ]
    for preferred in ("hero_subject", "narrative_payoff", "background_reveal", "supporting_subject"):
        if preferred in roles:
            return preferred
    return str(roles[0])


def _clamp_numeric_field(
    target: dict[str, Any],
    field_name: str,
    *,
    lower: float,
    upper: float,
    path: str,
    repairs: list[dict[str, Any]],
) -> None:
    value = target.get(field_name)
    if not isinstance(value, int | float):
        return
    clamped = min(max(float(value), lower), upper)
    if clamped != float(value):
        target[field_name] = clamped
        repairs.append({"path": path, "from": value, "to": clamped, "reason": "schema_numeric_bounds"})


def _prompt_payload(planner_input: SinglePromptPlannerInput) -> dict[str, Any]:
    return {
        "page_context": planner_input.page_context,
        "selected_assets": planner_input.selected_assets,
        "content_goal": planner_input.content_goal,
        "brand_persona_constraints": planner_input.brand_persona_constraints,
        "platform_constraints": planner_input.platform_constraints,
        "duration_target_seconds": planner_input.duration_target_seconds,
        "input_page_context_hash": planner_input.input_page_context_hash,
        "selected_asset_ids": planner_input.selected_asset_ids,
        "planning_prompt_version": PLANNING_PROMPT_VERSION,
        "allowed_prompt_paths": list(PROMPT_PATHS),
        "suggested_prompt_paths": planner_input.suggested_prompt_paths,
        "pinned_prompt_paths": planner_input.pinned_prompt_paths,
        "banned_prompt_paths": planner_input.banned_prompt_paths,
    }


def _validate_against_prompt_request(
    plan: CinematicReelPlan,
    *,
    planner_input: SinglePromptPlannerInput,
) -> None:
    expected_assets = set(planner_input.selected_asset_ids)
    if set(plan.provenance.selected_asset_ids) != expected_assets:
        raise ValueError("provenance.selected_asset_ids must exactly match selected assets")
    if plan.provenance.input_page_context_hash != planner_input.input_page_context_hash:
        raise ValueError("provenance.input_page_context_hash does not match planner input")
    if plan.provenance.planning_prompt_version != PLANNING_PROMPT_VERSION:
        raise ValueError("provenance.planning_prompt_version does not match current prompt")
    selected_paths = set(plan.selected_prompt_paths)
    missing_pinned = set(planner_input.pinned_prompt_paths) - selected_paths
    if missing_pinned:
        raise ValueError(f"selected_prompt_paths missing pinned paths: {sorted(missing_pinned)}")
    banned_used = set(planner_input.banned_prompt_paths).intersection(selected_paths)
    if banned_used:
        raise ValueError(f"selected_prompt_paths includes banned paths: {sorted(banned_used)}")


__all__ = [
    "ARTIFACT_FILENAMES",
    "PLANNING_PROMPT_VERSION",
    "RECOMMENDED_CHATGPT_MODEL",
    "MasterPromptPackage",
    "SinglePromptPlannerInput",
    "ValidatedCinematicPlan",
    "attach_plan_hash",
    "build_master_planning_prompt",
    "build_plan_artifacts",
    "compute_plan_hash",
    "normalize_pasted_plan_payload",
    "parse_pasted_json",
    "stable_json_hash",
    "validate_pasted_cinematic_plan",
]
