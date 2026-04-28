"""Structured creative trace artifacts for reel packages."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SECRET_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "client_secret",
    "credential",
    "password",
    "secret",
    "token",
)
_REDACTED = "[redacted]"


class CreativeTraceGeneratorSelection(BaseModel):
    """Generator identity preserved for operator/debug inspection."""

    model_config = ConfigDict(extra="forbid")

    provider_name: str = "unknown"
    generator_path: str = "unknown"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreativeTraceArtifact(BaseModel):
    """Stable JSON artifact describing how a reel was conceived."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["phase_1"] = "phase_1"
    artifact_type: Literal["creative_trace"] = "creative_trace"
    reel_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    brief: dict[str, Any] = Field(default_factory=dict)
    generator_selection: CreativeTraceGeneratorSelection
    script: dict[str, Any] = Field(default_factory=dict)
    script_lint: dict[str, Any] = Field(default_factory=dict)
    scene_plan: dict[str, Any] = Field(default_factory=dict)
    compiled_prompt: dict[str, Any] = Field(default_factory=dict)
    prompt_trace: dict[str, Any] = Field(default_factory=dict)
    posting_plan: dict[str, Any] = Field(default_factory=dict)
    render_diagnostics: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "brief",
        "script",
        "script_lint",
        "scene_plan",
        "compiled_prompt",
        "prompt_trace",
        "posting_plan",
        "render_diagnostics",
        mode="before",
    )
    @classmethod
    def _sanitize_mapping(cls, value: object) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            return {}
        sanitized = sanitize_trace_payload(value)
        return sanitized if isinstance(sanitized, dict) else {}


def build_alignment_context(
    creative_output: Mapping[str, Any],
    *,
    editing_output: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract the fields alignment QA and observability tools compare.

    Values are JSON-friendly and safe to embed next to package format/repetition QA.
    """

    brief = _mapping(creative_output.get("brief"))
    script = _mapping(creative_output.get("script"))
    compiled_prompt = _mapping(creative_output.get("compiled_prompt"))
    editing = _mapping(editing_output) if editing_output is not None else {}
    lead = (
        str(brief.get("narrative_goal", "") or "").strip()
        or str(brief.get("title", "") or "").strip()
    )
    return {
        "lead_message": lead,
        "content_pillar": str(brief.get("content_pillar", "") or ""),
        "hook_text": str(script.get("hook_text", "") or ""),
        "compiled_prompt_excerpt": str(compiled_prompt.get("prompt", "") or "")[:400],
        "cover_frame_timestamp_seconds": editing.get("cover_frame_timestamp_seconds"),
        "duration_seconds": editing.get("duration_seconds"),
    }


def build_creative_trace(
    *,
    reel_id: str,
    run_id: str,
    creative_output: Mapping[str, Any],
    render_diagnostics: Mapping[str, Any] | None = None,
) -> CreativeTraceArtifact:
    """Build the package-adjacent creative trace from orchestration output."""

    script = _mapping(creative_output.get("script"))
    compiled_prompt = _mapping(creative_output.get("compiled_prompt"))
    prompt_trace = _mapping(compiled_prompt.get("trace"))
    if not prompt_trace:
        prompt_trace = _mapping(
            _mapping(creative_output.get("primary_asset_request")).get("prompt_trace")
        )

    diagnostics: dict[str, Any] = {}
    if render_diagnostics:
        sanitized = sanitize_trace_payload(dict(render_diagnostics))
        if isinstance(sanitized, dict):
            diagnostics = sanitized

    return CreativeTraceArtifact(
        reel_id=str(reel_id),
        run_id=str(run_id),
        brief=_mapping(creative_output.get("brief")),
        generator_selection=CreativeTraceGeneratorSelection(
            provider_name=str(
                _first_present(
                    _mapping(creative_output.get("script_generation")).get("provider_name"),
                    script.get("provider_name"),
                    "unknown",
                )
            ),
            generator_path=str(
                _first_present(
                    _mapping(creative_output.get("script_generation")).get("generator_path"),
                    script.get("generator_path"),
                    "unknown",
                )
            ),
            metadata=_mapping(
                _first_present(
                    _mapping(creative_output.get("script_generation")).get("generation_metadata"),
                    script.get("generation_metadata"),
                    {},
                )
            ),
        ),
        script=script,
        script_lint=_mapping(creative_output.get("script_lint")),
        scene_plan=_mapping(creative_output.get("scene_plan")),
        compiled_prompt=compiled_prompt,
        prompt_trace=prompt_trace,
        posting_plan=_mapping(creative_output.get("posting_plan")),
        render_diagnostics=diagnostics,
    )


def sanitize_trace_payload(value: Any) -> Any:
    """Recursively redact secret-looking values while preserving debug shape."""

    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if _is_secret_key(key):
                sanitized[key] = _REDACTED
            else:
                sanitized[key] = sanitize_trace_payload(raw_value)
        return sanitized
    if isinstance(value, list):
        return [sanitize_trace_payload(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_trace_payload(item) for item in value]
    return value


def _mapping(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        sanitized = sanitize_trace_payload(value)
        return sanitized if isinstance(sanitized, dict) else {}
    return {}


def _first_present(*values: object) -> object:
    for value in values:
        if value is not None:
            return value
    return None


def _is_secret_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    return any(fragment in normalized for fragment in _SECRET_KEY_FRAGMENTS)
