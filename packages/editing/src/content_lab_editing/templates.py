"""Hook-first editorial templates for short-form reel editing.

These templates express explicit, deterministic editorial decisions that shape
the very front of a reel: how tight the hook is, how quickly we cut into the
body, how densely overlays can stack, and how the final beat resolves. They
live outside the ffmpeg layer so that template selection and application can
be inspected, tested, and traced without touching media.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

from content_lab_editing.edit_plan import SceneAwareEditPlan, SceneEditPlanSegment

TransitionStyle: TypeAlias = Literal["hard_cut", "whip_cut", "cross_fade"]
EndCardTreatment: TypeAlias = Literal["hold_final_frame", "cta_overlay", "tag_card"]

EDITORIAL_TEMPLATE_METADATA_KEY = "editorial_template_id"
EDITORIAL_TEMPLATE_VERSION_METADATA_KEY = "editorial_template_version"

# Purpose ordering for hook-first reels. Segments whose purpose is not listed
# here are placed after all known purposes in their original timeline order.
_PURPOSE_ORDER: tuple[str, ...] = ("hook", "setup", "value", "payoff", "close")


@dataclass(frozen=True, slots=True)
class EditorialTemplate:
    """Deterministic editorial template for hook-first short-form reels."""

    template_id: str
    template_version: str
    hook_min_seconds: float
    hook_max_seconds: float
    end_card_min_seconds: float
    end_card_max_seconds: float
    overlay_density_per_second: float
    transition_style: TransitionStyle
    end_card_treatment: EndCardTreatment
    description: str = ""

    def __post_init__(self) -> None:
        if self.hook_min_seconds <= 0.0:
            raise ValueError("hook_min_seconds must be positive")
        if self.hook_max_seconds < self.hook_min_seconds:
            raise ValueError("hook_max_seconds must be >= hook_min_seconds")
        if self.end_card_min_seconds <= 0.0:
            raise ValueError("end_card_min_seconds must be positive")
        if self.end_card_max_seconds < self.end_card_min_seconds:
            raise ValueError("end_card_max_seconds must be >= end_card_min_seconds")
        if self.overlay_density_per_second < 0.0:
            raise ValueError("overlay_density_per_second must be non-negative")

    def as_metadata(self) -> dict[str, Any]:
        """Serialize the template as JSON-friendly metadata for packaging."""

        return {
            EDITORIAL_TEMPLATE_METADATA_KEY: self.template_id,
            EDITORIAL_TEMPLATE_VERSION_METADATA_KEY: self.template_version,
            "hook_min_seconds": self.hook_min_seconds,
            "hook_max_seconds": self.hook_max_seconds,
            "end_card_min_seconds": self.end_card_min_seconds,
            "end_card_max_seconds": self.end_card_max_seconds,
            "overlay_density_per_second": self.overlay_density_per_second,
            "transition_style": self.transition_style,
            "end_card_treatment": self.end_card_treatment,
        }


HOOK_FIRST_V1 = EditorialTemplate(
    template_id="hook_first_v1",
    template_version="hook_first_v1.2026.04",
    hook_min_seconds=0.6,
    hook_max_seconds=1.4,
    end_card_min_seconds=0.5,
    end_card_max_seconds=1.2,
    overlay_density_per_second=1.5,
    transition_style="hard_cut",
    end_card_treatment="hold_final_frame",
    description=(
        "Baseline hook-first structure with a tight first second and a held " "final frame."
    ),
)

HOOK_PLUS_PAYOFF_V1 = EditorialTemplate(
    template_id="hook_plus_payoff_v1",
    template_version="hook_plus_payoff_v1.2026.04",
    hook_min_seconds=0.8,
    hook_max_seconds=1.6,
    end_card_min_seconds=0.8,
    end_card_max_seconds=1.6,
    overlay_density_per_second=1.0,
    transition_style="hard_cut",
    end_card_treatment="cta_overlay",
    description=(
        "Hook-first structure that protects an explicit payoff beat and "
        "resolves on a CTA overlay."
    ),
)

FAST_CUTS_V1 = EditorialTemplate(
    template_id="fast_cuts_v1",
    template_version="fast_cuts_v1.2026.04",
    hook_min_seconds=0.4,
    hook_max_seconds=1.0,
    end_card_min_seconds=0.3,
    end_card_max_seconds=0.9,
    overlay_density_per_second=2.0,
    transition_style="whip_cut",
    end_card_treatment="tag_card",
)

CALM_EXPLAINER_V1 = EditorialTemplate(
    template_id="calm_explainer_v1",
    template_version="calm_explainer_v1.2026.04",
    hook_min_seconds=1.0,
    hook_max_seconds=2.2,
    end_card_min_seconds=1.0,
    end_card_max_seconds=2.0,
    overlay_density_per_second=0.6,
    transition_style="cross_fade",
    end_card_treatment="cta_overlay",
)

EDITORIAL_TEMPLATES: tuple[EditorialTemplate, ...] = (
    HOOK_FIRST_V1,
    HOOK_PLUS_PAYOFF_V1,
    FAST_CUTS_V1,
    CALM_EXPLAINER_V1,
)

DEFAULT_EDITORIAL_TEMPLATE: EditorialTemplate = HOOK_FIRST_V1


def get_editorial_template(template_id: str) -> EditorialTemplate:
    """Look up a registered editorial template by id."""

    normalized = (template_id or "").strip().lower()
    for template in EDITORIAL_TEMPLATES:
        if template.template_id == normalized:
            return template
    raise KeyError(f"Unknown editorial template: {template_id!r}")


def select_editorial_template(
    *,
    scene_plan: Mapping[str, Any] | None = None,
    script: Mapping[str, Any] | None = None,
) -> EditorialTemplate:
    """Deterministically choose an editorial template from creative context.

    Selection is purely rule-based and stable under identical inputs:

    * long, low-overlay reels favour the calm explainer shape,
    * high overlay density or many scenes favour the fast-cuts template,
    * scene plans that reserve a dedicated payoff beat use the hook + payoff
      template,
    * otherwise the default hook-first template is used.
    """

    duration_seconds = _plan_or_script_duration(scene_plan=scene_plan, script=script)
    overlay_count = _overlay_cue_count(script)
    scene_count = _scene_count(scene_plan)
    has_payoff_scene = _scene_plan_has_payoff(scene_plan)

    overlay_density = overlay_count / duration_seconds if duration_seconds > 0 else 0.0

    if duration_seconds >= 45.0 and overlay_density <= 0.7:
        return CALM_EXPLAINER_V1
    if overlay_density >= 1.6 or scene_count >= 6:
        return FAST_CUTS_V1
    if has_payoff_scene:
        return HOOK_PLUS_PAYOFF_V1
    return HOOK_FIRST_V1


def apply_editorial_template(
    *,
    plan: SceneAwareEditPlan,
    template: EditorialTemplate,
) -> SceneAwareEditPlan:
    """Return a new edit plan retimed to match the editorial template.

    Segments are reordered into hook-first purpose order, the opening beat is
    clamped into the template's hook window, and the closing beat is clamped
    into the end-card window. Intermediate segments keep their existing
    durations. The resulting plan is deterministic for any given
    ``(plan, template)`` pair.
    """

    ordered = _ordered_segments(plan.segments)
    retimed = _retime_with_template(ordered, template=template)
    metadata = dict(plan.metadata)
    metadata[EDITORIAL_TEMPLATE_METADATA_KEY] = template.template_id
    metadata[EDITORIAL_TEMPLATE_VERSION_METADATA_KEY] = template.template_version
    metadata["transition_style"] = template.transition_style
    metadata["end_card_treatment"] = template.end_card_treatment

    return SceneAwareEditPlan(
        schema_version=plan.schema_version,
        compiler_name=plan.compiler_name,
        segments=retimed,
        metadata=metadata,
    )


def select_and_apply_editorial_template(
    *,
    plan: SceneAwareEditPlan,
    scene_plan: Mapping[str, Any] | None = None,
    script: Mapping[str, Any] | None = None,
    template: EditorialTemplate | None = None,
) -> tuple[SceneAwareEditPlan, EditorialTemplate]:
    """Select a template (if none was supplied) and apply it to the plan."""

    chosen = template or select_editorial_template(scene_plan=scene_plan, script=script)
    return apply_editorial_template(plan=plan, template=chosen), chosen


def apply_overlay_density_cap(
    overlays: Sequence[Any],
    *,
    clip_duration_seconds: float,
    template: EditorialTemplate,
) -> tuple[Any, ...]:
    """Drop trailing overlays beyond the template's density cap.

    The cap is ``ceil(overlay_density_per_second * clip_duration_seconds)``,
    with a floor of one overlay whenever the template permits any overlays at
    all. Order is preserved so the earliest (hook-relevant) overlays are
    always kept first.
    """

    if template.overlay_density_per_second <= 0.0:
        return ()
    if clip_duration_seconds <= 0.0:
        return ()
    cap = max(
        1,
        math.ceil(template.overlay_density_per_second * clip_duration_seconds),
    )
    if len(overlays) <= cap:
        return tuple(overlays)
    return tuple(list(overlays)[:cap])


def _ordered_segments(
    segments: Sequence[SceneEditPlanSegment],
) -> list[SceneEditPlanSegment]:
    indexed = list(enumerate(segments))

    def sort_key(item: tuple[int, SceneEditPlanSegment]) -> tuple[int, float, int]:
        index, segment = item
        purpose = segment.purpose.lower()
        try:
            priority = _PURPOSE_ORDER.index(purpose)
        except ValueError:
            priority = len(_PURPOSE_ORDER)
        return (priority, segment.timeline_start_seconds, index)

    return [segment for _, segment in sorted(indexed, key=sort_key)]


def _retime_with_template(
    segments: Sequence[SceneEditPlanSegment],
    *,
    template: EditorialTemplate,
) -> list[SceneEditPlanSegment]:
    if not segments:
        return []
    retimed: list[SceneEditPlanSegment] = []
    cursor = 0.0
    total = len(segments)
    for index, segment in enumerate(segments):
        duration = segment.duration_seconds
        purpose = segment.purpose.lower()
        is_first = index == 0
        is_last = index == total - 1
        if is_first or purpose == "hook":
            duration = _clamp(
                duration,
                minimum=template.hook_min_seconds,
                maximum=template.hook_max_seconds,
            )
        elif is_last or purpose == "close":
            duration = _clamp(
                duration,
                minimum=template.end_card_min_seconds,
                maximum=template.end_card_max_seconds,
            )
        retimed.append(
            SceneEditPlanSegment(
                segment_id=segment.segment_id,
                scene_id=segment.scene_id,
                purpose=segment.purpose,
                source_uri=segment.source_uri,
                source_start_seconds=segment.source_start_seconds,
                duration_seconds=duration,
                timeline_start_seconds=cursor,
            )
        )
        cursor += duration
    return retimed


def _clamp(value: float, *, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def _plan_or_script_duration(
    *,
    scene_plan: Mapping[str, Any] | None,
    script: Mapping[str, Any] | None,
) -> float:
    for source in (script, scene_plan):
        if source is None:
            continue
        duration = source.get("duration_seconds")
        if duration is None:
            continue
        try:
            return float(duration)
        except (TypeError, ValueError):
            continue
    return 0.0


def _overlay_cue_count(script: Mapping[str, Any] | None) -> int:
    if script is None:
        return 0
    overlays = script.get("overlay_timeline")
    if isinstance(overlays, Sequence) and not isinstance(overlays, str | bytes):
        return len(overlays)
    return 0


def _scene_count(scene_plan: Mapping[str, Any] | None) -> int:
    if scene_plan is None:
        return 0
    scenes = scene_plan.get("scenes")
    if isinstance(scenes, Sequence) and not isinstance(scenes, str | bytes):
        return len(scenes)
    return 0


def _scene_plan_has_payoff(scene_plan: Mapping[str, Any] | None) -> bool:
    if scene_plan is None:
        return False
    scenes = scene_plan.get("scenes")
    if not isinstance(scenes, Sequence) or isinstance(scenes, str | bytes):
        return False
    for scene in scenes:
        if not isinstance(scene, Mapping):
            continue
        if str(scene.get("purpose") or "").lower() == "payoff":
            return True
    return False


@dataclass
class OverlayStylePreset:
    """Default typography and text policy for a semantic on-screen role.

    Phase-1 vertical canvas (1080x1920). Emphasis/CTA stay single-line; hook uses
    :func:`content_lab_editing.layout.autofit_hook_overlay` in the overlay pipeline.
    """

    name: str
    default_font_size: int
    default_line_spacing: int
    default_margin_x: int
    default_margin_y: int
    max_word_count: int | None
    max_text_lines: int
    use_hook_autofit: bool


# Stable defaults: hook can scale/wrap; emphasis/CTA are compact, single line.
HOOK_OVERLAY_PRESET = OverlayStylePreset(
    name="hook",
    default_font_size=64,
    default_line_spacing=12,
    default_margin_x=80,
    default_margin_y=160,
    max_word_count=None,
    max_text_lines=2,
    use_hook_autofit=True,
)

EMPHASIS_OVERLAY_PRESET = OverlayStylePreset(
    name="emphasis",
    default_font_size=56,
    default_line_spacing=10,
    default_margin_x=80,
    default_margin_y=150,
    max_word_count=10,
    max_text_lines=1,
    use_hook_autofit=False,
)

CTA_OVERLAY_PRESET = OverlayStylePreset(
    name="cta",
    default_font_size=56,
    default_line_spacing=10,
    default_margin_x=80,
    default_margin_y=200,
    max_word_count=8,
    max_text_lines=1,
    use_hook_autofit=False,
)

_OVERLAY_PRESET_BY_NAME: dict[str, OverlayStylePreset] = {
    "hook": HOOK_OVERLAY_PRESET,
    "emphasis": EMPHASIS_OVERLAY_PRESET,
    "cta": CTA_OVERLAY_PRESET,
}


def get_overlay_style_preset(role: str) -> OverlayStylePreset | None:
    """Return preset for ``hook`` / ``emphasis`` / ``cta``; ``other`` and unknown = None."""

    key = (role or "other").strip().lower()
    if key in {"value", "context"}:
        key = "emphasis"
    if key == "disclosure":
        key = "cta"
    return _OVERLAY_PRESET_BY_NAME.get(key)


def _norm_token(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip().lower()
    s = str(value)
    if "." in s and s.rsplit(".", 1)[-1] in {
        "HOOK",
        "VALUE",
        "CTA",
        "DISCLOSURE",
        "EMPHASIS",
        "CONTEXT",
    }:
        return s.rsplit(".", 1)[-1].lower()
    return s.strip().lower()


def resolve_canonical_overlay_role(payload: Mapping[str, object]) -> str:
    """Map ``role`` / script ``emphasis`` / scene plan keys to a canonical role.

    Priority: explicit ``role`` / ``overlay_role`` → script ``emphasis`` (cue) →
    ``plan_overlay_role`` / ``scene_plan_overlay_role`` / ``scene_overlay_role``.

    * ``value`` and ``context`` map to **emphasis**; ``disclosure`` maps to **cta**.
    """

    raw: str
    for key in ("role", "overlay_role"):
        v = payload.get(key)
        if v is not None and str(v).strip() != "":
            raw = _norm_token(v)
            break
    else:
        v = payload.get("emphasis")
        if v is not None and str(v).strip() != "":
            m = {
                "hook": "hook",
                "value": "emphasis",
                "cta": "cta",
                "disclosure": "cta",
            }
            t = _norm_token(v)
            raw = m.get(t, t)
        else:
            first: object | None = None
            for skey in (
                "plan_overlay_role",
                "scene_plan_overlay_role",
                "scene_overlay_role",
            ):
                w = payload.get(skey)
                if w is not None and str(w).strip() != "":
                    first = w
                    break
            if first is None:
                return "other"
            t = _norm_token(first)
            m2 = {
                "hook": "hook",
                "context": "emphasis",
                "emphasis": "emphasis",
                "cta": "cta",
                "disclosure": "cta",
            }
            raw = m2.get(t, t)

    if raw in {"value", "context"}:
        raw = "emphasis"
    if raw == "disclosure":
        raw = "cta"
    if raw in {"hook", "emphasis", "cta"}:
        return raw
    return "other"


__all__ = [
    "CALM_EXPLAINER_V1",
    "CTA_OVERLAY_PRESET",
    "DEFAULT_EDITORIAL_TEMPLATE",
    "EDITORIAL_TEMPLATES",
    "EDITORIAL_TEMPLATE_METADATA_KEY",
    "EDITORIAL_TEMPLATE_VERSION_METADATA_KEY",
    "EMPHASIS_OVERLAY_PRESET",
    "EditorialTemplate",
    "EndCardTreatment",
    "FAST_CUTS_V1",
    "HOOK_FIRST_V1",
    "HOOK_OVERLAY_PRESET",
    "HOOK_PLUS_PAYOFF_V1",
    "OverlayStylePreset",
    "TransitionStyle",
    "apply_editorial_template",
    "apply_overlay_density_cap",
    "get_editorial_template",
    "get_overlay_style_preset",
    "resolve_canonical_overlay_role",
    "select_and_apply_editorial_template",
    "select_editorial_template",
]
