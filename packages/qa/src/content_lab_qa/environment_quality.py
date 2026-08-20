"""Environment base quality gating for cinematic reel plans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from content_lab_creative.planning_schema import CinematicReelPlan, TimelineObject
from content_lab_editing.render_strategy import (
    DOWNGRADED_RENDER_STRATEGIES,
    REALISTIC_RENDER_STRATEGIES,
    downgrade_render_strategy_for_environment_quality,
)

EnvironmentQualitySeverity = Literal["warn", "fail"]

SHARP_FULL_FRAME_MIN_WIDTH = 1080
SHARP_FULL_FRAME_MIN_HEIGHT = 1600


@dataclass(frozen=True, slots=True)
class EnvironmentQualityFinding:
    code: str
    severity: EnvironmentQualitySeverity
    message: str
    scene_id: str | None
    suggested_fix: str
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "scene_id": self.scene_id,
            "suggested_fix": self.suggested_fix,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class EnvironmentQualityReport:
    findings: tuple[EnvironmentQualityFinding, ...]
    recommended_render_strategy: str
    realism_risk_delta: float

    @property
    def passed(self) -> bool:
        return not any(finding.severity == "fail" for finding in self.findings)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "environment_quality_qa_v1",
            "passed": self.passed,
            "recommended_render_strategy": self.recommended_render_strategy,
            "realism_risk_delta": self.realism_risk_delta,
            "findings": [finding.as_dict() for finding in self.findings],
            "failure_codes": [
                finding.code for finding in self.findings if finding.severity == "fail"
            ],
            "warning_codes": [
                finding.code for finding in self.findings if finding.severity == "warn"
            ],
        }


def environment_base_full_frame_eligible(width: int | None, height: int | None) -> bool:
    """Return whether source dimensions are sharp enough for 9:16 full-frame use."""

    if width is None or height is None:
        return False
    return width >= SHARP_FULL_FRAME_MIN_WIDTH or height >= SHARP_FULL_FRAME_MIN_HEIGHT


def validate_environment_quality(plan: CinematicReelPlan) -> EnvironmentQualityReport:
    """Validate environment base sharpness and render strategy credibility."""

    findings: list[EnvironmentQualityFinding] = []
    environment_bases = [
        item for scene in plan.scenes for item in scene.objects if item.role == "environment_base"
    ]
    has_sharp_environment = any(_can_use_as_sharp_full_frame(item) for item in environment_bases)
    recommended = downgrade_render_strategy_for_environment_quality(
        has_environment_base=bool(environment_bases),
        has_sharp_environment_base=has_sharp_environment,
    )
    risk_delta = 0.0

    if not environment_bases:
        if plan.render_strategy in REALISTIC_RENDER_STRATEGIES:
            findings.append(
                _finding(
                    "missing_valid_environment_base",
                    "fail",
                    "Realistic render strategy has no environment_base asset.",
                    None,
                    "Downgrade to product_card_layout, tabletop_layout, or graphic_layout.",
                    recommended_render_strategy=recommended,
                )
            )
        return EnvironmentQualityReport(
            findings=tuple(findings),
            recommended_render_strategy=recommended,
            realism_risk_delta=0.35,
        )

    for scene in plan.scenes:
        for item in [obj for obj in scene.objects if obj.role == "environment_base"]:
            if item.source_width is None or item.source_height is None:
                findings.append(
                    _finding(
                        "environment_dimensions_unknown",
                        "warn",
                        "Environment base source dimensions are unknown.",
                        scene.scene_id,
                        "Attach source_width/source_height so full-frame eligibility can be checked.",
                        object_id=item.object_id,
                    )
                )
                continue
            if _can_use_as_sharp_full_frame(item):
                continue
            risk_delta = max(risk_delta, 0.25)
            if plan.render_strategy in REALISTIC_RENDER_STRATEGIES and _fills_frame(item):
                findings.append(
                    _finding(
                        "low_res_environment_full_frame",
                        "fail",
                        "Low-resolution environment cannot be used as a sharp full-frame scene.",
                        scene.scene_id,
                        "Use low_res_texture_backdrop or downgrade to a card/tabletop/graphic layout.",
                        object_id=item.object_id,
                        source_width=item.source_width,
                        source_height=item.source_height,
                        recommended_render_strategy="low_res_texture_backdrop",
                    )
                )
            else:
                findings.append(
                    _finding(
                        "low_res_environment_texture_only",
                        "warn",
                        "Low-resolution environment is allowed only as blurred/padded texture.",
                        scene.scene_id,
                        "Keep it blurred/padded and let foreground assets carry sharp detail.",
                        object_id=item.object_id,
                        source_width=item.source_width,
                        source_height=item.source_height,
                    )
                )
            if not _render_notes_cover_low_res(plan.render_notes):
                findings.append(
                    _finding(
                        "missing_low_res_render_notes",
                        "fail" if plan.render_strategy == "low_res_texture_backdrop" else "warn",
                        "Render notes do not describe low-resolution backdrop handling.",
                        scene.scene_id,
                        "Add notes for blur, padding/crop, texture backdrop, and foreground detail.",
                        object_id=item.object_id,
                    )
                )

    if (
        not has_sharp_environment
        and plan.render_strategy in REALISTIC_RENDER_STRATEGIES
        and not any(finding.severity == "fail" for finding in findings)
    ):
        findings.append(
            _finding(
                "realistic_strategy_without_sharp_environment",
                "warn",
                "Realistic strategy has no confirmed sharp environment base.",
                None,
                "Confirm source dimensions or downgrade render_strategy.",
                recommended_render_strategy=recommended,
            )
        )
    if plan.render_strategy in DOWNGRADED_RENDER_STRATEGIES and not has_sharp_environment:
        findings.append(
            _finding(
                "render_strategy_downgraded_for_environment",
                "warn",
                "Render strategy is downgraded because no sharp environment base is available.",
                None,
                "Use foreground detail and avoid pretending this is a real filmed scene.",
                recommended_render_strategy=plan.render_strategy,
            )
        )

    return EnvironmentQualityReport(
        findings=tuple(findings),
        recommended_render_strategy=recommended,
        realism_risk_delta=risk_delta,
    )


def _can_use_as_sharp_full_frame(item: TimelineObject) -> bool:
    return environment_base_full_frame_eligible(item.source_width, item.source_height)


def _fills_frame(item: TimelineObject) -> bool:
    return item.width_normalised * item.scale >= 0.9 or item.height_normalised * item.scale >= 0.9


def _render_notes_cover_low_res(render_notes: list[str]) -> bool:
    text = " ".join(render_notes).lower()
    return "low-res" in text or (
        "blur" in text and ("pad" in text or "texture" in text or "foreground" in text)
    )


def _finding(
    code: str,
    severity: EnvironmentQualitySeverity,
    message: str,
    scene_id: str | None,
    suggested_fix: str,
    **details: Any,
) -> EnvironmentQualityFinding:
    return EnvironmentQualityFinding(
        code=code,
        severity=severity,
        message=message,
        scene_id=scene_id,
        suggested_fix=suggested_fix,
        details=details,
    )


__all__ = [
    "EnvironmentQualityFinding",
    "EnvironmentQualityReport",
    "EnvironmentQualitySeverity",
    "SHARP_FULL_FRAME_MIN_HEIGHT",
    "SHARP_FULL_FRAME_MIN_WIDTH",
    "environment_base_full_frame_eligible",
    "validate_environment_quality",
]
