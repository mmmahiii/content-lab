#!/usr/bin/env python
"""Smoke utility for the manual single-prompt cinematic planner workflow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
for relative in (
    "packages/shared/py/src",
    "packages/core/src",
    "packages/creative/src",
):
    src_path = REPO_ROOT / relative
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

from content_lab_creative.single_prompt_reel_planner import (  # noqa: E402
    PLANNING_PROMPT_VERSION,
    SinglePromptPlannerInput,
    build_master_planning_prompt,
    validate_pasted_cinematic_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate prompts or validate pasted JSON for the cinematic reel planner."
    )
    parser.add_argument(
        "--mode",
        choices=("prompt", "validate", "mock"),
        default="mock",
        help="prompt writes the copy/paste prompt, validate splits a pasted plan, mock does both.",
    )
    parser.add_argument("--planner-input-json", type=Path)
    parser.add_argument("--plan-json", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/single_prompt_plan"))
    args = parser.parse_args()

    planner_input = _load_planner_input(args.planner_input_json)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    prompt_package = build_master_planning_prompt(planner_input)
    _write_json(args.output_dir / "planner_input.json", planner_input.model_dump(mode="json"))
    _write_json(args.output_dir / "prompt_package.json", prompt_package.model_dump(mode="json"))
    (args.output_dir / "master_prompt.txt").write_text(prompt_package.master_prompt, encoding="utf-8")

    if args.mode == "prompt":
        print(f"Wrote master prompt to {args.output_dir / 'master_prompt.txt'}")
        return 0

    if args.mode == "validate":
        if args.plan_json is None:
            parser.error("--plan-json is required in validate mode")
        raw_plan: str | dict[str, Any] = args.plan_json.read_text(encoding="utf-8")
    else:
        raw_plan = _mock_plan(planner_input)
        _write_json(args.output_dir / "mock_chatgpt_plan.json", raw_plan)

    validated = validate_pasted_cinematic_plan(raw_plan, planner_input=planner_input)
    for filename, payload in validated.artifacts.items():
        _write_json(args.output_dir / filename, payload)
    _write_json(args.output_dir / "validation_report.json", validated.validation_report)
    print(f"Wrote {len(validated.artifacts)} planner artifacts to {args.output_dir}")
    print(f"plan_hash={validated.plan_hash}")
    return 0


def _load_planner_input(path: Path | None) -> SinglePromptPlannerInput:
    if path is None:
        return _fixture_input()
    return SinglePromptPlannerInput.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _fixture_input() -> SinglePromptPlannerInput:
    return SinglePromptPlannerInput(
        page_context={
            "display_name": "Kitchen Lab",
            "platform": "instagram",
            "niche": "steak cooking",
        },
        selected_assets=[
            {
                "asset_id": "kitchen_bg",
                "asset_label": "Kitchen background",
                "asset_kind": "background_video",
                "media_type": "video",
                "possible_cinematic_roles": ["environment_base"],
            },
            {
                "asset_id": "steak_clip",
                "asset_label": "Steak closeup",
                "asset_kind": "subject_video",
                "media_type": "video",
                "possible_cinematic_roles": ["hero_subject"],
            },
            {
                "asset_id": "sizzle_audio",
                "asset_label": "Oil sizzle",
                "asset_kind": "sound_effect",
                "media_type": "audio",
                "possible_cinematic_roles": ["audio_layer"],
            },
        ],
        content_goal="Make steak prep feel cinematic and appetising.",
        platform_constraints={"platform": "instagram", "aspect_ratio": "9:16"},
        duration_target_seconds=6.5,
        pinned_prompt_paths=["sensory_hook"],
    )


def _motion() -> dict[str, Any]:
    return {
        "type": "linear",
        "start_value": {"x": 0.5, "scale": 1.0},
        "end_value": {"x": 0.5, "scale": 1.04},
        "easing": "ease_in_out",
        "jitter_allowed": False,
        "speed": 0.2,
        "sync_to_audio": None,
    }


def _shadow(enabled: bool, *, contact: bool = False) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "source_light_id": "key_window" if enabled else None,
        "offset_x": 0.03 if enabled else 0.0,
        "offset_y": 0.05 if enabled else 0.0,
        "blur": 0.22 if contact else 0.55,
        "opacity": 0.42 if enabled else 0.0,
        "softness": 0.55 if contact else 0.9,
        "derived_from_z_depth": True,
        "contact_shadow_required": contact,
    }


def _mock_plan(planner_input: SinglePromptPlannerInput) -> dict[str, Any]:
    objects = [
        _timeline_object(
            object_id="kitchen_bg",
            asset_id="kitchen_bg",
            asset_label="Kitchen background",
            role="environment_base",
            z=0.05,
            width=1.0,
            height=1.0,
            shadow=_shadow(False),
        ),
        _timeline_object(
            object_id="steak_hero",
            asset_id="steak_clip",
            asset_label="Steak closeup",
            role="hero_subject",
            z=0.72,
            width=0.62,
            height=0.42,
            shadow=_shadow(True, contact=True),
        ),
    ]
    return {
        "plan_id": "plan_smoke_kitchen_sizzle",
        "page_context_summary": "Kitchen Lab makes short sensory steak cooking reels.",
        "content_goal": planner_input.content_goal,
        "selected_prompt_paths": ["sensory_hook", "cinematic_closeup"],
        "narrative_arc": {
            "hook": "Open on the sizzle before text appears.",
            "development": "Push into the steak texture with coherent depth.",
            "reveal_payoff": "Hold the appetising closeup as the visual payoff.",
            "closing_retention_loop": "End on a frame that loops back to the first sizzle.",
        },
        "total_duration_seconds": 6.5,
        "fps": 24,
        "canvas": {"aspect_ratio": "9:16", "width": 1080, "height": 1920},
        "scenes": [
            {
                "scene_id": "scene_1",
                "start_time": 0.0,
                "end_time": 6.5,
                "purpose": "One coherent closeup kitchen moment.",
                "dominant_focal_role": "hero_subject",
                "emotional_intent": "Sensory appetite and calm precision.",
                "visual_density": "low",
                "camera_move": {
                    "move_type": "slow_push_in",
                    "start_time": 0.0,
                    "end_time": 6.5,
                    "crop_x": 0.5,
                    "crop_y": 0.5,
                    "zoom": 1.06,
                    "rotation": 0.0,
                    "shake_intensity": 0.02,
                    "shake_frequency": 6.0,
                    "motion_curve": _motion(),
                },
                "objects": objects,
                "captions": [
                    {
                        "caption_id": "cap_hook",
                        "text": "That first sizzle matters",
                        "role": "hook",
                        "start_time": 0.4,
                        "end_time": 1.8,
                        "x": 0.5,
                        "y": 0.14,
                        "max_width": 0.72,
                        "font_size": 54,
                        "weight": "bold",
                        "alignment": "center",
                        "animation": "fade_up",
                        "safe_area": {
                            "top": 0.08,
                            "right": 0.06,
                            "bottom": 0.08,
                            "left": 0.06,
                        },
                        "safe_area_compliant": True,
                        "renderer_text_only": True,
                    }
                ],
                "audio_layers": [],
                "transition_in": None,
                "transition_out": "loop_to_open",
            }
        ],
        "global_camera_style": "Slow closeup push with tiny handheld motion.",
        "global_lighting_style": "Warm window light with soft contact shadows.",
        "caption_strategy": "One short editable caption, clear of the hero subject.",
        "audio_strategy": "Use the selected sizzle as the immediate sensory layer.",
        "lighting_shadow_plan": {
            "lights": [
                {
                    "light_id": "key_window",
                    "type": "window",
                    "x": 0.2,
                    "y": 0.12,
                    "z": 0.9,
                    "intensity": 1.2,
                    "colour_temperature": 4300,
                    "softness": 0.75,
                }
            ],
            "per_object_shadow_specs": [
                {"object_id": item["object_id"], **item["shadow_spec"]} for item in objects
            ],
            "global_colour_temperature": 4300,
            "contrast_level": "medium",
        },
        "audio_plan": {
            "layers": [
                {
                    "audio_id": "sizzle",
                    "asset_id": "sizzle_audio",
                    "role": "sensory_sizzle",
                    "start_time": 0.0,
                    "end_time": 6.5,
                    "volume": 0.85,
                    "fade_in": 0.0,
                    "fade_out": 0.4,
                    "sync_points": [
                        {"time": 0.2, "label": "first_sizzle", "target_object_id": "steak_hero"}
                    ],
                }
            ],
            "sync_points": [{"time": 0.2, "label": "first_sizzle", "target_object_id": "steak_hero"}],
            "sensory_moments": ["0.2s first sizzle"],
        },
        "realism_constraints": {
            "dominant_subject_required": True,
            "max_foreground_objects": 3,
            "require_contact_shadows": True,
            "forbid_floating_assets": True,
            "forbid_baked_text": True,
            "forbid_fake_ui": True,
            "require_depth_consistency": True,
            "require_caption_safe_area": True,
            "require_motion_continuity": True,
        },
        "render_notes": ["Use stored registry assets only."],
        "provenance": {
            "input_page_context_hash": planner_input.input_page_context_hash,
            "selected_asset_ids": planner_input.selected_asset_ids,
            "selected_prompt_paths": ["sensory_hook", "cinematic_closeup"],
            "planning_prompt_version": PLANNING_PROMPT_VERSION,
            "plan_hash": "",
            "rejected_assets": [],
            "realism_risk_score": 0.2,
        },
    }


def _timeline_object(
    *,
    object_id: str,
    asset_id: str,
    asset_label: str,
    role: str,
    z: float,
    width: float,
    height: float,
    shadow: dict[str, Any],
) -> dict[str, Any]:
    return {
        "object_id": object_id,
        "asset_id": asset_id,
        "asset_label": asset_label,
        "role": role,
        "scene_id": "scene_1",
        "start_time": 0.0,
        "end_time": 6.5,
        "x": 0.5,
        "y": 0.52,
        "z": z,
        "scale": 1.0,
        "width_normalised": width,
        "height_normalised": height,
        "rotation": 0.0,
        "opacity": 1.0,
        "anchor_point": "center",
        "motion_curve": _motion(),
        "shadow_spec": shadow,
        "blur_spec": {"radius": 0.0, "background_blur": 0.0, "motion_blur": 0.04},
        "occlusion_group": "scene_1_table",
        "realism_reason": f"{asset_label} has a clear role in the coherent kitchen scene.",
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
