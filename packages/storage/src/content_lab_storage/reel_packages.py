"""Helpers for persisting canonical ready-to-post reel packages."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from content_lab_storage.checksums import checksum_file
from content_lab_storage.client import S3StorageClient, StoredObject
from content_lab_storage.paths import (
    CAPTION_VARIANTS_FILENAME,
    COVER_IMAGE_FILENAME,
    FINAL_VIDEO_FILENAME,
    PACKAGE_MANIFEST_FILENAME,
    POSTING_PLAN_FILENAME,
    PROVENANCE_FILENAME,
    CanonicalStorageLayout,
    ReelPackageRefs,
)
from content_lab_storage.refs import StorageRef

REQUIRED_REEL_PACKAGE_ARTIFACT_NAMES = frozenset(
    {
        "final_video",
        "cover",
        "caption_variants",
        "posting_plan",
        "provenance",
    }
)


@dataclass(frozen=True, slots=True)
class ReelPackageArtifact:
    """Uploaded reel-package artifact metadata."""

    name: str
    filename: str
    ref: StorageRef
    kind: str | None
    content_type: str | None
    size_bytes: int | None
    checksum_sha256: str | None
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def storage_uri(self) -> str:
        return self.ref.uri

    def as_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "filename": self.filename,
            "storage_uri": self.storage_uri,
            "kind": self.kind,
            "content_type": self.content_type,
        }
        if self.size_bytes is not None:
            payload["size_bytes"] = self.size_bytes
        if self.checksum_sha256 is not None:
            payload["checksum_sha256"] = self.checksum_sha256
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True, slots=True)
class StoredReelPackage:
    """Canonical reel-package upload result."""

    root: StorageRef
    artifacts: tuple[ReelPackageArtifact, ...]

    @property
    def root_uri(self) -> str:
        return self.root.uri

    @property
    def artifact_uris(self) -> dict[str, str]:
        return {artifact.name: artifact.storage_uri for artifact in self.artifacts}

    def artifact_by_name(self, name: str) -> ReelPackageArtifact | None:
        normalized_name = name.strip().lower()
        return next(
            (
                artifact
                for artifact in self.artifacts
                if artifact.name.strip().lower() == normalized_name
            ),
            None,
        )


@dataclass(frozen=True, slots=True)
class _ArtifactSpec:
    name: str
    filename: str
    ref: StorageRef
    kind: str | None
    content_type: str | None


def expected_reel_package_filenames(*, include_manifest: bool = True) -> tuple[str, ...]:
    """Return the canonical filenames expected in a ready-to-post package directory."""

    filenames = (
        FINAL_VIDEO_FILENAME,
        COVER_IMAGE_FILENAME,
        CAPTION_VARIANTS_FILENAME,
        POSTING_PLAN_FILENAME,
        PROVENANCE_FILENAME,
    )
    if include_manifest:
        return (*filenames, PACKAGE_MANIFEST_FILENAME)
    return filenames


def resolve_reel_package_directory(
    directory: str | Path,
    *,
    include_manifest: bool = True,
) -> dict[str, Path]:
    """Validate a local package directory and return the canonical artifact paths."""

    resolved_directory = Path(directory)
    if not resolved_directory.exists():
        raise FileNotFoundError(f"Package directory {resolved_directory} does not exist")
    if not resolved_directory.is_dir():
        raise ValueError(f"Package directory {resolved_directory} must be a directory")

    artifact_paths = {
        filename: resolved_directory / filename
        for filename in expected_reel_package_filenames(include_manifest=include_manifest)
    }
    missing = [
        filename
        for filename, path in artifact_paths.items()
        if not path.exists() or not path.is_file()
    ]
    if missing:
        joined = ", ".join(sorted(missing))
        raise ValueError(f"Package directory is missing required artifacts: {joined}")
    return artifact_paths


def assert_reel_package_complete(
    artifacts: Iterable[ReelPackageArtifact | Mapping[str, Any]],
) -> None:
    """Raise if the canonical five artifact slots are not present."""

    names: set[str] = set()
    for artifact in artifacts:
        if isinstance(artifact, ReelPackageArtifact):
            names.add(artifact.name)
            continue
        raw_name = artifact.get("name")
        if raw_name is not None:
            names.add(str(raw_name).strip())

    missing = sorted(REQUIRED_REEL_PACKAGE_ARTIFACT_NAMES.difference(names))
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"Reel package is incomplete; missing required artifacts: {joined}")


def persist_reel_package_directory(
    *,
    client: S3StorageClient,
    layout: CanonicalStorageLayout,
    reel_id: UUID | str,
    directory: str | Path,
    include_manifest: bool = True,
    metadata: Mapping[str, str] | None = None,
) -> StoredReelPackage:
    """Upload a local ready-to-post package directory to canonical object storage."""

    artifact_paths = resolve_reel_package_directory(directory, include_manifest=include_manifest)
    package_refs = layout.reel_package(reel_id)
    base_metadata = dict(metadata or {})
    uploaded: list[ReelPackageArtifact] = []

    for spec in _artifact_specs(package_refs, include_manifest=include_manifest):
        path = artifact_paths[spec.filename]
        checksums = checksum_file(path)
        object_metadata = {
            **base_metadata,
            "artifact-name": spec.name,
            "reel-id": str(reel_id),
        }
        stored = client.put_object(
            ref=spec.ref,
            data=path.read_bytes(),
            content_type=spec.content_type,
            metadata=object_metadata,
            checksum_sha256=checksums.content_hash,
        )
        uploaded.append(
            _uploaded_artifact(
                spec=spec,
                stored=stored,
                checksum_sha256=checksums.content_hash,
            )
        )

    assert_reel_package_complete(uploaded)
    return StoredReelPackage(root=package_refs.root, artifacts=tuple(uploaded))


def _artifact_specs(
    package_refs: ReelPackageRefs,
    *,
    include_manifest: bool,
) -> tuple[_ArtifactSpec, ...]:
    specs = (
        _ArtifactSpec(
            name="final_video",
            filename=FINAL_VIDEO_FILENAME,
            ref=package_refs.final_video,
            kind="video",
            content_type="video/mp4",
        ),
        _ArtifactSpec(
            name="cover",
            filename=COVER_IMAGE_FILENAME,
            ref=package_refs.cover,
            kind="image",
            content_type="image/png",
        ),
        _ArtifactSpec(
            name="caption_variants",
            filename=CAPTION_VARIANTS_FILENAME,
            ref=package_refs.caption_variants,
            kind="text",
            content_type="text/plain",
        ),
        _ArtifactSpec(
            name="posting_plan",
            filename=POSTING_PLAN_FILENAME,
            ref=package_refs.posting_plan,
            kind="json",
            content_type="application/json",
        ),
        _ArtifactSpec(
            name="provenance",
            filename=PROVENANCE_FILENAME,
            ref=package_refs.provenance,
            kind="json",
            content_type="application/json",
        ),
    )
    if include_manifest:
        return (
            *specs,
            _ArtifactSpec(
                name="package_manifest",
                filename=PACKAGE_MANIFEST_FILENAME,
                ref=package_refs.manifest,
                kind="json",
                content_type="application/json",
            ),
        )
    return specs


def _uploaded_artifact(
    *,
    spec: _ArtifactSpec,
    stored: StoredObject,
    checksum_sha256: str,
) -> ReelPackageArtifact:
    return ReelPackageArtifact(
        name=spec.name,
        filename=spec.filename,
        ref=stored.ref,
        kind=spec.kind,
        content_type=stored.content_type or spec.content_type,
        size_bytes=stored.size_bytes,
        checksum_sha256=stored.checksum_sha256 or checksum_sha256,
        metadata=dict(stored.metadata),
    )
