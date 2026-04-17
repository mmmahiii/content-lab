"""Org-scoped package metadata and signed-download routes."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.models import Org, Run
from content_lab_api.routes._storage import build_signed_download
from content_lab_api.schemas.packages import PackageArtifactOut, PackageDetailOut
from content_lab_shared.settings import Settings
from content_lab_storage import (
    CAPTION_VARIANTS_FILENAME,
    COVER_IMAGE_FILENAME,
    FINAL_VIDEO_FILENAME,
    PACKAGE_MANIFEST_FILENAME,
    POSTING_PLAN_FILENAME,
    PROVENANCE_FILENAME,
    CanonicalStorageLayout,
    StorageRef,
)

router = APIRouter(prefix="/orgs/{org_id}/packages", tags=["packages"])

_SUPPORT_ARTIFACT_NAMES = frozenset({"manifest", "package_manifest", "provenance"})
_PACKAGE_ARTIFACT_FILENAMES = {
    "final_video": FINAL_VIDEO_FILENAME,
    "cover": COVER_IMAGE_FILENAME,
    "caption_variants": CAPTION_VARIANTS_FILENAME,
    "posting_plan": POSTING_PLAN_FILENAME,
    "provenance": PROVENANCE_FILENAME,
    "manifest": PACKAGE_MANIFEST_FILENAME,
    "package_manifest": PACKAGE_MANIFEST_FILENAME,
}


def _get_org_or_404(db: Session, org_id: uuid.UUID) -> Org:
    org = db.get(Org, org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Org not found")
    return org


def _get_run_or_404(db: Session, *, org_id: uuid.UUID, run_id: uuid.UUID) -> Run:
    run = db.query(Run).filter(Run.org_id == org_id, Run.id == run_id).one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Package not found")
    return run


def _coerce_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _extract_package_payload(run: Run) -> dict[str, Any]:
    payload = _coerce_mapping(run.output_payload)
    nested = _coerce_mapping(payload.get("package"))
    candidate = nested or payload
    if not any(
        key in candidate
        for key in ("artifacts", "manifest", "manifest_uri", "package_root_uri", "provenance")
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Package not found")
    return candidate


def _normalized_artifacts(package_payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_artifacts = package_payload.get("artifacts")
    if raw_artifacts is None:
        raw_artifacts = _coerce_mapping(package_payload.get("manifest")).get("artifacts", [])

    artifacts: list[dict[str, Any]] = []
    if isinstance(raw_artifacts, dict):
        iterable = [
            {"name": name, **_coerce_mapping(value)} for name, value in raw_artifacts.items()
        ]
    elif isinstance(raw_artifacts, list):
        iterable = [_coerce_mapping(item) for item in raw_artifacts]
    else:
        iterable = []

    for item in iterable:
        name = str(item.get("name", "")).strip()
        storage_uri = str(item.get("storage_uri", "")).strip()
        if not name or not storage_uri:
            continue
        artifacts.append(
            {
                "name": name,
                "storage_uri": storage_uri,
                "kind": item.get("kind"),
                "content_type": item.get("content_type"),
                "metadata": {
                    key: value
                    for key, value in item.items()
                    if key not in {"name", "storage_uri", "kind", "content_type"}
                },
            }
        )
    return artifacts


def _artifact_uri_by_name(artifacts: list[dict[str, Any]], *names: str) -> str | None:
    normalized_names = {name.lower() for name in names}
    for artifact in artifacts:
        if artifact["name"].strip().lower() in normalized_names:
            return str(artifact["storage_uri"])
    return None


def _optional_uuid(value: Any) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def _package_layout() -> CanonicalStorageLayout:
    return CanonicalStorageLayout(bucket=Settings().minio_bucket)


def _invalid_package_metadata(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Package metadata is invalid: {detail}",
    )


def _validate_package_root_uri(package_root_uri: str, *, reel_id: uuid.UUID) -> str:
    expected_ref = _package_layout().reel_package_prefix(reel_id)
    try:
        ref = StorageRef.from_uri(package_root_uri)
    except ValueError as exc:
        raise _invalid_package_metadata(
            "package_root_uri must be a canonical s3:// package path"
        ) from exc
    if ref.uri != expected_ref.uri:
        raise _invalid_package_metadata("package_root_uri is outside the canonical package scope")
    return str(ref.uri)


def _validate_package_object_uri(
    storage_uri: str,
    *,
    reel_id: uuid.UUID,
    artifact_name: str | None = None,
) -> str:
    layout = _package_layout()
    expected_root = layout.reel_package_prefix(reel_id)
    try:
        ref = StorageRef.from_uri(storage_uri)
    except ValueError as exc:
        raise _invalid_package_metadata(
            "package artifact URIs must be canonical s3:// object refs"
        ) from exc

    if ref.bucket != expected_root.bucket or not ref.key.startswith(f"{expected_root.key}/"):
        raise _invalid_package_metadata(
            "package artifact URIs are outside the canonical package scope"
        )

    if artifact_name is None:
        return str(ref.uri)

    expected_filename = _PACKAGE_ARTIFACT_FILENAMES.get(artifact_name.strip().lower())
    if expected_filename is None:
        return str(ref.uri)

    expected_ref = layout.reel_package_object(reel_id, expected_filename)
    if ref.uri != expected_ref.uri:
        raise _invalid_package_metadata(
            f"{artifact_name} must resolve to its canonical package object"
        )
    return str(ref.uri)


@router.get("/{run_id}", response_model=PackageDetailOut)
def get_package(
    org_id: uuid.UUID,
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> PackageDetailOut:
    _get_org_or_404(db, org_id)
    run = _get_run_or_404(db, org_id=org_id, run_id=run_id)
    package_payload = _extract_package_payload(run)
    artifacts = _normalized_artifacts(package_payload)
    manifest_metadata = _coerce_mapping(package_payload.get("manifest"))
    provenance = _coerce_mapping(package_payload.get("provenance"))
    manifest_uri = (
        package_payload.get("manifest_uri")
        or manifest_metadata.get("storage_uri")
        or _artifact_uri_by_name(artifacts, "manifest", "package_manifest")
    )
    provenance_uri = (
        package_payload.get("provenance_uri")
        or provenance.get("storage_uri")
        or _artifact_uri_by_name(artifacts, "provenance")
    )

    reel_uuid = _optional_uuid(
        package_payload.get("reel_id") or _coerce_mapping(run.input_params).get("reel_id")
    )
    has_package_uris = any(
        value is not None and str(value).strip() != ""
        for value in (
            package_payload.get("package_root_uri"),
            manifest_uri,
            provenance_uri,
            *[artifact["storage_uri"] for artifact in artifacts],
        )
    )
    if has_package_uris and reel_uuid is None:
        raise _invalid_package_metadata("reel_id is required to validate package storage scope")

    validated_package_root_uri = (
        None
        if package_payload.get("package_root_uri") is None or reel_uuid is None
        else _validate_package_root_uri(str(package_payload["package_root_uri"]), reel_id=reel_uuid)
    )
    validated_manifest_uri = (
        None
        if manifest_uri is None or reel_uuid is None
        else _validate_package_object_uri(
            str(manifest_uri), reel_id=reel_uuid, artifact_name="package_manifest"
        )
    )
    validated_provenance_uri = (
        None
        if provenance_uri is None or reel_uuid is None
        else _validate_package_object_uri(
            str(provenance_uri), reel_id=reel_uuid, artifact_name="provenance"
        )
    )

    return PackageDetailOut(
        run_id=run.id,
        org_id=run.org_id,
        status=run.status,
        workflow_key=run.workflow_key,
        reel_id=reel_uuid,
        package_root_uri=validated_package_root_uri,
        manifest_uri=validated_manifest_uri,
        manifest_metadata=manifest_metadata,
        manifest_download=(
            None
            if validated_manifest_uri is None
            else build_signed_download(storage_uri=validated_manifest_uri)
        ),
        provenance=provenance,
        provenance_uri=validated_provenance_uri,
        provenance_download=(
            None
            if validated_provenance_uri is None
            else build_signed_download(storage_uri=validated_provenance_uri)
        ),
        artifacts=[
            PackageArtifactOut(
                name=artifact["name"],
                storage_uri=(
                    artifact["storage_uri"]
                    if reel_uuid is None
                    else _validate_package_object_uri(
                        artifact["storage_uri"],
                        reel_id=reel_uuid,
                        artifact_name=artifact["name"],
                    )
                ),
                kind=artifact["kind"],
                content_type=artifact["content_type"],
                metadata=artifact["metadata"],
                download=build_signed_download(
                    storage_uri=(
                        artifact["storage_uri"]
                        if reel_uuid is None
                        else _validate_package_object_uri(
                            artifact["storage_uri"],
                            reel_id=reel_uuid,
                            artifact_name=artifact["name"],
                        )
                    )
                ),
            )
            for artifact in artifacts
            if artifact["name"].strip().lower() not in _SUPPORT_ARTIFACT_NAMES
        ],
        created_at=run.created_at,
        updated_at=run.updated_at,
    )
