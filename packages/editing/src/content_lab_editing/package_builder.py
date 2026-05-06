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
    COMPOSITION_MANIFEST_FILENAME,
    COVER_IMAGE_FILENAME,
    CREATIVE_TRACE_FILENAME,
    FINAL_VIDEO_FILENAME,
    OVERLAY_RENDER_TRACE_FILENAME,
    PACKAGE_MANIFEST_FILENAME,
    POSTING_PLAN_FILENAME,
    PROVENANCE_FILENAME,
    TIMELINE_FILENAME,
    TIMELINE_RENDER_TRACE_FILENAME,
    CanonicalStorageLayout,
    S3StorageClient,
)
from content_lab_storage.checksums import checksum_file
from content_lab_storage.reel_packages import (
    REQUIRED_REEL_PACKAGE_ARTIFACT_NAMES,
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
    provenance: dict[str, Any]

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
    creative_trace: Mapping[str, Any] | None = None,
    overlay_render_trace: Mapping[str, Any] | None = None,
    timeline: Mapping[str, Any] | None = None,
    timeline_render_trace: Mapping[str, Any] | None = None,
    composition_manifest: Mapping[str, Any] | None = None,
    temp_root: str | Path | None = None,
    include_manifest: bool = True,
    editing_metadata: Mapping[str, Any] | None = None,
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
    if composition_manifest is not None:
        _write_json(package_directory / COMPOSITION_MANIFEST_FILENAME, composition_manifest)
    enriched_provenance = _enrich_provenance(
        provenance,
        reel_id=normalized_reel_id,
        package_directory=package_directory,
        composition_manifest=composition_manifest,
    )
    _write_json(package_directory / PROVENANCE_FILENAME, enriched_provenance)
    if creative_trace is not None:
        _write_json(package_directory / CREATIVE_TRACE_FILENAME, creative_trace)
    if overlay_render_trace is None:
        raise ValueError("overlay_render_trace is required for production-safe overlay QA")
    _write_json(package_directory / OVERLAY_RENDER_TRACE_FILENAME, overlay_render_trace)
    if timeline is None:
        raise ValueError("timeline is required for MED-001 package output")
    if timeline_render_trace is None:
        raise ValueError("timeline_render_trace is required for MED-007 package output")
    _write_json(package_directory / TIMELINE_FILENAME, timeline)
    _write_json(package_directory / TIMELINE_RENDER_TRACE_FILENAME, timeline_render_trace)

    manifest_payload: dict[str, Any] | None = None
    if include_manifest:
        manifest_payload = _build_manifest(
            reel_id=normalized_reel_id,
            package_directory=package_directory,
            editing_metadata=editing_metadata,
        )
        enriched_provenance = _enrich_provenance(
            enriched_provenance,
            reel_id=normalized_reel_id,
            package_directory=package_directory,
            composition_manifest=composition_manifest,
            package_artifacts=manifest_payload["artifacts"],
        )
        _write_json(package_directory / PROVENANCE_FILENAME, enriched_provenance)
        manifest_payload = _build_manifest(
            reel_id=normalized_reel_id,
            package_directory=package_directory,
            editing_metadata=editing_metadata,
        )
        _write_json(package_directory / PACKAGE_MANIFEST_FILENAME, manifest_payload)

    return LocalReelPackage(
        reel_id=normalized_reel_id,
        directory=package_directory,
        manifest=manifest_payload,
        provenance=enriched_provenance,
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
    creative_trace: Mapping[str, Any] | None = None,
    overlay_render_trace: Mapping[str, Any] | None = None,
    timeline: Mapping[str, Any] | None = None,
    timeline_render_trace: Mapping[str, Any] | None = None,
    composition_manifest: Mapping[str, Any] | None = None,
    temp_root: str | Path | None = None,
    include_manifest: bool = True,
    upload_metadata: Mapping[str, str] | None = None,
    editing_metadata: Mapping[str, Any] | None = None,
) -> BuiltReelPackage:
    """Build the canonical package locally and upload it to object storage."""

    local_package = build_package_directory(
        reel_id=reel_id,
        final_video_path=final_video_path,
        cover_path=cover_path,
        caption_variants=caption_variants,
        posting_plan=posting_plan,
        provenance=provenance,
        creative_trace=creative_trace,
        overlay_render_trace=overlay_render_trace,
        timeline=timeline,
        timeline_render_trace=timeline_render_trace,
        composition_manifest=composition_manifest,
        temp_root=temp_root,
        include_manifest=include_manifest,
        editing_metadata=editing_metadata,
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
            provenance=local_package.provenance,
            creative_trace=creative_trace,
            caption_variants=caption_variants,
            overlay_render_trace=overlay_render_trace,
            timeline=timeline,
            timeline_render_trace=timeline_render_trace,
            composition_manifest=composition_manifest,
        ),
    )


def _build_manifest(
    *,
    reel_id: str,
    package_directory: Path,
    editing_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
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
        _manifest_artifact(
            name="timeline",
            filename=TIMELINE_FILENAME,
            package_directory=package_directory,
            content_type="application/json",
            kind="json",
        ),
        _manifest_artifact(
            name="timeline_render_trace",
            filename=TIMELINE_RENDER_TRACE_FILENAME,
            package_directory=package_directory,
            content_type="application/json",
            kind="json",
        ),
        _manifest_artifact(
            name="overlay_render_trace",
            filename=OVERLAY_RENDER_TRACE_FILENAME,
            package_directory=package_directory,
            content_type="application/json",
            kind="json",
        ),
    ]
    creative_trace_path = package_directory / CREATIVE_TRACE_FILENAME
    if creative_trace_path.exists() and creative_trace_path.is_file():
        artifacts.append(
            _manifest_artifact(
                name="creative_trace",
                filename=CREATIVE_TRACE_FILENAME,
                package_directory=package_directory,
                content_type="application/json",
                kind="json",
            )
        )
    composition_manifest_path = package_directory / COMPOSITION_MANIFEST_FILENAME
    if composition_manifest_path.exists() and composition_manifest_path.is_file():
        artifacts.append(
            _manifest_artifact(
                name="composition_manifest",
                filename=COMPOSITION_MANIFEST_FILENAME,
                package_directory=package_directory,
                content_type="application/json",
                kind="json",
            )
        )
    assert_reel_package_complete(artifacts)
    payload: dict[str, Any] = {
        "version": _MANIFEST_VERSION,
        "reel_id": reel_id,
        "artifact_count": len(artifacts),
        "required_artifacts": [
            artifact["name"]
            for artifact in artifacts
            if artifact["name"] in REQUIRED_REEL_PACKAGE_ARTIFACT_NAMES
        ],
        "complete": True,
        "artifacts": artifacts,
    }
    if editing_metadata:
        payload["editing"] = dict(editing_metadata)
    return payload


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


def _enrich_provenance(
    provenance: Mapping[str, Any],
    *,
    reel_id: str,
    package_directory: Path,
    composition_manifest: Mapping[str, Any] | None,
    package_artifacts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    enriched = dict(provenance)
    enriched.setdefault("reel_id", reel_id)

    composition_manifest_path = package_directory / COMPOSITION_MANIFEST_FILENAME
    if composition_manifest is not None and composition_manifest_path.exists():
        enriched["composition_manifest_hash"] = checksum_file(
            composition_manifest_path
        ).content_hash
        enriched.setdefault("transforms", _composition_transforms(composition_manifest))

    assets = enriched.get("assets")
    if isinstance(assets, list):
        enriched.setdefault("source_assets", _asset_subset(assets, derived=False))
        enriched.setdefault("derived_assets", _asset_subset(assets, derived=True))
        final_render_asset_id = _final_render_asset_id(assets)
        if final_render_asset_id is not None:
            enriched.setdefault("final_render_asset_id", final_render_asset_id)

    if package_artifacts:
        enriched["package_artifacts"] = [
            _package_artifact_provenance(artifact) for artifact in package_artifacts
        ]
    return enriched


def _composition_transforms(composition_manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    transforms: list[dict[str, Any]] = []
    for layer in _composition_layers(composition_manifest):
        if not isinstance(layer, Mapping):
            continue
        transforms.append(
            {
                key: value
                for key, value in {
                    "asset_id": _optional_text(layer.get("asset_id")),
                    "layer_id": _optional_text(layer.get("layer_id")),
                    "role": _optional_text(layer.get("asset_kind")),
                    "transform_recipe": _layer_transform_recipe(layer),
                    "transform_version": "composition_manifest.v1",
                    "start_time": layer.get("start_time"),
                    "end_time": layer.get("end_time"),
                    "z_index": layer.get("z_index"),
                }.items()
                if value is not None
            }
        )
    return transforms


def _composition_layers(composition_manifest: Mapping[str, Any]) -> list[Any]:
    layers: list[Any] = []
    background = composition_manifest.get("background_layer")
    if background is not None:
        layers.append(background)
    for key in ("layers", "audio_layers"):
        value = composition_manifest.get(key)
        if isinstance(value, list):
            layers.extend(value)
    return layers


def _layer_transform_recipe(layer: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "x",
        "y",
        "width",
        "height",
        "scale",
        "opacity",
        "crop",
        "rotation",
        "mask_mode",
        "blend_mode",
        "animation",
        "motion_transform",
        "safe_area_constraints",
    )
    return {key: layer[key] for key in keys if key in layer and layer[key] is not None}


def _asset_subset(assets: list[Any], *, derived: bool) -> list[dict[str, Any]]:
    return [
        dict(asset)
        for asset in assets
        if isinstance(asset, Mapping) and _is_derived(asset) is derived
    ]


def _is_derived(asset: Mapping[str, Any]) -> bool:
    role = _optional_text(asset.get("role")) or ""
    stage = _optional_text(asset.get("stage")) or ""
    source_type = _optional_text(asset.get("source_type") or asset.get("source")) or ""
    return (
        stage.lower() in {"derived", "output", "render"}
        or source_type.lower() in {"derived", "package_output"}
        or role.lower() in {"final_video", "final_render", "cover"}
        or _optional_text(asset.get("derived_from_asset_id")) is not None
    )


def _final_render_asset_id(assets: list[Any]) -> str | None:
    for asset in assets:
        if not isinstance(asset, Mapping):
            continue
        role = (_optional_text(asset.get("role")) or "").lower()
        asset_id = _optional_text(asset.get("asset_id"))
        if role in {"final_video", "final_render"} and asset_id is not None:
            return asset_id
    return None


def _package_artifact_provenance(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "name": artifact.get("name"),
            "filename": artifact.get("filename"),
            "storage_uri": artifact.get("storage_uri"),
            "checksum_sha256": artifact.get("checksum_sha256"),
            "content_type": artifact.get("content_type"),
            "kind": artifact.get("kind"),
            "size_bytes": artifact.get("size_bytes"),
        }.items()
        if value is not None
    }


def _caption_variants_for_package_payload(
    value: str | Sequence[str] | Sequence[Mapping[str, Any]],
) -> str | list[Any]:
    """Return a JSON-serializable copy of caption variants for downstream QA."""

    if isinstance(value, str):
        return value
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        rows: list[Any] = []
        for item in value:
            if isinstance(item, Mapping):
                rows.append({str(key): item[key] for key in item})
            else:
                rows.append(str(item))
        return rows
    return str(value)


def _package_payload(
    *,
    reel_id: str,
    stored_package: StoredReelPackage,
    manifest: Mapping[str, Any] | None,
    provenance: Mapping[str, Any],
    creative_trace: Mapping[str, Any] | None,
    caption_variants: str | Sequence[str] | Sequence[Mapping[str, Any]],
    overlay_render_trace: Mapping[str, Any] | None,
    timeline: Mapping[str, Any] | None,
    timeline_render_trace: Mapping[str, Any] | None,
    composition_manifest: Mapping[str, Any] | None,
) -> dict[str, Any]:
    artifacts = [artifact.as_payload() for artifact in stored_package.artifacts]
    provenance_artifact = stored_package.artifact_by_name("provenance")
    composition_manifest_artifact = stored_package.artifact_by_name("composition_manifest")
    creative_trace_artifact = stored_package.artifact_by_name("creative_trace")
    overlay_trace_artifact = stored_package.artifact_by_name("overlay_render_trace")
    timeline_artifact = stored_package.artifact_by_name("timeline")
    timeline_render_trace_artifact = stored_package.artifact_by_name("timeline_render_trace")
    manifest_artifact = stored_package.artifact_by_name("package_manifest")
    return {
        "reel_id": reel_id,
        "package_root_uri": stored_package.root_uri,
        "manifest_uri": None if manifest_artifact is None else manifest_artifact.storage_uri,
        "manifest": {} if manifest is None else dict(manifest),
        "provenance_uri": None if provenance_artifact is None else provenance_artifact.storage_uri,
        "provenance": dict(provenance),
        "composition_manifest_uri": (
            None
            if composition_manifest_artifact is None
            else composition_manifest_artifact.storage_uri
        ),
        "composition_manifest": (
            {} if composition_manifest is None else dict(composition_manifest)
        ),
        "creative_trace_uri": (
            None if creative_trace_artifact is None else creative_trace_artifact.storage_uri
        ),
        "creative_trace": {} if creative_trace is None else dict(creative_trace),
        "caption_variants": _caption_variants_for_package_payload(caption_variants),
        "overlay_render_trace_uri": (
            None if overlay_trace_artifact is None else overlay_trace_artifact.storage_uri
        ),
        "overlay_render_trace": {} if overlay_render_trace is None else dict(overlay_render_trace),
        "timeline_uri": None if timeline_artifact is None else timeline_artifact.storage_uri,
        "timeline": {} if timeline is None else dict(timeline),
        "timeline_render_trace_uri": (
            None
            if timeline_render_trace_artifact is None
            else timeline_render_trace_artifact.storage_uri
        ),
        "timeline_render_trace": (
            {} if timeline_render_trace is None else dict(timeline_render_trace)
        ),
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


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).strip().split())
    return normalized or None
