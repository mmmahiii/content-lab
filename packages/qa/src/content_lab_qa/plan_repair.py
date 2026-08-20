"""Deterministic repairs for cinematic plans before realism QA rejects them."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from content_lab_creative.planning_schema import CinematicReelPlan

_PHYSICAL_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bchopp(?:ing|ed|s)?\b", re.IGNORECASE), "cut detail"),
    (re.compile(r"\bpour(?:ing|s|ed)?\b", re.IGNORECASE), "camera reveal"),
    (re.compile(r"\bdrip(?:ping|s|ped)?\b", re.IGNORECASE), "surface detail"),
    (re.compile(r"\bdrizzl(?:ing|e|ed)?\b", re.IGNORECASE), "surface highlight"),
    (re.compile(r"\bbubbl(?:ing|es|ed)?\b", re.IGNORECASE), "texture detail"),
)
_SENSORY_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsizzl(?:ing|e|ed|es)?\b", re.IGNORECASE), "close-up detail"),
    (re.compile(r"\bsteam(?:ing|y)?\b", re.IGNORECASE), "soft highlight"),
)
_IMPOSSIBLE_MOTION_TERMS = ("deformation", "liquid", "splash", "steam", "sizzle", "chop")

_DOMINANT_EXCLUDED_ROLES: frozenset[str] = frozenset(
    {"environment_base", "audio_layer", "caption_support", "transition_element"}
)

_HERO_SCALE_CAP = 5.0
_HERO_Z_CAP = 0.99
_COMPETITOR_SCALE_FLOOR = 0.3
_COMPETITOR_Z_FLOOR = 0.015
_COMPETITOR_OPACITY_FLOOR = 0.45


@dataclass(frozen=True, slots=True)
class PlanRepairResult:
    plan: CinematicReelPlan
    repairs: tuple[dict[str, Any], ...]

    @property
    def repaired(self) -> bool:
        return bool(self.repairs)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "cinematic_plan_auto_repair_v1",
            "applied": self.repaired,
            "repairs": list(self.repairs),
        }


def repair_cinematic_plan_for_realism(
    plan: CinematicReelPlan,
    report: Any,
    *,
    overlap_context: object | None = None,
) -> PlanRepairResult:
    """Repair known deterministic realism failures without changing asset choices."""

    failure_codes = {
        str(finding.code)
        for finding in getattr(report, "findings", ())
        if getattr(finding, "severity", "") == "fail"
    }
    repair_codes = {
        "prompt_path_impossible_physical_motion_claim",
        "prompt_path_impossible_sensory_claim",
        "impossible_static_asset_motion",
    }
    if not failure_codes.intersection(repair_codes):
        return PlanRepairResult(plan=plan, repairs=())

    payload = plan.model_dump(mode="json")
    repairs: list[dict[str, Any]] = []

    if failure_codes.intersection(
        {
            "prompt_path_impossible_physical_motion_claim",
            "prompt_path_impossible_sensory_claim",
        }
    ):
        _repair_impossible_language(payload, repairs)
    if "impossible_static_asset_motion" in failure_codes:
        _repair_impossible_motion_curves(payload, repairs)
    if not repairs:
        return PlanRepairResult(plan=plan, repairs=())
    payload.setdefault("provenance", {})["plan_hash"] = ""
    return PlanRepairResult(
        plan=CinematicReelPlan.model_validate(payload),
        repairs=tuple(repairs),
    )


def _payload_blur_sharpness(item: dict[str, Any]) -> float:
    blur = item.get("blur_spec")
    if not isinstance(blur, dict):
        blur = {}
    radius = float(blur.get("radius") or 0.0)
    motion_blur = float(blur.get("motion_blur") or 0.0)
    sharpness = 1.0 - min(1.0, radius + motion_blur)
    return sharpness


def _payload_visual_priority(item: dict[str, Any]) -> float:
    """Match :func:`scene_coherence._visual_priority` for deterministic JSON payloads."""

    start = float(item.get("start_time") or 0.0)
    end = float(item.get("end_time") or 0.0)
    duration = max(0.0, end - start)
    scale = float(item.get("scale") or 1.0)
    w = float(item.get("width_normalised") or 0.1)
    h = float(item.get("height_normalised") or 0.1)
    area = w * h * scale * scale
    z = float(item.get("z") or 0.0)
    opacity = float(item.get("opacity") or 1.0)
    sharpness = _payload_blur_sharpness(item)
    return (
        z * 0.25 + area * 0.32 + opacity * 0.18 + sharpness * 0.12 + duration * 0.013
    )


def _repair_hero_visual_priority(payload: dict[str, Any], repairs: list[dict[str, Any]]) -> None:
    for scene_index, scene in enumerate(_iter_dicts(payload.get("scenes"))):
        objects = _iter_dicts(scene.get("objects"))
        dominant_candidates = [
            item
            for item in objects
            if isinstance(item.get("role"), str) and item["role"] not in _DOMINANT_EXCLUDED_ROLES
        ]
        heroes = [o for o in objects if o.get("role") == "hero_subject"]
        narrative = [o for o in objects if o.get("role") == "narrative_payoff"]
        if heroes:
            focus = max(
                heroes,
                key=lambda o: (_payload_visual_priority(o), str(o.get("object_id") or "")),
            )
        elif narrative:
            focus = max(
                narrative,
                key=lambda o: (_payload_visual_priority(o), str(o.get("object_id") or "")),
            )
        else:
            continue

        def _snapshot(item: dict[str, Any]) -> dict[str, float]:
            return {
                "scale": float(item.get("scale") or 1.0),
                "z": float(item.get("z") or 0.5),
                "opacity": float(item.get("opacity") or 1.0),
            }

        changed = False
        before_snap = {_str_id(o): _snapshot(o) for o in objects if o.get("object_id")}

        for _ in range(80):
            dominant = max(
                dominant_candidates,
                key=lambda o: (_payload_visual_priority(o), str(o.get("object_id") or "")),
            )
            if dominant.get("role") in {"hero_subject", "narrative_payoff"}:
                break

            steal_roles = {"supporting_subject", "foreground_texture"}
            dominant_role = str(dominant.get("role") or "")
            if dominant_role in steal_roles:
                d_scale = float(dominant.get("scale") or 1.0)
                dominant["scale"] = max(_COMPETITOR_SCALE_FLOOR, d_scale * 0.89)
                dominant["z"] = max(
                    _COMPETITOR_Z_FLOOR,
                    float(dominant.get("z") or 0.5) - 0.065,
                )
                dominant["opacity"] = max(
                    _COMPETITOR_OPACITY_FLOOR,
                    float(dominant.get("opacity") or 1.0) - 0.08,
                )
                changed = True
                continue

            scale_now = float(focus.get("scale") or 1.0)
            z_now = float(focus.get("z") or 0.5)
            op_now = float(focus.get("opacity") or 1.0)
            boosted = False
            if scale_now < _HERO_SCALE_CAP - 1e-6:
                focus["scale"] = min(scale_now * 1.07, _HERO_SCALE_CAP)
                boosted = True
            elif z_now < _HERO_Z_CAP - 1e-6:
                focus["z"] = min(z_now + 0.055, _HERO_Z_CAP)
                boosted = True
            elif op_now < 1.0 - 1e-6:
                focus["opacity"] = min(op_now + 0.085, 1.0)
                boosted = True

            if not boosted:
                d_scale = float(dominant.get("scale") or 1.0)
                dominant["scale"] = max(_COMPETITOR_SCALE_FLOOR, d_scale * 0.898)
                dominant["z"] = max(
                    _COMPETITOR_Z_FLOOR,
                    float(dominant.get("z") or 0.5) - 0.058,
                )
                dominant["opacity"] = max(
                    _COMPETITOR_OPACITY_FLOOR,
                    float(dominant.get("opacity") or 1.0) - 0.075,
                )
            changed = True
        else:
            dominant = max(
                dominant_candidates,
                key=lambda o: (_payload_visual_priority(o), str(o.get("object_id") or "")),
            )
            if dominant.get("role") not in {"hero_subject", "narrative_payoff"}:
                dominant["scale"] = max(_COMPETITOR_SCALE_FLOOR, float(dominant.get("scale") or 1.0) * 0.82)
                changed = True

        if not changed:
            continue

        after_snap = {_str_id(o): _snapshot(o) for o in objects if o.get("object_id")}
        repairs.append(
            {
                "code": "hero_not_highest_visual_priority",
                "path": f"scenes.{scene_index}",
                "scene_id": scene.get("scene_id"),
                "from": before_snap,
                "to": after_snap,
                "reason": "boost_focal_subject_or_relaxed_competing_object_to_match_scene_coherence",
            },
        )


def _str_id(item: dict[str, Any]) -> str:
    return str(item.get("object_id"))


def _repair_caption_positions(payload: dict[str, Any], repairs: list[dict[str, Any]]) -> None:
    for scene_index, scene in enumerate(_iter_dicts(payload.get("scenes"))):
        heroes_only = [
            item
            for item in _iter_dicts(scene.get("objects"))
            if item.get("role") == "hero_subject"
        ]
        hero_for_caption = (
            max(
                heroes_only,
                key=lambda o: (_payload_visual_priority(o), str(o.get("object_id"))),
            )
            if heroes_only
            else None
        )
        if hero_for_caption is None:
            continue
        for caption_index, caption in enumerate(_iter_dicts(scene.get("captions"))):
            if _caption_hero_overlap_ratio(caption, hero_for_caption) <= 0.02:
                continue
            before = {"x": caption.get("x"), "y": caption.get("y"), "max_width": caption.get("max_width")}
            _move_caption_away_from_hero(caption, hero_for_caption)
            after = {"x": caption.get("x"), "y": caption.get("y"), "max_width": caption.get("max_width")}
            repairs.append(
                {
                    "code": "caption_overlaps_hero",
                    "path": f"scenes.{scene_index}.captions.{caption_index}",
                    "from": before,
                    "to": after,
                    "reason": "moved_caption_to_clear_hero_bounds",
                }
            )


def _repair_impossible_language(payload: dict[str, Any], repairs: list[dict[str, Any]]) -> None:
    _sanitize_owner_string(payload, "page_context_summary", "page_context_summary", repairs)
    _sanitize_owner_string(payload, "content_goal", "content_goal", repairs)
    string_paths = [
        ("narrative_arc.hook", payload.get("narrative_arc"), "hook"),
        ("narrative_arc.development", payload.get("narrative_arc"), "development"),
        ("narrative_arc.reveal_payoff", payload.get("narrative_arc"), "reveal_payoff"),
        (
            "narrative_arc.closing_retention_loop",
            payload.get("narrative_arc"),
            "closing_retention_loop",
        ),
        ("global_camera_style", payload, "global_camera_style"),
        ("global_lighting_style", payload, "global_lighting_style"),
        ("caption_strategy", payload, "caption_strategy"),
        ("audio_strategy", payload, "audio_strategy"),
    ]
    for path, owner, key in string_paths:
        _sanitize_owner_string(owner, key, path, repairs)

    for note_index, note in enumerate(list(payload.get("render_notes") or [])):
        cleaned = _sanitize_claim_text(note)
        if cleaned != note:
            payload["render_notes"][note_index] = cleaned
            _record_text_repair(repairs, f"render_notes.{note_index}", note, cleaned)

    for scene_index, scene in enumerate(_iter_dicts(payload.get("scenes"))):
        _sanitize_owner_string(scene, "purpose", f"scenes.{scene_index}.purpose", repairs)
        _sanitize_owner_string(
            scene,
            "emotional_intent",
            f"scenes.{scene_index}.emotional_intent",
            repairs,
        )
        _sanitize_owner_string(scene, "transition_in", f"scenes.{scene_index}.transition_in", repairs)
        _sanitize_owner_string(scene, "transition_out", f"scenes.{scene_index}.transition_out", repairs)
        for caption_index, caption in enumerate(_iter_dicts(scene.get("captions"))):
            _sanitize_owner_string(
                caption,
                "text",
                f"scenes.{scene_index}.captions.{caption_index}.text",
                repairs,
            )
        for object_index, item in enumerate(_iter_dicts(scene.get("objects"))):
            _sanitize_owner_string(
                item,
                "realism_reason",
                f"scenes.{scene_index}.objects.{object_index}.realism_reason",
                repairs,
            )
            _sanitize_owner_string(
                item,
                "relationship_reason",
                f"scenes.{scene_index}.objects.{object_index}.relationship_reason",
                repairs,
            )

    audio_plan = payload.get("audio_plan")
    if isinstance(audio_plan, dict):
        for moment_index, moment in enumerate(list(audio_plan.get("sensory_moments") or [])):
            cleaned = _sanitize_claim_text(moment)
            if cleaned != moment:
                audio_plan["sensory_moments"][moment_index] = cleaned
                _record_text_repair(
                    repairs,
                    f"audio_plan.sensory_moments.{moment_index}",
                    moment,
                    cleaned,
                )


def _repair_impossible_motion_curves(
    payload: dict[str, Any],
    repairs: list[dict[str, Any]],
) -> None:
    for scene_index, scene in enumerate(_iter_dicts(payload.get("scenes"))):
        for object_index, item in enumerate(_iter_dicts(scene.get("objects"))):
            if item.get("role") in {"atmospheric_layer", "motion_layer"}:
                continue
            motion_curve = item.get("motion_curve")
            if not isinstance(motion_curve, dict):
                continue
            before = str(motion_curve.get("type") or "")
            if not any(term in before.lower() for term in _IMPOSSIBLE_MOTION_TERMS):
                continue
            motion_curve["type"] = "linear"
            repairs.append(
                {
                    "code": "impossible_static_asset_motion",
                    "path": f"scenes.{scene_index}.objects.{object_index}.motion_curve.type",
                    "from": before,
                    "to": "linear",
                    "reason": "static_assets_use_transform_only_motion",
                }
            )


def _sanitize_owner_string(
    owner: object,
    key: str,
    path: str,
    repairs: list[dict[str, Any]],
) -> None:
    if not isinstance(owner, dict):
        return
    before = owner.get(key)
    if not isinstance(before, str):
        return
    cleaned = _sanitize_claim_text(before)
    if cleaned != before:
        owner[key] = cleaned
        _record_text_repair(repairs, path, before, cleaned)


def _sanitize_claim_text(value: str) -> str:
    cleaned = value
    for pattern, replacement in (*_PHYSICAL_REPLACEMENTS, *_SENSORY_REPLACEMENTS):
        cleaned = pattern.sub(replacement, cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _record_text_repair(
    repairs: list[dict[str, Any]],
    path: str,
    before: str,
    after: str,
) -> None:
    repairs.append(
        {
            "code": "impossible_prompt_path_claim",
            "path": path,
            "from": before,
            "to": after,
            "reason": "rewrote_unsupported_motion_or_sensory_claim",
        }
    )


def _move_caption_away_from_hero(caption: dict[str, Any], hero: dict[str, Any]) -> None:
    safe_area = caption.get("safe_area") if isinstance(caption.get("safe_area"), dict) else {}
    top = float(safe_area.get("top", 0.08))
    right = float(safe_area.get("right", 0.06))
    bottom = float(safe_area.get("bottom", 0.08))
    left = float(safe_area.get("left", 0.06))

    hero_y = float(hero.get("y") or 0.5)
    hero_x = float(hero.get("x") or 0.5)

    for step in range(14):
        if _caption_hero_overlap_ratio(caption, hero) <= 0.02:
            return

        mw = float(caption.get("max_width") or 0.72)
        max_width = min(mw, 1.0 - left - right, 0.76)
        caption["max_width"] = max(0.12, max_width)
        caption_height = _caption_height(caption)

        caption["x"] = _clamp(float(caption.get("x") or 0.5), left + caption["max_width"] / 2, 1.0 - right - caption["max_width"] / 2)
        top_y = top + caption_height / 2 + 0.02
        bottom_y = 1.0 - bottom - caption_height / 2 - 0.02
        if step == 0:
            caption["y"] = top_y if hero_y >= 0.5 else bottom_y
            if _caption_hero_overlap_ratio(caption, hero) > 0.02:
                caption["y"] = bottom_y if caption["y"] == top_y else top_y
            continue

        caption["max_width"] = max(0.14, float(caption.get("max_width") or 0.72) * 0.9)
        edge_left = left + caption["max_width"] / 2 + 0.02
        edge_right = 1.0 - right - caption["max_width"] / 2 - 0.02
        caption["x"] = edge_left if hero_x >= 0.5 else edge_right
        caption["x"] = _clamp(caption["x"], left + caption["max_width"] / 2, 1.0 - right - caption["max_width"] / 2)

        caption["y"] = top_y if step % 2 == 1 else bottom_y
        caption["y"] = _clamp(caption["y"], top + caption_height / 2, 1.0 - bottom - caption_height / 2)

        fs = float(caption.get("font_size") or 48)
        if step >= 6 and fs > 32:
            caption["font_size"] = int(fs - 4)


def _caption_hero_overlap_ratio(caption: dict[str, Any], hero: dict[str, Any]) -> float:
    caption_height = _caption_height(caption)
    max_width = float(caption.get("max_width") or 0.72)
    x = float(caption.get("x") or 0.5)
    y = float(caption.get("y") or 0.5)
    caption_bounds = (
        max(0.0, x - max_width / 2),
        max(0.0, y - caption_height / 2),
        min(1.0, x + max_width / 2),
        min(1.0, y + caption_height / 2),
    )
    hero_bounds = _object_bounds(hero)
    overlap_width = max(
        0.0,
        min(caption_bounds[2], hero_bounds[2]) - max(caption_bounds[0], hero_bounds[0]),
    )
    overlap_height = max(
        0.0,
        min(caption_bounds[3], hero_bounds[3]) - max(caption_bounds[1], hero_bounds[1]),
    )
    caption_area = max(
        0.0001,
        (caption_bounds[2] - caption_bounds[0]) * (caption_bounds[3] - caption_bounds[1]),
    )
    return overlap_width * overlap_height / caption_area


def _object_bounds(item: dict[str, Any]) -> tuple[float, float, float, float]:
    width = float(item.get("width_normalised") or 0.1) * float(item.get("scale") or 1.0)
    height = float(item.get("height_normalised") or 0.1) * float(item.get("scale") or 1.0)
    x = float(item.get("x") or 0.5)
    y = float(item.get("y") or 0.5)
    return (
        max(0.0, x - width / 2),
        max(0.0, y - height / 2),
        min(1.0, x + width / 2),
        min(1.0, y + height / 2),
    )


def _caption_height(caption: dict[str, Any]) -> float:
    return min(0.18, max(0.04, float(caption.get("font_size") or 48) / 1080))


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))


def _iter_dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


__all__ = ["PlanRepairResult", "repair_cinematic_plan_for_realism"]
