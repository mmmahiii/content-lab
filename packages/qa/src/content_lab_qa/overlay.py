"""Overlay text fidelity QA: compare planned script overlays to the edit manifest."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from content_lab_core.types import QAVerdict
from content_lab_editing.overlays import TextOverlay, normalize_overlay_timeline
from content_lab_qa.gate import QAResult

Severity = Literal["fail"]
StackingMode = Literal["no_time_overlap", "separate_vertical_regions"]

_TEMPLATE_SEPARATE_VERTICAL: Final[frozenset[str]] = frozenset(
    {"hook_plus_payoff_v1", "calm_explainer_v1"}
)


def default_overlay_stack_policy_for_template(template_id: str | None) -> dict[str, str]:
    """Map editorial template selection to the collision/stacking policy for QA."""

    tid = (template_id or "").strip()
    if tid in _TEMPLATE_SEPARATE_VERTICAL:
        return {
            "mode": "separate_vertical_regions",
            "template_id": tid,
            "source": "editorial_template_id",
        }
    return {"mode": "no_time_overlap", "template_id": tid, "source": "default"}


class OverlayTextFidelityFinding(BaseModel):
    """A deterministic mismatch between planned overlays and the render manifest."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=80)
    severity: Severity = "fail"
    message: str = Field(min_length=1, max_length=1_200)
    details: dict[str, object] = Field(default_factory=dict)


class OverlayTextFidelityReport(BaseModel):
    """Structured overlay fidelity QA."""

    model_config = ConfigDict(extra="forbid")

    gate_name: str = "overlay_text_fidelity"
    verdict: QAVerdict
    message: str = ""
    findings: tuple[OverlayTextFidelityFinding, ...] = Field(default_factory=tuple)

    @property
    def blocks_readiness(self) -> bool:
        return self.verdict == QAVerdict.FAIL

    def as_qa_result(self) -> QAResult:
        return QAResult(
            gate_name=self.gate_name,
            verdict=self.verdict,
            message=self.message,
            details={
                "gate_name": self.gate_name,
                "verdict": self.verdict.value,
                "message": self.message,
                "findings": [finding.model_dump(mode="json") for finding in self.findings],
                "fail_findings": [finding.model_dump(mode="json") for finding in self.findings],
            },
        )


def evaluate_overlay_text_fidelity_qa(
    *,
    script: Mapping[str, Any],
    editing: Mapping[str, Any] | None = None,
) -> OverlayTextFidelityReport:
    """Fail when the edit overlay manifest disagrees with the plan or layout/collision policies."""

    editing_payload: dict[str, Any] = dict(editing or {})
    duration = _coalesce_float(
        editing_payload.get("duration_seconds"),
        script.get("duration_seconds"),
    )

    timeline = script.get("overlay_timeline")
    try:
        planned = _planned_overlay_rows(timeline, clip_duration_seconds=duration)
        authored = _authored_overlay_rows(timeline, clip_duration_seconds=duration)
    except ValueError as exc:
        return OverlayTextFidelityReport(
            verdict=QAVerdict.FAIL,
            message="Overlay timeline could not be interpreted for fidelity QA.",
            findings=(
                OverlayTextFidelityFinding(
                    code="overlay_timeline_unreadable",
                    message="Planned overlay timeline is not compatible with render normalization.",
                    details={"error": str(exc)},
                ),
            ),
        )

    manifest_raw = editing_payload.get("overlay_render_manifest")
    if planned and manifest_raw is None:
        return OverlayTextFidelityReport(
            verdict=QAVerdict.FAIL,
            message="Editing output is missing overlay_render_manifest while overlays are planned.",
            findings=(
                OverlayTextFidelityFinding(
                    code="overlay_manifest_missing",
                    message="Rendered overlay manifest was not emitted for this edit.",
                    details={
                        "planned_overlay_count": len(planned),
                        "planned_preview": [
                            {
                                "index": i,
                                "text": row.text,
                                "role": role,
                                "start_seconds": row.start_seconds,
                                "end_seconds": row.end_seconds,
                            }
                            for i, (row, role) in enumerate(planned)
                        ],
                    },
                ),
            ),
        )

    rendered = _parse_render_manifest(manifest_raw)
    if planned and rendered is None:
        return OverlayTextFidelityReport(
            verdict=QAVerdict.FAIL,
            message="Overlay render manifest is missing or invalid while overlays are planned.",
            findings=(
                OverlayTextFidelityFinding(
                    code="overlay_manifest_missing",
                    message="Rendered overlay manifest is absent or malformed.",
                    details={
                        "planned_overlay_count": len(planned),
                        "raw_type": type(manifest_raw).__name__,
                    },
                ),
            ),
        )

    if not planned:
        if rendered and len(rendered) > 0:
            return OverlayTextFidelityReport(
                verdict=QAVerdict.FAIL,
                message="Rendered overlays exist but the script planned none.",
                findings=(
                    OverlayTextFidelityFinding(
                        code="overlay_text_count_mismatch",
                        message="Overlay manifest contains entries while overlay_timeline is empty.",
                        details={
                            "planned_overlay_count": 0,
                            "rendered_overlay_count": len(rendered),
                            "rendered_preview": [_render_row_payload(r) for r in rendered],
                        },
                    ),
                ),
            )
        return OverlayTextFidelityReport(
            verdict=QAVerdict.PASS,
            message="No overlays planned; overlay fidelity checks skipped.",
        )

    assert rendered is not None
    if len(planned) != len(rendered):
        return OverlayTextFidelityReport(
            verdict=QAVerdict.FAIL,
            message="Planned overlay count does not match the rendered manifest.",
            findings=(
                OverlayTextFidelityFinding(
                    code="overlay_text_count_mismatch",
                    message="Overlay manifest length differs from the planned overlay timeline.",
                    details={
                        "planned_overlay_count": len(planned),
                        "rendered_overlay_count": len(rendered),
                        "planned_preview": [
                            _planned_row_payload(i, row, role)
                            for i, (row, role) in enumerate(planned)
                        ],
                        "rendered_preview": [_render_row_payload(r) for r in rendered],
                    },
                ),
            ),
        )

    findings: list[OverlayTextFidelityFinding] = []
    for index, ((planned_overlay, role), rendered_row) in enumerate(
        zip(planned, rendered, strict=True)
    ):
        if planned_overlay.text != rendered_row.text:
            findings.append(
                OverlayTextFidelityFinding(
                    code="overlay_text_mismatch",
                    message="Rendered overlay text does not match the planned overlay text.",
                    details={
                        "index": index,
                        "planned_role": role,
                        "planned_text": planned_overlay.text,
                        "rendered_text": rendered_row.text,
                    },
                )
            )
            continue
        if not _timing_match(planned_overlay, rendered_row):
            findings.append(
                OverlayTextFidelityFinding(
                    code="overlay_timing_mismatch",
                    message="Rendered overlay timing does not match the planned overlay timing.",
                    details={
                        "index": index,
                        "planned_role": role,
                        "planned_text": planned_overlay.text,
                        "rendered_text": rendered_row.text,
                        "planned_start_seconds": planned_overlay.start_seconds,
                        "rendered_start_seconds": rendered_row.start_seconds,
                        "planned_end_seconds": planned_overlay.end_seconds,
                        "rendered_end_seconds": rendered_row.end_seconds,
                    },
                )
            )

    findings.extend(
        _overlay_layout_findings(
            planned=planned,
            rendered=rendered,
            editing_payload=editing_payload,
        )
    )
    findings.extend(
        _overlay_collision_findings(
            planned=planned,
            rendered=rendered,
            editing_payload=editing_payload,
            clip_end_seconds=duration,
            authored=authored,
        )
    )

    if findings:
        return OverlayTextFidelityReport(
            verdict=QAVerdict.FAIL,
            message="; ".join(f.message for f in findings),
            findings=tuple(findings),
        )

    return OverlayTextFidelityReport(
        verdict=QAVerdict.PASS,
        message="Overlay script, manifest, layout, safe-area, and collision checks passed.",
    )


@dataclass(slots=True)
class _RenderRow:
    text: str
    start_seconds: float
    end_seconds: float | None
    layout: dict[str, Any] | None = None


def _overlay_layout_findings(
    *,
    planned: list[tuple[TextOverlay, str]],
    rendered: list[_RenderRow],
    editing_payload: dict[str, Any],
) -> list[OverlayTextFidelityFinding]:
    findings: list[OverlayTextFidelityFinding] = []
    raw_safe = editing_payload.get("overlay_safe_area")
    if not _is_valid_overlay_safe_area(raw_safe):
        findings.append(
            OverlayTextFidelityFinding(
                code="overlay_safe_area_missing",
                message="Editing output is missing a valid overlay_safe_area block for layout QA.",
                details={
                    "expected_keys": sorted(_REQUIRED_SAFE_AREA_KEYS),
                    "raw_type": type(raw_safe).__name__,
                },
            )
        )
        return findings

    assert isinstance(raw_safe, Mapping)
    safe_payload = {k: _as_int_for_json(raw_safe[k]) for k in sorted(_REQUIRED_SAFE_AREA_KEYS)}

    for index, ((_planned_overlay, role), row) in enumerate(zip(planned, rendered, strict=True)):
        layout = row.layout
        if layout is None:
            findings.append(
                OverlayTextFidelityFinding(
                    code="overlay_layout_missing",
                    message="Overlay manifest entry is missing layout metrics from the renderer.",
                    details={
                        "index": index,
                        "planned_role": role,
                        "overlay_text": row.text,
                        "overlay_safe_area": safe_payload,
                    },
                )
            )
            continue
        if not layout.get("layout_verified", False):
            continue

        detail_base: dict[str, object] = {
            "index": index,
            "planned_role": role,
            "overlay_text": row.text,
            "layout": dict(layout),
            "overlay_safe_area": safe_payload,
        }
        if bool(layout.get("font_unreadably_small")):
            findings.append(
                OverlayTextFidelityFinding(
                    code="overlay_font_unreadably_small",
                    message="Overlay font size is below the readability threshold for this resolution.",
                    details={**detail_base, "font_size": layout.get("font_size")},
                )
            )
        if bool(layout.get("did_not_fit_horizontally")):
            findings.append(
                OverlayTextFidelityFinding(
                    code="overlay_text_did_not_fit",
                    message="Overlay text is too wide for the usable horizontal band (likely clipped or squashed).",
                    details={
                        **detail_base,
                        "usable_max_text_width_px": layout.get("usable_max_text_width_px"),
                        "max_line_width_px": layout.get("max_line_width_px"),
                    },
                )
            )
        if bool(layout.get("out_of_bounds")):
            findings.append(
                OverlayTextFidelityFinding(
                    code="overlay_out_of_frame",
                    message="Overlay estimate sits outside the video frame (clipped or unreadable).",
                    details={
                        **detail_base,
                        "block_left_px": layout.get("block_left_px"),
                        "block_top_px": layout.get("block_top_px"),
                        "block_right_px": layout.get("block_right_px"),
                        "block_bottom_px": layout.get("block_bottom_px"),
                    },
                )
            )
        elif not bool(layout.get("fits_safe_area", False)):
            findings.append(
                OverlayTextFidelityFinding(
                    code="overlay_safe_area_violation",
                    message="Overlay leaves the title-safe region (likely obscured by platform chrome).",
                    details={
                        **detail_base,
                        "block_left_px": layout.get("block_left_px"),
                        "block_top_px": layout.get("block_top_px"),
                        "block_right_px": layout.get("block_right_px"),
                        "block_bottom_px": layout.get("block_bottom_px"),
                    },
                )
            )
    return findings


_TIME_OVERLAP_EPS = 0.05


def _overlay_collision_findings(
    *,
    planned: list[tuple[TextOverlay, str]],
    rendered: list[_RenderRow],
    editing_payload: dict[str, Any],
    clip_end_seconds: float | None,
    authored: list[tuple[TextOverlay, str]] | None = None,
) -> list[OverlayTextFidelityFinding]:
    collision_source = authored if authored is not None else planned
    if len(collision_source) < 2:
        return []

    mode, policy_meta = _resolve_overlay_stack_policy(editing_payload)
    mode_typed = cast(StackingMode, mode)

    clip_end = clip_end_seconds
    if clip_end is None:
        ends = [float(r.end_seconds) for r in rendered if r.end_seconds is not None]
        clip_end = max(ends) if ends else None

    intervals: list[tuple[float, float]] = []
    for overlay, _role in collision_source:
        start = float(overlay.start_seconds)
        end_raw = overlay.end_seconds
        if end_raw is None:
            if clip_end is None:
                return [
                    OverlayTextFidelityFinding(
                        code="overlay_collision_unverified",
                        message="Overlay collision QA needs clip duration or per-cue end times.",
                        details={
                            "stack_policy_mode": mode_typed,
                            "stack_policy": dict(policy_meta),
                        },
                    )
                ]
            end_f = float(clip_end)
        else:
            end_f = float(end_raw)
        end_f = max(end_f, start + _TIME_OVERLAP_EPS * 2)
        intervals.append((start, end_f))

    findings: list[OverlayTextFidelityFinding] = []
    for i in range(len(intervals)):
        for j in range(i + 1, len(intervals)):
            overlap = _overlap_interval_seconds(intervals[i], intervals[j])
            if overlap is None:
                continue
            if mode_typed == "separate_vertical_regions" and (
                _planned_vertical_align(collision_source[i][0])
                != _planned_vertical_align(collision_source[j][0])
            ):
                continue
            role_i = collision_source[i][1]
            role_j = collision_source[j][1]
            findings.append(
                OverlayTextFidelityFinding(
                    code="overlay_time_collision",
                    message="Two overlays share a visible time window under the active stacking policy.",
                    details={
                        "stack_policy_mode": mode_typed,
                        "stack_policy": dict(policy_meta),
                        "overlap_start_seconds": overlap[0],
                        "overlap_end_seconds": overlap[1],
                        "overlay_a": _overlay_collision_actor_from_overlay(
                            i, role_i, collision_source[i][0]
                        ),
                        "overlay_b": _overlay_collision_actor_from_overlay(
                            j, role_j, collision_source[j][0]
                        ),
                    },
                )
            )
    return findings


def _planned_vertical_align(overlay: TextOverlay) -> str:
    return str(overlay.vertical_align)


def _resolve_overlay_stack_policy(
    editing_payload: Mapping[str, Any],
) -> tuple[str, dict[str, str]]:
    raw = editing_payload.get("overlay_stack_policy")
    if isinstance(raw, Mapping):
        mode = str(raw.get("mode") or "").strip()
        if mode in ("no_time_overlap", "separate_vertical_regions"):
            meta: dict[str, str] = {"mode": mode}
            for key in ("source", "template_id"):
                value = raw.get(key)
                if isinstance(value, str):
                    meta[key] = value
                elif isinstance(value, int | float | bool):
                    meta[key] = str(value)
            return mode, meta
    tid = editing_payload.get("editorial_template_id")
    if isinstance(tid, str) and tid.strip() in _TEMPLATE_SEPARATE_VERTICAL:
        t = tid.strip()
        return "separate_vertical_regions", {
            "mode": "separate_vertical_regions",
            "template_id": t,
            "source": "editorial_template_id",
        }
    return "no_time_overlap", {"mode": "no_time_overlap", "source": "default"}


def _overlap_interval_seconds(
    a: tuple[float, float],
    b: tuple[float, float],
) -> tuple[float, float] | None:
    lo = max(a[0], b[0])
    hi = min(a[1], b[1])
    if hi - lo <= _TIME_OVERLAP_EPS:
        return None
    return (lo, hi)


def _overlap_excused_by_vertical_stack(
    layout_a: dict[str, Any] | None,
    layout_b: dict[str, Any] | None,
) -> bool:
    if not layout_a or not layout_b:
        return False
    if not layout_a.get("layout_verified") or not layout_b.get("layout_verified"):
        return False
    va = layout_a.get("vertical_align")
    vb = layout_b.get("vertical_align")
    if not isinstance(va, str) or not isinstance(vb, str):
        return False
    if va == vb:
        return False
    return {va, vb} == {"top", "bottom"}


def _overlay_collision_actor(
    index: int,
    role: str,
    row: _RenderRow,
) -> dict[str, object]:
    return {
        "overlay_id": f"overlay-{index}",
        "index": index,
        "planned_role": role,
        "text": row.text,
        "start_seconds": row.start_seconds,
        "end_seconds": row.end_seconds,
    }


def _overlay_collision_actor_from_overlay(
    index: int,
    role: str,
    overlay: TextOverlay,
) -> dict[str, object]:
    return {
        "overlay_id": f"overlay-{index}",
        "index": index,
        "planned_role": role,
        "text": overlay.text,
        "start_seconds": overlay.start_seconds,
        "end_seconds": overlay.end_seconds,
    }


_REQUIRED_SAFE_AREA_KEYS = frozenset(
    {"frame_width", "frame_height", "inset_left", "inset_right", "inset_top", "inset_bottom"}
)


def _is_valid_overlay_safe_area(raw: object) -> bool:
    if not isinstance(raw, Mapping):
        return False
    try:
        return all(k in raw for k in _REQUIRED_SAFE_AREA_KEYS) and all(
            _optional_int_for_area(raw.get(k)) is not None for k in _REQUIRED_SAFE_AREA_KEYS
        )
    except (TypeError, ValueError):
        return False


def _optional_int_for_area(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip(), 10)
        except ValueError:
            return None
    return None


def _as_int_for_json(value: object) -> int:
    parsed = _optional_int_for_area(value)
    if parsed is None:
        raise ValueError("expected integral safe-area component")
    return int(parsed)


def _planned_row_payload(index: int, row: TextOverlay, role: str) -> dict[str, object]:
    return {
        "index": index,
        "planned_role": role,
        "text": row.text,
        "start_seconds": row.start_seconds,
        "end_seconds": row.end_seconds,
    }


def _render_row_payload(row: _RenderRow) -> dict[str, object]:
    return {
        "text": row.text,
        "start_seconds": row.start_seconds,
        "end_seconds": row.end_seconds,
    }


def _coalesce_float(primary: object, fallback: object) -> float | None:
    result = _optional_float(primary)
    if result is not None:
        return result
    return _optional_float(fallback)


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _planned_overlay_rows(
    timeline: object,
    *,
    clip_duration_seconds: float | None,
) -> list[tuple[TextOverlay, str]]:
    if not isinstance(timeline, list):
        return []
    role_rows: list[tuple[float, float, str]] = []
    for raw in timeline:
        if not isinstance(raw, Mapping):
            continue
        role = str(raw.get("emphasis") or raw.get("overlay_role") or "").strip()
        start = (
            _optional_float(raw.get("start_seconds")) or _optional_float(raw.get("start")) or 0.0
        )
        end = _optional_float(raw.get("end_seconds")) or _optional_float(raw.get("end"))
        if end is None:
            duration = _optional_float(raw.get("duration_seconds")) or _optional_float(
                raw.get("duration")
            )
            if duration is not None:
                end = start + duration
        role_rows.append((start, end or float("inf"), role))

    overlays = normalize_overlay_timeline(timeline, clip_duration_seconds=clip_duration_seconds)
    rows: list[tuple[TextOverlay, str]] = []
    role_rows.sort(key=lambda item: (item[0], item[1]))
    for index, overlay in enumerate(overlays):
        role = role_rows[index][2] if index < len(role_rows) else overlay.overlay_role
        rows.append((overlay, role))
    return rows


def _authored_overlay_rows(
    timeline: object,
    *,
    clip_duration_seconds: float | None,
) -> list[tuple[TextOverlay, str]]:
    if not isinstance(timeline, list):
        return []
    rows: list[tuple[TextOverlay, str]] = []
    for raw in timeline:
        if not isinstance(raw, Mapping):
            continue
        role = str(raw.get("emphasis") or raw.get("overlay_role") or "").strip()
        mapping = dict(raw)
        text_value = str(mapping.get("text") or "").strip()
        if not text_value and mapping.get("overlay_text") is not None:
            mapping["text"] = str(mapping.get("overlay_text") or "").strip()
        overlay = TextOverlay.from_mapping(mapping, clip_duration_seconds=clip_duration_seconds)
        rows.append((overlay, role))
    rows.sort(
        key=lambda item: (item[0].start_seconds, item[0].end_seconds or float("inf")),
    )
    return rows


def _parse_render_manifest(raw: object) -> list[_RenderRow] | None:
    if not isinstance(raw, list):
        return None
    rendered: list[_RenderRow] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            return None
        text = str(entry.get("text") or "").strip()
        start = _optional_float(entry.get("start_seconds"))
        if start is None:
            start = 0.0
        end = _optional_float(entry.get("end_seconds"))
        layout_payload = entry.get("layout")
        layout: dict[str, Any] | None
        if layout_payload is None:
            layout = None
        elif isinstance(layout_payload, Mapping):
            layout = dict(layout_payload)
        else:
            return None
        rendered.append(_RenderRow(text=text, start_seconds=start, end_seconds=end, layout=layout))
    return rendered


_TIMING_EPS = 0.02


def _timing_match(planned: TextOverlay, rendered: _RenderRow) -> bool:
    if abs(planned.start_seconds - rendered.start_seconds) > _TIMING_EPS:
        return False
    pe = planned.end_seconds
    re = rendered.end_seconds
    if pe is None and re is None:
        return True
    if pe is None or re is None:
        return False
    return bool(abs(float(pe) - float(re)) <= _TIMING_EPS)
