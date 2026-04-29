"""Phase-1 duration consistency checks for creative planning and editing."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# FFmpeg / container timing can differ slightly from integer plan seconds.
PHASE1_RENDERED_DURATION_TOLERANCE_SECONDS = 0.25


def validate_phase1_creative_duration_alignment(
    creative: Mapping[str, Any],
    *,
    require_primary_asset_request: bool = True,
) -> int:
    """Ensure brief, script, scene plan, posting variant, and asset request agree on duration.

    Raises:
        ValueError: if any tracked duration differs, overlays extend past the timeline,
        or scene boundaries do not cover the declared duration.
    """

    brief = _mapping_or_empty(creative.get("brief"))
    script = _mapping_or_empty(creative.get("script"))
    scene_plan = _mapping_or_empty(creative.get("scene_plan"))
    posting_plan = _mapping_or_empty(creative.get("posting_plan"))
    primary = _mapping_or_empty(creative.get("primary_asset_request"))

    if not brief:
        raise ValueError("brief is required for duration alignment")
    if not script:
        raise ValueError("script is required for duration alignment")
    if not scene_plan:
        raise ValueError("scene_plan is required for duration alignment")

    durations: dict[str, int] = {
        "brief": _require_int(brief.get("duration_seconds"), field="brief.duration_seconds"),
        "script": _require_int(script.get("duration_seconds"), field="script.duration_seconds"),
        "scene_plan": _require_int(
            scene_plan.get("duration_seconds"),
            field="scene_plan.duration_seconds",
        ),
    }

    if posting_plan:
        variant = _mapping_or_empty(posting_plan.get("variant"))
        variant_duration = variant.get("duration_seconds")
        if variant_duration is not None:
            durations["posting_plan.variant"] = _require_int(
                variant_duration,
                field="posting_plan.variant.duration_seconds",
            )

    if require_primary_asset_request:
        if not primary:
            raise ValueError("primary_asset_request is required for duration alignment")
        raw_asset_duration = primary.get("duration_seconds")
        if raw_asset_duration is None:
            raise ValueError("primary_asset_request.duration_seconds must be set")
        # Registry / JSON may surface ints or floats; timeline seconds are integral for phase-1.
        durations["primary_asset_request"] = _require_int(
            raw_asset_duration,
            field="primary_asset_request.duration_seconds",
        )

    unique = sorted(set(durations.values()))
    if len(unique) != 1:
        detail = ", ".join(f"{name}={value}" for name, value in sorted(durations.items()))
        raise ValueError(f"Phase-1 duration mismatch across creative artifacts ({detail})")

    canonical = unique[0]

    if script:
        overlays = script.get("overlay_timeline")
        if isinstance(overlays, list):
            for index, cue in enumerate(overlays):
                payload = _mapping_or_empty(cue)
                end_raw = payload.get("end_seconds")
                if end_raw is None:
                    continue
                end_s = float(end_raw)
                if end_s > float(canonical) + 1e-6:
                    raise ValueError(
                        "overlay_timeline cue extends beyond canonical duration_seconds "
                        f"(cue_index={index}, end_seconds={end_s}, duration_seconds={canonical})"
                    )

    if scene_plan:
        scenes = scene_plan.get("scenes")
        if isinstance(scenes, list) and scenes:
            last = _mapping_or_empty(scenes[-1])
            end_raw = last.get("end_seconds")
            if end_raw is None:
                raise ValueError("scene_plan final scene is missing end_seconds")
            final_end = int(round(float(end_raw)))
            if final_end != canonical:
                raise ValueError(
                    "scene_plan final scene end_seconds must equal duration_seconds "
                    f"(got end_seconds={end_raw}, duration_seconds={canonical})"
                )

    return canonical


def assert_rendered_media_matches_plan_duration(
    *,
    expected_duration_seconds: int,
    rendered_duration_seconds: float,
    tolerance_seconds: float = PHASE1_RENDERED_DURATION_TOLERANCE_SECONDS,
) -> None:
    """Fail fast when the edited output length drifts from the planned timeline."""

    if rendered_duration_seconds < 0:
        raise ValueError("rendered_duration_seconds must not be negative")
    delta = abs(float(rendered_duration_seconds) - float(expected_duration_seconds))
    if delta > tolerance_seconds:
        raise ValueError(
            "Rendered media duration does not match planned duration_seconds "
            f"(rendered={rendered_duration_seconds:.3f}, expected={expected_duration_seconds}, "
            f"tolerance={tolerance_seconds})"
        )


def _mapping_or_empty(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _require_int(value: Any, *, field: str) -> int:
    if value is None or value == "":
        raise ValueError(f"{field} must be set for duration alignment")
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a whole-second integer")
    try:
        coerced = int(round(float(value)))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if coerced < 1:
        raise ValueError(f"{field} must be a positive integer")
    return coerced


__all__ = [
    "PHASE1_RENDERED_DURATION_TOLERANCE_SECONDS",
    "assert_rendered_media_matches_plan_duration",
    "validate_phase1_creative_duration_alignment",
]
