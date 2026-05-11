"""Package completeness QA for ready-to-post reel packages."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from pydantic import Field

from content_lab_core.models import DomainModel
from content_lab_core.types import QAVerdict
from content_lab_qa.gate import QAResult, qa_result_blocks_readiness
from content_lab_qa.provenance import validate_package_provenance
from content_lab_qa.semantic_script import SemanticScriptQARequest, evaluate_semantic_script
from content_lab_qa.source_rights import validate_source_rights
from content_lab_qa.text import validate_caption_meta_language

_REQUIRED_PACKAGE_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("final_video", "final_video.mp4"),
    ("cover", "cover.png"),
    ("caption_variants", "caption_variants.txt"),
    ("posting_plan", "posting_plan.json"),
    ("provenance", "provenance.json"),
    ("timeline", "timeline.json"),
    ("timeline_render_trace", "timeline_render_trace.json"),
    ("overlay_render_trace", "overlay_render_trace.json"),
)
_HEX_DIGITS = frozenset("0123456789abcdef")


class PackageQAResult(DomainModel):
    """Aggregated package QA verdict with reusable per-check output."""

    verdict: QAVerdict
    message: str = ""
    errors: list[str] = Field(default_factory=list)
    checks: list[QAResult] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.verdict in (QAVerdict.PASS, QAVerdict.SKIP)

    def as_payload(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "verdict": self.verdict.value,
            "message": self.message,
            "errors": list(self.errors),
            "checks": [check.as_payload() for check in self.checks],
        }


class PackageQualityAssuranceError(ValueError):
    """Raised when ready-to-post package gates fail (completeness, captions, provenance, etc.)."""

    def __init__(self, message: str, *, package_qa: PackageQAResult | None = None) -> None:
        super().__init__(message)
        self.package_qa = package_qa


def evaluate_package(package_payload: Mapping[str, Any] | object) -> PackageQAResult:
    """Evaluate ready-to-post package completeness and provenance deterministically."""

    checks: list[QAResult] = [
        validate_package_completeness(package_payload),
        validate_layered_output_format(package_payload),
        validate_package_media_timeline(package_payload),
        validate_package_overlay_render_trace(package_payload),
        validate_caption_meta_language(package_payload),
        validate_package_provenance(_provenance_payload(package_payload)),
        validate_source_rights(_provenance_payload(package_payload)),
        validate_package_script_semantics(package_payload),
    ]
    errors = [
        check.message for check in checks if qa_result_blocks_readiness(check) and check.message
    ]
    verdict = QAVerdict.PASS if not errors else QAVerdict.FAIL
    message = "Package QA passed." if not errors else errors[0]
    return PackageQAResult(verdict=verdict, message=message, errors=errors, checks=checks)


def validate_package_script_semantics(package_payload: Mapping[str, Any] | object) -> QAResult:
    """Evaluate caption/script semantics when a package payload carries inline phase-1 script JSON."""

    if not isinstance(package_payload, Mapping):
        return QAResult(
            gate_name="package_script_semantics",
            verdict=QAVerdict.SKIP,
            message="Package payload is not a mapping; semantic caption QA skipped.",
            details={"skipped": True},
        )
    script = package_payload.get("script")
    if not isinstance(script, Mapping):
        return QAResult(
            gate_name="package_script_semantics",
            verdict=QAVerdict.SKIP,
            message="Package payload has no inline script; semantic caption QA skipped.",
            details={"skipped": True},
        )

    report = evaluate_semantic_script(SemanticScriptQARequest(script=script))
    base = report.as_qa_result()
    return QAResult(
        gate_name="package_script_semantics",
        verdict=base.verdict,
        message=base.message,
        details=dict(base.details),
    )


def validate_layered_output_format(package_payload: Mapping[str, Any] | object) -> QAResult:
    """Validate rendered layered output before package readiness."""

    if not isinstance(package_payload, Mapping):
        return QAResult(
            gate_name="package_layered_output",
            verdict=QAVerdict.FAIL,
            message="Package payload must be a JSON object for layered output QA.",
            details={"findings": [_finding("layered_output_payload_missing")]},
        )
    if not _requires_layered_output_check(package_payload):
        return QAResult(
            gate_name="package_layered_output",
            verdict=QAVerdict.SKIP,
            message="Package has no layered output metadata; layered output QA skipped.",
            details={"skipped": True},
        )

    findings: list[dict[str, Any]] = []
    artifacts = _artifact_index(package_payload.get("artifacts"))
    output = _layered_output_metadata(package_payload)
    video_stream = _first_stream(output, "video")
    audio_stream = _first_stream(output, "audio")

    width = _optional_float(output.get("width") or video_stream.get("width"))
    height = _optional_float(output.get("height") or video_stream.get("height"))
    if width != 1080 or height != 1920:
        findings.append(
            _finding(
                "final_video_dimensions_invalid",
                width=width,
                height=height,
                expected_width=1080,
                expected_height=1920,
            )
        )

    format_name = str(output.get("format_name") or "").strip().lower()
    container = str(output.get("container") or output.get("format") or "").strip().lower()
    final_video = artifacts.get("final_video", {})
    final_filename = _artifact_filename(final_video)
    has_container_metadata = bool(format_name or container)
    invalid_container_metadata = "mp4" not in format_name and container != "mp4"
    invalid_filename = not final_filename.endswith(".mp4")
    if (has_container_metadata and invalid_container_metadata) or (
        not has_container_metadata and invalid_filename
    ):
        findings.append(
            _finding(
                "final_video_not_valid_mp4",
                format_name=format_name,
                container=container,
                filename=final_filename,
            )
        )

    duration = _optional_float(
        output.get("duration_seconds")
        or output.get("duration")
        or _mapping_get(output.get("format"), "duration")
    )
    expected_duration = _expected_package_duration(package_payload)
    if duration is None or duration <= 0:
        findings.append(_finding("final_video_duration_missing"))
    elif expected_duration is not None and abs(duration - expected_duration) > 0.25:
        findings.append(
            _finding(
                "final_video_duration_invalid",
                duration_seconds=duration,
                expected_duration_seconds=expected_duration,
            )
        )

    intentional_silence = bool(
        package_payload.get("intentional_silence")
        or output.get("intentional_silence")
        or _mapping_get(package_payload.get("audio"), "intentional_silence")
    )
    if not audio_stream and not intentional_silence:
        findings.append(_finding("final_video_missing_audio"))

    cover = artifacts.get("cover")
    if cover is None:
        findings.append(_finding("cover_image_missing"))
    elif _artifact_filename(cover) != "cover.png":
        findings.append(
            _finding("cover_image_invalid", filename=_artifact_filename(cover))
        )

    completeness = validate_package_completeness(package_payload)
    if not completeness.passed:
        findings.append(
            _finding(
                "package_artifacts_incomplete",
                errors=_string_list(completeness.details.get("errors")),
            )
        )

    if findings:
        return QAResult(
            gate_name="package_layered_output",
            verdict=QAVerdict.FAIL,
            message="Layered output format validation failed.",
            details={"findings": findings},
        )
    return QAResult(
        gate_name="package_layered_output",
        verdict=QAVerdict.PASS,
        message="Layered output format validation passed.",
        details={"findings": []},
    )


def validate_package_overlay_render_trace(package_payload: Mapping[str, Any] | object) -> QAResult:
    """Validate overlay render trace fields before a package reaches ready."""

    if not isinstance(package_payload, Mapping):
        return QAResult(
            gate_name="package_overlay_render_trace",
            verdict=QAVerdict.FAIL,
            message="Package payload must be a JSON object for overlay QA.",
            details={"findings": [{"code": "overlay_render_trace_missing", "severity": "fail"}]},
        )
    trace = package_payload.get("overlay_render_trace")
    if not isinstance(trace, Mapping):
        return QAResult(
            gate_name="package_overlay_render_trace",
            verdict=QAVerdict.FAIL,
            message="Package payload is missing overlay_render_trace.",
            details={"findings": [{"code": "overlay_render_trace_missing", "severity": "fail"}]},
        )
    overlays = trace.get("overlays")
    if not isinstance(overlays, list):
        return QAResult(
            gate_name="package_overlay_render_trace",
            verdict=QAVerdict.FAIL,
            message="Overlay render trace is missing overlays.",
            details={"findings": [{"code": "overlay_render_trace_missing", "severity": "fail"}]},
        )

    duration = _optional_float(
        trace.get("clip_duration_seconds")
        or package_payload.get("duration_seconds")
        or _mapping_get(package_payload.get("timeline"), "duration_seconds")
    )
    frame_height = int(_optional_float(trace.get("frame_height_px")) or 1920)
    min_font = max(24, frame_height // 72)
    findings: list[dict[str, Any]] = []
    intervals: list[tuple[int, float, float]] = []

    for index, raw in enumerate(overlays):
        if not isinstance(raw, Mapping):
            continue
        source_text = str(raw.get("source_text") or "").strip()
        rendered_text = str(
            raw.get("rendered_text") or raw.get("text") or raw.get("final_render_text") or ""
        ).strip()
        role = str(raw.get("role") or raw.get("preset") or "").strip().lower()
        if source_text != rendered_text:
            findings.append(_overlay_trace_finding("overlay_text_mismatch", index))
            if role == "hook" or source_text.startswith(rendered_text):
                findings.append(_overlay_trace_finding("hook_incomplete", index))
        if bool(raw.get("clipped")):
            findings.append(_overlay_trace_finding("overlay_text_clipped", index))
        if raw.get("safe_area_passed") is False:
            findings.append(_overlay_trace_finding("overlay_safe_area_failed", index))
        if str(raw.get("collision_check") or "").strip().lower() == "failed":
            findings.append(_overlay_trace_finding("overlay_collision_detected", index))
        font_size = _optional_float(raw.get("font_size"))
        if font_size is not None and font_size < min_font:
            findings.append(
                _overlay_trace_finding(
                    "overlay_readability_failed",
                    index,
                    font_size=font_size,
                    minimum_font_size=min_font,
                )
            )

        start = _optional_float(
            raw.get("visible_start_seconds") or raw.get("effective_visible_start_seconds")
        )
        end = _optional_float(
            raw.get("visible_end_seconds") or raw.get("effective_visible_end_seconds")
        )
        if start is None:
            start = _optional_float(raw.get("start_seconds"))
        if end is None:
            end = _optional_float(raw.get("end_seconds"))
        if start is None or end is None:
            continue
        intervals.append((index, start, end))
        if duration is not None and end > duration + 0.05:
            findings.append(_overlay_trace_finding("overlay_exceeds_video_duration", index))
        visible_duration = max(0.0, end - start)
        minimum_duration = 0.5
        if rendered_text and visible_duration + 1e-6 < minimum_duration:
            findings.append(
                _overlay_trace_finding(
                    "overlay_readability_failed",
                    index,
                    visible_duration_seconds=round(visible_duration, 3),
                    minimum_duration_seconds=round(minimum_duration, 3),
                )
            )

    for left in range(len(intervals)):
        idx_a, start_a, end_a = intervals[left]
        for right in range(left + 1, len(intervals)):
            idx_b, start_b, end_b = intervals[right]
            if max(start_a, start_b) < min(end_a, end_b) - 0.05:
                findings.append(
                    _overlay_trace_finding(
                        "overlay_collision_detected",
                        idx_a,
                        other_index=idx_b,
                    )
                )

    if findings:
        return QAResult(
            gate_name="package_overlay_render_trace",
            verdict=QAVerdict.FAIL,
            message="Overlay render trace validation failed.",
            details={"findings": findings},
        )
    return QAResult(
        gate_name="package_overlay_render_trace",
        verdict=QAVerdict.PASS,
        message="Overlay render trace validation passed.",
        details={"findings": []},
    )


def validate_package_media_timeline(package_payload: Mapping[str, Any] | object) -> QAResult:
    """Validate inline timeline trace checks exposed by the package payload."""

    if not isinstance(package_payload, Mapping):
        return QAResult(
            gate_name="package_media_timeline",
            verdict=QAVerdict.FAIL,
            message="Package payload must be a JSON object for media timeline QA.",
            details={"findings": [{"code": "media_timeline_missing", "severity": "fail"}]},
        )
    trace = package_payload.get("timeline_render_trace")
    if not isinstance(trace, Mapping):
        return QAResult(
            gate_name="package_media_timeline",
            verdict=QAVerdict.FAIL,
            message="Package payload is missing timeline_render_trace.",
            details={"findings": [{"code": "media_timeline_missing", "severity": "fail"}]},
        )
    checks = trace.get("checks")
    if not isinstance(checks, Mapping):
        return QAResult(
            gate_name="package_media_timeline",
            verdict=QAVerdict.FAIL,
            message="Timeline render trace is missing validation checks.",
            details={"findings": [{"code": "media_timeline_missing", "severity": "fail"}]},
        )

    findings: list[dict[str, Any]] = []
    for check_name, raw_check in checks.items():
        if not isinstance(raw_check, Mapping) or raw_check.get("passed") is not False:
            continue
        code = raw_check.get("code")
        findings.append(
            {
                "code": str(code or check_name),
                "severity": "fail",
                "message": str(raw_check.get("message") or f"{check_name} failed."),
            }
        )
    if findings:
        return QAResult(
            gate_name="package_media_timeline",
            verdict=QAVerdict.FAIL,
            message="Timeline validation failed.",
            details={"findings": findings},
        )
    return QAResult(
        gate_name="package_media_timeline",
        verdict=QAVerdict.PASS,
        message="Timeline validation checks passed.",
        details={"findings": []},
    )


def validate_package_completeness(package_payload: Mapping[str, Any] | object) -> QAResult:
    """Validate the required package artifacts and any manifest checksum coverage."""

    if not isinstance(package_payload, Mapping):
        error = "Package payload must be a JSON object."
        return QAResult(
            gate_name="package_completeness",
            verdict=QAVerdict.FAIL,
            message=error,
            details={"errors": [error]},
        )

    errors: list[str] = []
    details: dict[str, Any] = {}

    raw_artifacts = package_payload.get("artifacts")
    if not isinstance(raw_artifacts, list):
        error = "Package payload must include an artifacts list."
        return QAResult(
            gate_name="package_completeness",
            verdict=QAVerdict.FAIL,
            message=error,
            details={"errors": [error]},
        )

    artifact_index: dict[str, Mapping[str, Any]] = {}
    duplicate_names: list[str] = []
    for artifact in raw_artifacts:
        if not isinstance(artifact, Mapping):
            errors.append("Package artifacts list must only contain objects.")
            continue
        raw_name = str(artifact.get("name", "")).strip()
        if not raw_name:
            errors.append("Package artifact entries must include a non-blank name.")
            continue
        if raw_name in artifact_index:
            duplicate_names.append(raw_name)
            continue
        artifact_index[raw_name] = artifact

    if duplicate_names:
        joined_duplicates = ", ".join(sorted(duplicate_names))
        errors.append(f"Package artifacts list contains duplicate entries: {joined_duplicates}.")

    missing_artifacts: list[str] = []
    for artifact_name, expected_filename in _REQUIRED_PACKAGE_ARTIFACTS:
        artifact = artifact_index.get(artifact_name)
        if artifact is None:
            missing_artifacts.append(expected_filename)
            continue
        actual_filename = _artifact_filename(artifact)
        if actual_filename != expected_filename:
            errors.append(
                f"Required package file {expected_filename} is missing or mislabeled; "
                f"artifact {artifact_name} points to {actual_filename or 'nothing'}."
            )

    if missing_artifacts:
        details["missing_files"] = list(missing_artifacts)
        errors.append(
            "Package is missing required files: " + ", ".join(sorted(missing_artifacts)) + "."
        )

    manifest_check = _validate_manifest(package_payload, artifact_index)
    if not manifest_check.passed:
        errors.append(manifest_check.message)
    details.update(manifest_check.details)

    if errors:
        details["errors"] = list(errors)
        return QAResult(
            gate_name="package_completeness",
            verdict=QAVerdict.FAIL,
            message=errors[0],
            details=details,
        )

    return QAResult(
        gate_name="package_completeness",
        verdict=QAVerdict.PASS,
        message="Package includes the required files and manifest checksums match.",
        details=details,
    )


def _artifact_index(value: object) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, list):
        return {}
    index: dict[str, Mapping[str, Any]] = {}
    for artifact in value:
        if not isinstance(artifact, Mapping):
            continue
        name = str(artifact.get("name", "")).strip()
        if name and name not in index:
            index[name] = artifact
    return index


def _validate_manifest(
    package_payload: Mapping[str, Any],
    artifact_index: Mapping[str, Mapping[str, Any]],
) -> QAResult:
    manifest = package_payload.get("manifest")
    if manifest is None:
        return QAResult(
            gate_name="package_manifest",
            verdict=QAVerdict.SKIP,
            message="Package manifest not present; checksum comparison skipped.",
        )
    if not isinstance(manifest, Mapping):
        error = "Package manifest must be a JSON object when present."
        return QAResult(
            gate_name="package_manifest",
            verdict=QAVerdict.FAIL,
            message=error,
            details={"errors": [error]},
        )
    if manifest.get("complete") is False:
        error = "Package manifest marks the package as incomplete."
        return QAResult(
            gate_name="package_manifest",
            verdict=QAVerdict.FAIL,
            message=error,
            details={"errors": [error]},
        )

    manifest_artifacts_raw = manifest.get("artifacts")
    if not isinstance(manifest_artifacts_raw, list):
        error = "Package manifest must include an artifacts list when present."
        return QAResult(
            gate_name="package_manifest",
            verdict=QAVerdict.FAIL,
            message=error,
            details={"errors": [error]},
        )

    manifest_index: dict[str, Mapping[str, Any]] = {}
    errors: list[str] = []
    checksum_mismatches: list[dict[str, str]] = []
    missing_manifest_entries: list[str] = []
    for artifact in manifest_artifacts_raw:
        if not isinstance(artifact, Mapping):
            errors.append("Package manifest artifacts must only contain objects.")
            continue
        artifact_name = str(artifact.get("name", "")).strip()
        if not artifact_name:
            errors.append("Package manifest artifact entries must include a non-blank name.")
            continue
        manifest_index[artifact_name] = artifact

    for artifact_name, expected_filename in _REQUIRED_PACKAGE_ARTIFACTS:
        artifact = artifact_index.get(artifact_name)
        manifest_artifact = manifest_index.get(artifact_name)
        if manifest_artifact is None:
            missing_manifest_entries.append(expected_filename)
            continue
        if _artifact_filename(manifest_artifact) not in ("", expected_filename):
            errors.append(
                f"Package manifest entry {artifact_name} points to "
                f"{_artifact_filename(manifest_artifact)} instead of {expected_filename}."
            )
        if artifact is None:
            continue
        artifact_checksum = _normalize_checksum(artifact.get("checksum_sha256"))
        manifest_checksum = _normalize_checksum(manifest_artifact.get("checksum_sha256"))
        if artifact_checksum is None or manifest_checksum is None:
            errors.append(
                f"Package manifest entry {artifact_name} must include a valid checksum_sha256."
            )
            continue
        if artifact_checksum != manifest_checksum:
            checksum_mismatches.append(
                {
                    "artifact": artifact_name,
                    "package_checksum": artifact_checksum,
                    "manifest_checksum": manifest_checksum,
                }
            )

    if missing_manifest_entries:
        errors.append(
            "Package manifest is missing required artifact entries: "
            + ", ".join(sorted(missing_manifest_entries))
            + "."
        )
    if checksum_mismatches:
        mismatch_names = ", ".join(item["artifact"] for item in checksum_mismatches)
        errors.append(f"Package manifest checksum mismatch for: {mismatch_names}.")

    details: dict[str, Any] = {}
    if missing_manifest_entries:
        details["missing_manifest_entries"] = list(missing_manifest_entries)
    if checksum_mismatches:
        details["checksum_mismatches"] = list(checksum_mismatches)
    if errors:
        details["errors"] = list(errors)
        return QAResult(
            gate_name="package_manifest",
            verdict=QAVerdict.FAIL,
            message=errors[0],
            details=details,
        )

    return QAResult(
        gate_name="package_manifest",
        verdict=QAVerdict.PASS,
        message="Package manifest matches the uploaded artifact checksums.",
    )


def _artifact_filename(artifact: Mapping[str, Any]) -> str:
    filename = str(artifact.get("filename", "")).strip()
    if filename:
        return filename
    storage_uri = str(artifact.get("storage_uri", "")).strip()
    if not storage_uri:
        return ""
    parsed = urlparse(storage_uri)
    path = parsed.path if parsed.scheme else storage_uri
    candidate = path.rsplit("/", maxsplit=1)[-1]
    return candidate.strip()


def _normalize_checksum(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized.startswith("sha256:"):
        normalized = normalized[7:]
    if len(normalized) != 64 or any(character not in _HEX_DIGITS for character in normalized):
        return None
    return f"sha256:{normalized}"


def _mapping_get(value: object, key: str) -> object:
    if isinstance(value, Mapping):
        return value.get(key)
    return None


def _requires_layered_output_check(package_payload: Mapping[str, Any]) -> bool:
    return any(
        _has_payload(package_payload.get(key))
        for key in (
            "composition_manifest",
            "layered_composition",
            "layered_output",
            "final_video_metadata",
        )
    )


def _has_payload(value: Any) -> bool:
    if isinstance(value, Mapping):
        return bool(value)
    return value not in (None, "")


def _layered_output_metadata(package_payload: Mapping[str, Any]) -> Mapping[str, Any]:
    for key in ("layered_output", "final_video_metadata", "media_metadata"):
        value = package_payload.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _first_stream(metadata: Mapping[str, Any], codec_type: str) -> Mapping[str, Any]:
    streams = metadata.get("streams")
    if not isinstance(streams, list):
        return {}
    for stream in streams:
        if isinstance(stream, Mapping) and stream.get("codec_type") == codec_type:
            return stream
    return {}


def _expected_package_duration(package_payload: Mapping[str, Any]) -> float | None:
    return _optional_float(
        package_payload.get("duration_seconds")
        or _mapping_get(package_payload.get("timeline"), "duration_seconds")
        or _mapping_get(package_payload.get("timeline_render_trace"), "final_render_duration_seconds")
        or _mapping_get(package_payload.get("timeline_render_trace"), "duration_seconds")
        or _mapping_get(package_payload.get("overlay_render_trace"), "clip_duration_seconds")
    )


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _overlay_trace_finding(code: str, index: int, **details: Any) -> dict[str, Any]:
    return {
        "code": code,
        "severity": "fail",
        "index": index,
        **details,
    }


def _finding(code: str, **details: Any) -> dict[str, Any]:
    return {
        "code": code,
        "severity": "fail",
        **details,
    }


def _provenance_payload(package_payload: Mapping[str, Any] | object) -> Mapping[str, Any] | object:
    if not isinstance(package_payload, Mapping):
        return package_payload
    raw_provenance: object = package_payload.get("provenance", {})
    return raw_provenance


__all__ = [
    "PackageQAResult",
    "PackageQualityAssuranceError",
    "evaluate_package",
    "validate_layered_output_format",
    "validate_package_completeness",
    "validate_package_media_timeline",
    "validate_package_overlay_render_trace",
    "validate_package_script_semantics",
]
