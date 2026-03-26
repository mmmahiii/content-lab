"""Package completeness QA for ready-to-post reel packages."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from pydantic import Field

from content_lab_core.models import DomainModel
from content_lab_core.types import QAVerdict
from content_lab_qa.gate import QAResult
from content_lab_qa.provenance import validate_package_provenance

_REQUIRED_PACKAGE_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("final_video", "final_video.mp4"),
    ("cover", "cover.png"),
    ("caption_variants", "caption_variants.txt"),
    ("posting_plan", "posting_plan.json"),
    ("provenance", "provenance.json"),
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


def evaluate_package(package_payload: Mapping[str, Any] | object) -> PackageQAResult:
    """Evaluate ready-to-post package completeness and provenance deterministically."""

    checks: list[QAResult] = [
        validate_package_completeness(package_payload),
        validate_package_provenance(_provenance_payload(package_payload)),
    ]
    errors = [check.message for check in checks if not check.passed and check.message]
    verdict = QAVerdict.PASS if not errors else QAVerdict.FAIL
    message = "Package QA passed." if not errors else errors[0]
    return PackageQAResult(verdict=verdict, message=message, errors=errors, checks=checks)


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


def _provenance_payload(package_payload: Mapping[str, Any] | object) -> Mapping[str, Any] | object:
    if not isinstance(package_payload, Mapping):
        return package_payload
    raw_provenance: object = package_payload.get("provenance", {})
    return raw_provenance


__all__ = ["PackageQAResult", "evaluate_package", "validate_package_completeness"]
