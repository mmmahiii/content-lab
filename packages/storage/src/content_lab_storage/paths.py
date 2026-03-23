"""Canonical S3 object paths for phase-1 assets and reel packages."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from content_lab_storage.refs import StorageRef, build_key

PACKAGE_MANIFEST_FILENAME = "package_manifest.json"
PROVENANCE_FILENAME = "provenance.json"
FINAL_VIDEO_FILENAME = "final_video.mp4"
COVER_IMAGE_FILENAME = "cover.png"
CAPTION_VARIANTS_FILENAME = "caption_variants.txt"
POSTING_PLAN_FILENAME = "posting_plan.json"


def _normalize_id(value: UUID | str, *, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


@dataclass(frozen=True, slots=True)
class ReelPackageRefs:
    """Stable object refs for the canonical reel package outputs."""

    root: StorageRef
    final_video: StorageRef
    cover: StorageRef
    caption_variants: StorageRef
    posting_plan: StorageRef
    provenance: StorageRef
    manifest: StorageRef


@dataclass(frozen=True, slots=True)
class CanonicalStorageLayout:
    """Build canonical object refs for Content Lab's storage contract."""

    bucket: str

    def raw_asset_prefix(self, asset_id: UUID | str) -> StorageRef:
        return StorageRef(
            bucket=self.bucket,
            key=build_key("assets", "raw", _normalize_id(asset_id, field_name="asset_id")),
        )

    def raw_asset_object(self, asset_id: UUID | str, *segments: str) -> StorageRef:
        return StorageRef(
            bucket=self.bucket,
            key=build_key(self.raw_asset_prefix(asset_id).key, *segments),
        )

    def derived_asset_prefix(self, asset_id: UUID | str) -> StorageRef:
        return StorageRef(
            bucket=self.bucket,
            key=build_key("assets", "derived", _normalize_id(asset_id, field_name="asset_id")),
        )

    def derived_asset_object(self, asset_id: UUID | str, *segments: str) -> StorageRef:
        return StorageRef(
            bucket=self.bucket,
            key=build_key(self.derived_asset_prefix(asset_id).key, *segments),
        )

    def reel_package_prefix(self, reel_id: UUID | str) -> StorageRef:
        return StorageRef(
            bucket=self.bucket,
            key=build_key("reels", "packages", _normalize_id(reel_id, field_name="reel_id")),
        )

    def reel_package_object(self, reel_id: UUID | str, filename: str) -> StorageRef:
        return StorageRef(
            bucket=self.bucket,
            key=build_key(self.reel_package_prefix(reel_id).key, filename),
        )

    def reel_package(self, reel_id: UUID | str) -> ReelPackageRefs:
        return ReelPackageRefs(
            root=self.reel_package_prefix(reel_id),
            final_video=self.reel_package_object(reel_id, FINAL_VIDEO_FILENAME),
            cover=self.reel_package_object(reel_id, COVER_IMAGE_FILENAME),
            caption_variants=self.reel_package_object(reel_id, CAPTION_VARIANTS_FILENAME),
            posting_plan=self.reel_package_object(reel_id, POSTING_PLAN_FILENAME),
            provenance=self.reel_package_object(reel_id, PROVENANCE_FILENAME),
            manifest=self.reel_package_object(reel_id, PACKAGE_MANIFEST_FILENAME),
        )
