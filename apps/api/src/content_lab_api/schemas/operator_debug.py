"""Operator-facing debug surfaces for process-reel runs (creative trace, QA, scene plan)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from content_lab_api.models.task import Task

PROCESS_REEL_WORKFLOW_KEY = "process_reel"


class ScenePlanSummaryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    beat_count: int | None = None
    duration_seconds: float | None = None
    title: str | None = None


class PromptTraceSummaryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_count: int | None = None
    excerpt: str | None = None


class CreativeTraceSurfaceOut(BaseModel):
    """Creative trace: URI when packaged, optional inline body when ``expand_debug``."""

    model_config = ConfigDict(extra="forbid")

    storage_uri: str | None = None
    schema_version: str | None = None
    artifact_type: str | None = None
    reel_id: str | None = None
    run_id: str | None = None
    generator: dict[str, Any] = Field(default_factory=dict)
    body: dict[str, Any] | None = None


class ProcessReelQASurfaceOut(BaseModel):
    """QA rollup: semantic script findings alongside format / repetition / alignment."""

    model_config = ConfigDict(extra="forbid")

    passed: bool | None = None
    verdict: str | None = None
    semantic_script: dict[str, Any] | None = None
    format: dict[str, Any] | None = None
    repetition: dict[str, Any] | None = None
    alignment: dict[str, Any] | None = None
    checks: list[dict[str, Any]] = Field(default_factory=list)


class ProcessReelOperatorDebugOut(BaseModel):
    """Structured creative + QA references for operator diagnosis (detail responses)."""

    model_config = ConfigDict(extra="forbid")

    creative_trace: CreativeTraceSurfaceOut | None = None
    scene_plan: dict[str, Any] | None = None
    scene_plan_summary: ScenePlanSummaryOut | None = None
    prompt_trace: dict[str, Any] | None = None
    prompt_trace_summary: PromptTraceSummaryOut | None = None
    qa: ProcessReelQASurfaceOut | None = None
    package_qa: dict[str, Any] | None = None


def _coerce_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _scene_plan_summary(scene_plan: Mapping[str, Any]) -> ScenePlanSummaryOut:
    beats = scene_plan.get("beats") or scene_plan.get("scenes") or []
    beat_count = len(beats) if isinstance(beats, list) else None
    duration = scene_plan.get("duration_seconds")
    if duration is not None:
        try:
            duration_seconds = float(duration)
        except (TypeError, ValueError):
            duration_seconds = None
    else:
        duration_seconds = None
    title = scene_plan.get("title")
    return ScenePlanSummaryOut(
        beat_count=beat_count,
        duration_seconds=duration_seconds,
        title=str(title).strip() if title is not None else None,
    )


def _prompt_trace_summary(prompt_trace: Mapping[str, Any]) -> PromptTraceSummaryOut:
    steps = prompt_trace.get("steps") or prompt_trace.get("revisions") or []
    step_count = len(steps) if isinstance(steps, list) else None
    excerpt: str | None = None
    for key in ("summary", "final_prompt", "compiled", "prompt"):
        raw = prompt_trace.get(key)
        if isinstance(raw, str) and raw.strip():
            excerpt = raw.strip()[:500]
            break
    if excerpt is None:
        compiled = prompt_trace.get("compiled_prompt")
        if isinstance(compiled, str) and compiled.strip():
            excerpt = compiled.strip()[:500]
    return PromptTraceSummaryOut(step_count=step_count, excerpt=excerpt)


def _resolve_prompt_trace(creative_planning: Mapping[str, Any]) -> dict[str, Any]:
    compiled = _coerce_mapping(creative_planning.get("compiled_prompt"))
    trace = _coerce_mapping(compiled.get("trace"))
    if trace:
        return trace
    primary = _coerce_mapping(creative_planning.get("primary_asset_request"))
    return _coerce_mapping(primary.get("prompt_trace"))


def _qa_surface_from_mapping(qa_payload: Mapping[str, Any]) -> ProcessReelQASurfaceOut:
    details = qa_payload
    checks_raw = details.get("checks")
    checks: list[dict[str, Any]] = []
    if isinstance(checks_raw, list):
        for item in checks_raw:
            if isinstance(item, Mapping):
                checks.append(dict(item))
    return ProcessReelQASurfaceOut(
        passed=details.get("passed") if "passed" in details else None,
        verdict=str(details["verdict"]) if details.get("verdict") is not None else None,
        semantic_script=(
            dict(details["semantic_script"])
            if isinstance(details.get("semantic_script"), Mapping)
            else None
        ),
        format=dict(details["format"]) if isinstance(details.get("format"), Mapping) else None,
        repetition=(
            dict(details["repetition"])
            if isinstance(details.get("repetition"), Mapping)
            else None
        ),
        alignment=(
            dict(details["alignment"]) if isinstance(details.get("alignment"), Mapping) else None
        ),
        checks=checks,
    )


def _merge_qa_from_tasks(
    qa_payload: dict[str, Any],
    tasks: list[Task] | None,
) -> dict[str, Any]:
    if qa_payload:
        return qa_payload
    if not tasks:
        return {}
    for task_row in tasks:
        if task_row.task_type == "qa" and task_row.result:
            return dict(task_row.result)
    return {}


def _creative_trace_surface(
    *,
    package_payload: Mapping[str, Any],
    expand_debug: bool,
) -> CreativeTraceSurfaceOut | None:
    uri = package_payload.get("creative_trace_uri")
    storage_uri = str(uri).strip() if uri is not None and str(uri).strip() else None
    inline = package_payload.get("creative_trace")
    trace_dict: dict[str, Any] = (
        dict(inline) if isinstance(inline, Mapping) and inline else {}
    )
    body: dict[str, Any] | None = dict(trace_dict) if expand_debug and trace_dict else None
    generator: dict[str, Any] = {}
    if isinstance(trace_dict.get("generator_selection"), Mapping):
        generator = dict(trace_dict["generator_selection"])
    if not storage_uri and not trace_dict:
        return None
    return CreativeTraceSurfaceOut(
        storage_uri=storage_uri,
        schema_version=(
            str(trace_dict["schema_version"])
            if trace_dict.get("schema_version") is not None
            else None
        ),
        artifact_type=(
            str(trace_dict["artifact_type"])
            if trace_dict.get("artifact_type") is not None
            else None
        ),
        reel_id=str(trace_dict["reel_id"]) if trace_dict.get("reel_id") is not None else None,
        run_id=str(trace_dict["run_id"]) if trace_dict.get("run_id") is not None else None,
        generator=generator,
        body=body,
    )


def build_process_reel_operator_debug(
    *,
    workflow_key: str,
    summary: Mapping[str, Any] | None,
    tasks: list[Task] | None = None,
    expand_debug: bool = False,
    package_overlay: Mapping[str, Any] | None = None,
) -> ProcessReelOperatorDebugOut | None:
    """Build operator debug from a terminal ``process_reel`` summary or compatible dict."""

    if workflow_key != PROCESS_REEL_WORKFLOW_KEY:
        return None

    merged_summary: dict[str, Any] = dict(summary or {})
    if package_overlay:
        inner = dict(merged_summary.get("package") or {})
        for key, value in dict(package_overlay).items():
            if value is not None and inner.get(key) in (None, "", {}):
                inner[key] = value
        merged_summary["package"] = inner

    step_outputs = merged_summary.get("step_outputs")
    if not isinstance(step_outputs, Mapping):
        step_outputs = {}

    creative_planning = _coerce_mapping(step_outputs.get("creative_planning"))
    qa_payload = _merge_qa_from_tasks(_coerce_mapping(step_outputs.get("qa")), tasks)

    package_payload = _coerce_mapping(merged_summary.get("package"))
    if not package_payload and isinstance(step_outputs.get("packaging"), Mapping):
        packaging = _coerce_mapping(step_outputs.get("packaging"))
        nested_pkg = packaging.get("package")
        if isinstance(nested_pkg, Mapping):
            package_payload = _coerce_mapping(nested_pkg)
        else:
            package_payload = packaging

    scene_plan_raw = creative_planning.get("scene_plan")
    scene_plan = dict(scene_plan_raw) if isinstance(scene_plan_raw, Mapping) else None

    prompt_trace = _resolve_prompt_trace(creative_planning)
    prompt_trace_summary = _prompt_trace_summary(prompt_trace) if prompt_trace else None

    scene_plan_summary = _scene_plan_summary(scene_plan) if scene_plan else None

    creative_trace = _creative_trace_surface(package_payload=package_payload, expand_debug=expand_debug)

    qa_surface = _qa_surface_from_mapping(qa_payload) if qa_payload else None

    packaging_step = _coerce_mapping(step_outputs.get("packaging"))
    package_qa = None
    if isinstance(packaging_step.get("package_qa"), Mapping):
        package_qa = dict(packaging_step["package_qa"])
    elif isinstance(package_payload.get("package_qa"), Mapping):
        package_qa = dict(package_payload["package_qa"])

    if (
        creative_trace is None
        and scene_plan is None
        and not prompt_trace
        and qa_surface is None
        and package_qa is None
    ):
        return None

    return ProcessReelOperatorDebugOut(
        creative_trace=creative_trace,
        scene_plan=scene_plan if expand_debug else None,
        scene_plan_summary=scene_plan_summary,
        prompt_trace=dict(prompt_trace) if expand_debug and prompt_trace else None,
        prompt_trace_summary=prompt_trace_summary,
        qa=qa_surface,
        package_qa=package_qa,
    )
