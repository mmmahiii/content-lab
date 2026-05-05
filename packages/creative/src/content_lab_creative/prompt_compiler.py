"""Provider-safe prompt compilation from structured scene plans."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from content_lab_creative.types import ScenePlanOutput, ScenePlanScene
from content_lab_creative.visual_lint import lint_scene_visual_specificity

DEFAULT_NEGATIVE_PROMPT = "text overlays, captions, watermarks"
DEFAULT_MAX_PROMPT_CHARS = 1_800
DEFAULT_MAX_SCENE_FRAGMENT_CHARS = 280
PROMPT_COMPILER_VERSION = "scene_prompt_compiler_v2"

_META_PATTERN = re.compile(
    r"\b("
    r"scene plan|scene-plan|visual intent|shot guidance|overlay role|"
    r"fresh angle|persona|planner|planning prose|script package|"
    r"provider prompt|prompt fragment|generation process|"
    r"set up|plain-language step|show the payoff"
    r")\b",
    re.IGNORECASE,
)


class CompiledScenePromptFragment(BaseModel):
    """Provider-facing prompt fragment for one scene."""

    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(min_length=1, max_length=80)
    purpose: str = Field(min_length=1, max_length=40)
    start_seconds: int = Field(ge=0)
    end_seconds: int = Field(gt=0)
    prompt_text: str = Field(min_length=1, max_length=DEFAULT_MAX_SCENE_FRAGMENT_CHARS)
    source_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_timing(self) -> CompiledScenePromptFragment:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("fragment end_seconds must be greater than start_seconds")
        return self


class PromptTraceSource(BaseModel):
    """Source identifiers used to compile a provider prompt."""

    model_config = ConfigDict(extra="forbid")

    brief_title: str = Field(min_length=1, max_length=200)
    scene_plan_schema_version: str = Field(min_length=1, max_length=40)
    scene_plan_compiler_name: str = Field(min_length=1, max_length=80)
    scene_ids: list[str] = Field(default_factory=list)
    source_hash: str = Field(min_length=64, max_length=64)


class PromptSafetyPolicy(BaseModel):
    """Provider safety and length limits applied during prompt compilation."""

    model_config = ConfigDict(extra="forbid")

    negative_prompt: str = Field(default=DEFAULT_NEGATIVE_PROMPT, min_length=1, max_length=500)
    max_prompt_chars: int = Field(default=DEFAULT_MAX_PROMPT_CHARS, ge=200, le=4_000)
    max_scene_fragment_chars: int = Field(
        default=DEFAULT_MAX_SCENE_FRAGMENT_CHARS,
        ge=80,
        le=600,
    )
    removed_meta_language: bool = False
    generic_filler_removed: bool = False
    no_legible_text_instruction_applied: bool = False


class PromptTrace(BaseModel):
    """Explainable prompt trace from brief to scene plan to final provider prompt."""

    model_config = ConfigDict(extra="forbid")

    compiler_name: str = Field(default=PROMPT_COMPILER_VERSION, min_length=1, max_length=80)
    source: PromptTraceSource
    fragments: list[CompiledScenePromptFragment] = Field(default_factory=list, min_length=1)
    safety: PromptSafetyPolicy
    visual_style_lock: dict[str, Any] = Field(default_factory=dict)
    enriched_scene_fields: list[dict[str, Any]] = Field(default_factory=list)
    prompt_specificity_lint: dict[str, Any] = Field(default_factory=dict)
    prompt_hash: str = Field(min_length=64, max_length=64)
    final_prompt_chars: int = Field(ge=1)


class CompiledProviderPrompt(BaseModel):
    """Final provider prompt package plus trace."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1, max_length=DEFAULT_MAX_PROMPT_CHARS)
    negative_prompt: str = Field(default=DEFAULT_NEGATIVE_PROMPT, min_length=1, max_length=500)
    trace: PromptTrace
    prompt_kind: Literal["scene_plan_visual_prompt"] = "scene_plan_visual_prompt"


def compile_provider_prompt(
    *,
    brief_payload: Mapping[str, Any],
    scene_plan: ScenePlanOutput,
    provider: str,
    model: str,
    negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
    max_prompt_chars: int = DEFAULT_MAX_PROMPT_CHARS,
    max_scene_fragment_chars: int = DEFAULT_MAX_SCENE_FRAGMENT_CHARS,
) -> CompiledProviderPrompt:
    """Compile scene-plan nodes into a provider-safe prompt and trace."""

    brief_title = _required_text(brief_payload.get("title") or scene_plan.brief_title)
    content_pillar = _optional_text(brief_payload.get("content_pillar"))
    fragments = [
        _compile_scene_fragment(
            scene,
            content_pillar=content_pillar,
            max_chars=max_scene_fragment_chars,
        )
        for scene in scene_plan.scenes
    ]
    prefix = _safe_sentence(
        f"Vertical {model} video for {brief_title}"
        + (f", focused on {content_pillar}" if content_pillar else "")
    )
    prompt = _join_prompt(prefix=prefix, fragments=fragments, max_chars=max_prompt_chars)
    lint_results = [
        lint_scene_visual_specificity(
            scene.model_dump(mode="json"),
            prompt_text=fragment.prompt_text,
        )
        for scene, fragment in zip(scene_plan.scenes, fragments, strict=True)
    ]
    source_hash = _hash_text(scene_plan.model_dump_json())
    trace = PromptTrace(
        source=PromptTraceSource(
            brief_title=brief_title,
            scene_plan_schema_version=scene_plan.schema_version,
            scene_plan_compiler_name=scene_plan.compiler_name,
            scene_ids=[scene.scene_id for scene in scene_plan.scenes],
            source_hash=source_hash,
        ),
        fragments=fragments,
        safety=PromptSafetyPolicy(
            negative_prompt=negative_prompt,
            max_prompt_chars=max_prompt_chars,
            max_scene_fragment_chars=max_scene_fragment_chars,
            removed_meta_language=_contains_meta_language(scene_plan.model_dump_json()),
            generic_filler_removed=all(item.generic_filler_removed for item in lint_results),
            no_legible_text_instruction_applied=any(
                item.no_legible_text_instruction_applied for item in lint_results
            ),
        ),
        visual_style_lock=dict(scene_plan.visual_style_lock),
        enriched_scene_fields=[_scene_visual_fields(scene) for scene in scene_plan.scenes],
        prompt_specificity_lint={
            "passed": all(item.passed for item in lint_results),
            "scenes": [
                {"scene_id": scene.scene_id, **lint.as_dict()}
                for scene, lint in zip(scene_plan.scenes, lint_results, strict=True)
            ],
        },
        prompt_hash=_hash_text(prompt),
        final_prompt_chars=len(prompt),
    )
    return CompiledProviderPrompt(
        provider=provider,
        model=model,
        prompt=prompt,
        negative_prompt=negative_prompt,
        trace=trace,
    )


def _compile_scene_fragment(
    scene: ScenePlanScene,
    *,
    content_pillar: str | None,
    max_chars: int,
) -> CompiledScenePromptFragment:
    raw_text = " ".join(
        part
        for part in (
            f"{scene.purpose.value} scene",
            f"{scene.start_seconds}-{scene.end_seconds}s",
            f"{scene.camera_framing or scene.shot_guidance} view",
            scene.camera_motion,
            scene.subject,
            f"at {scene.setting}" if scene.setting else None,
            scene.action,
            f"with {scene.key_visual_object}" if scene.key_visual_object else None,
            _no_legible_text_instruction(scene),
            scene.lighting,
            scene.palette,
            scene.continuity_anchor,
            scene.visual_purpose,
            scene.visual_intent if not scene.subject else None,
            scene.shot_guidance if not scene.camera_framing else None,
        )
        if part
    )
    prompt_text = _trim_chars(_safe_sentence(raw_text), max_chars=max_chars)
    return CompiledScenePromptFragment(
        scene_id=scene.scene_id,
        purpose=scene.purpose.value,
        start_seconds=scene.start_seconds,
        end_seconds=scene.end_seconds,
        prompt_text=prompt_text,
        source_fields=[
            "purpose",
            "duration",
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
    )


def _scene_visual_fields(scene: ScenePlanScene) -> dict[str, Any]:
    return {
        key: getattr(scene, key)
        for key in (
            "scene_id",
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
        )
    }


def _no_legible_text_instruction(scene: ScenePlanScene) -> str:
    haystack = " ".join(
        str(part or "")
        for part in (
            scene.key_visual_object,
            scene.action,
            scene.setting,
            scene.visual_intent,
            scene.shot_guidance,
        )
    ).lower()
    if any(
        term in haystack
        for term in ("screen", "dashboard", "laptop", "inbox", "kanban", "ui", "task board")
    ):
        return "no legible text on screens, no captions, no watermarks"
    forbidden = ", ".join(scene.forbidden_visual_elements)
    return forbidden


def _join_prompt(
    *,
    prefix: str,
    fragments: list[CompiledScenePromptFragment],
    max_chars: int,
) -> str:
    prompt = ". ".join([prefix, *(fragment.prompt_text for fragment in fragments)])
    return _trim_chars(prompt, max_chars=max_chars)


def _safe_sentence(value: str) -> str:
    without_meta = _META_PATTERN.sub("", value)
    normalized = " ".join(without_meta.replace("|", " ").split())
    normalized = normalized.replace(" ,", ",").replace(" .", ".")
    return normalized.strip(" .,:;") + "."


def _trim_chars(value: str, *, max_chars: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= max_chars:
        return normalized
    trimmed = normalized[:max_chars].rsplit(" ", 1)[0].strip(" .,:;")
    return trimmed + "."


def _contains_meta_language(value: str) -> bool:
    return _META_PATTERN.search(value) is not None


def _required_text(value: Any) -> str:
    normalized = _optional_text(value)
    if normalized is None:
        raise ValueError("prompt compiler requires a non-empty brief title")
    return normalized


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).strip().split())
    return normalized or None


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "CompiledProviderPrompt",
    "CompiledScenePromptFragment",
    "DEFAULT_MAX_PROMPT_CHARS",
    "DEFAULT_MAX_SCENE_FRAGMENT_CHARS",
    "DEFAULT_NEGATIVE_PROMPT",
    "PromptSafetyPolicy",
    "PromptTrace",
    "PromptTraceSource",
    "PROMPT_COMPILER_VERSION",
    "compile_provider_prompt",
]
