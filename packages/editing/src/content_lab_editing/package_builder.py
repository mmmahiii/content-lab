"""Build and persist canonical ready-to-post reel packages."""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from content_lab_storage import (
    CAPTION_VARIANTS_FILENAME,
    COVER_IMAGE_FILENAME,
    FINAL_VIDEO_FILENAME,
    PACKAGE_MANIFEST_FILENAME,
    POSTING_PLAN_FILENAME,
    PROVENANCE_FILENAME,
    CanonicalStorageLayout,
    S3StorageClient,
)
from content_lab_storage.checksums import checksum_file
from content_lab_storage.reel_packages import (
    StoredReelPackage,
    assert_reel_package_complete,
    persist_reel_package_directory,
)

_MANIFEST_VERSION = 1


@dataclass(frozen=True, slots=True)
class LocalReelPackage:
    """A fully materialized local package directory."""

    reel_id: str
    directory: Path
    manifest: dict[str, Any] | None

    @property
    def package_root_uri(self) -> str:
        return self.directory.as_uri()


@dataclass(frozen=True, slots=True)
class BuiltReelPackage:
    """Combined local-build and object-storage result."""

    local_package: LocalReelPackage
    stored_package: StoredReelPackage
    package_payload: dict[str, Any]


def build_package_directory(
    *,
    reel_id: UUID | str,
    final_video_path: str | Path,
    cover_path: str | Path,
    caption_variants: str | Sequence[str] | Sequence[Mapping[str, Any]],
    posting_plan: Mapping[str, Any],
    provenance: Mapping[str, Any],
    temp_root: str | Path | None = None,
    include_manifest: bool = True,
) -> LocalReelPackage:
    """Create the canonical ready-to-post package on local temp storage."""

    normalized_reel_id = _normalize_reel_id(reel_id)
    root = Path(temp_root) if temp_root is not None else Path(tempfile.mkdtemp())
    package_directory = root / f"reel-package-{normalized_reel_id}"
    package_directory.mkdir(parents=True, exist_ok=True)

    final_video_source = _resolve_existing_file(final_video_path, field_name="final_video_path")
    cover_source = _resolve_existing_file(cover_path, field_name="cover_path")

    shutil.copyfile(final_video_source, package_directory / FINAL_VIDEO_FILENAME)
    shutil.copyfile(cover_source, package_directory / COVER_IMAGE_FILENAME)
    (package_directory / CAPTION_VARIANTS_FILENAME).write_text(
        _render_caption_variants(caption_variants),
        encoding="utf-8",
    )
    _write_json(package_directory / POSTING_PLAN_FILENAME, posting_plan)
    _write_json(package_directory / PROVENANCE_FILENAME, provenance)

    manifest_payload: dict[str, Any] | None = None
    if include_manifest:
        manifest_payload = _build_manifest(
            reel_id=normalized_reel_id,
            package_directory=package_directory,
        )
        _write_json(package_directory / PACKAGE_MANIFEST_FILENAME, manifest_payload)

    return LocalReelPackage(
        reel_id=normalized_reel_id,
        directory=package_directory,
        manifest=manifest_payload,
    )


def build_ready_to_post_package(
    *,
    client: S3StorageClient,
    layout: CanonicalStorageLayout,
    reel_id: UUID | str,
    final_video_path: str | Path,
    cover_path: str | Path,
    caption_variants: str | Sequence[str] | Sequence[Mapping[str, Any]],
    posting_plan: Mapping[str, Any],
    provenance: Mapping[str, Any],
    temp_root: str | Path | None = None,
    include_manifest: bool = True,
    upload_metadata: Mapping[str, str] | None = None,
) -> BuiltReelPackage:
    """Build the canonical package locally and upload it to object storage."""

    local_package = build_package_directory(
        reel_id=reel_id,
        final_video_path=final_video_path,
        cover_path=cover_path,
        caption_variants=caption_variants,
        posting_plan=posting_plan,
        provenance=provenance,
        temp_root=temp_root,
        include_manifest=include_manifest,
    )
    stored_package = persist_reel_package_directory(
        client=client,
        layout=layout,
        reel_id=local_package.reel_id,
        directory=local_package.directory,
        include_manifest=include_manifest,
        metadata=upload_metadata,
    )
    return BuiltReelPackage(
        local_package=local_package,
        stored_package=stored_package,
        package_payload=_package_payload(
            reel_id=local_package.reel_id,
            stored_package=stored_package,
            manifest=local_package.manifest,
            provenance=provenance,
        ),
    )


def _build_manifest(*, reel_id: str, package_directory: Path) -> dict[str, Any]:
    artifacts = [
        _manifest_artifact(
            name="final_video",
            filename=FINAL_VIDEO_FILENAME,
            package_directory=package_directory,
            content_type="video/mp4",
            kind="video",
        ),
        _manifest_artifact(
            name="cover",
            filename=COVER_IMAGE_FILENAME,
            package_directory=package_directory,
            content_type="image/png",
            kind="image",
        ),
        _manifest_artifact(
            name="caption_variants",
            filename=CAPTION_VARIANTS_FILENAME,
            package_directory=package_directory,
            content_type="text/plain",
            kind="text",
        ),
        _manifest_artifact(
            name="posting_plan",
            filename=POSTING_PLAN_FILENAME,
            package_directory=package_directory,
            content_type="application/json",
            kind="json",
        ),
        _manifest_artifact(
            name="provenance",
            filename=PROVENANCE_FILENAME,
            package_directory=package_directory,
            content_type="application/json",
            kind="json",
        ),
    ]
    assert_reel_package_complete(artifacts)
    return {
        "version": _MANIFEST_VERSION,
        "reel_id": reel_id,
        "artifact_count": len(artifacts),
        "required_artifacts": [artifact["name"] for artifact in artifacts],
        "complete": True,
        "artifacts": artifacts,
    }


def _manifest_artifact(
    *,
    name: str,
    filename: str,
    package_directory: Path,
    content_type: str,
    kind: str,
) -> dict[str, Any]:
    path = package_directory / filename
    checksums = checksum_file(path)
    return {
        "name": name,
        "filename": filename,
        "content_type": content_type,
        "kind": kind,
        "size_bytes": path.stat().st_size,
        "checksum_sha256": checksums.content_hash,
    }


def _package_payload(
    *,
    reel_id: str,
    stored_package: StoredReelPackage,
    manifest: Mapping[str, Any] | None,
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    artifacts = [artifact.as_payload() for artifact in stored_package.artifacts]
    provenance_artifact = stored_package.artifact_by_name("provenance")
    manifest_artifact = stored_package.artifact_by_name("package_manifest")
    return {
        "reel_id": reel_id,
        "package_root_uri": stored_package.root_uri,
        "manifest_uri": None if manifest_artifact is None else manifest_artifact.storage_uri,
        "manifest": {} if manifest is None else dict(manifest),
        "provenance_uri": None if provenance_artifact is None else provenance_artifact.storage_uri,
        "provenance": dict(provenance),
        "artifacts": artifacts,
    }


def _normalize_reel_id(reel_id: UUID | str) -> str:
    normalized = str(reel_id).strip()
    if not normalized:
        raise ValueError("reel_id must not be blank")
    return normalized


def _resolve_existing_file(path: str | Path, *, field_name: str) -> Path:
    resolved = Path(path)
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(f"{field_name} {resolved} does not exist")
    return resolved


def _render_caption_variants(
    value: str | Sequence[str] | Sequence[Mapping[str, Any]],
) -> str:
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            raise ValueError("caption_variants must not be blank")
        return f"{normalized}\n"

    blocks: list[str] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, Mapping):
            variant_name = (
                str(item.get("variant", f"variant_{index}")).strip() or f"variant_{index}"
            )
            text = str(item.get("text", "")).strip()
        else:
            variant_name = f"variant_{index}"
            text = str(item).strip()
        if not text:
            raise ValueError("caption_variants entries must not be blank")
        blocks.append(f"[{variant_name}]\n{text}")

    if not blocks:
        raise ValueError("caption_variants must contain at least one variant")
    return "\n\n".join(blocks) + "\n"


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
