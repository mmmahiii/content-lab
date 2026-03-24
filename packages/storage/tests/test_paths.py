from __future__ import annotations

import uuid

from content_lab_storage import CanonicalStorageLayout


def test_raw_asset_paths_are_canonical() -> None:
    asset_id = uuid.uuid4()
    layout = CanonicalStorageLayout(bucket="content-lab")

    prefix = layout.raw_asset_prefix(asset_id)
    original = layout.raw_asset_object(asset_id, "original.mp4")

    assert prefix.uri == f"s3://content-lab/assets/raw/{asset_id}"
    assert original.uri == f"s3://content-lab/assets/raw/{asset_id}/original.mp4"


def test_derived_asset_paths_are_canonical() -> None:
    layout = CanonicalStorageLayout(bucket="content-lab")

    clip = layout.derived_asset_object("clip-123", "clip.mp4")

    assert clip.uri == "s3://content-lab/assets/derived/clip-123/clip.mp4"


def test_reel_package_paths_cover_all_phase1_outputs() -> None:
    reel_id = uuid.uuid4()
    layout = CanonicalStorageLayout(bucket="content-lab")

    package = layout.reel_package(reel_id)

    assert package.root.uri == f"s3://content-lab/reels/packages/{reel_id}"
    assert package.final_video.uri == f"s3://content-lab/reels/packages/{reel_id}/final_video.mp4"
    assert package.cover.uri == f"s3://content-lab/reels/packages/{reel_id}/cover.png"
    assert (
        package.caption_variants.uri
        == f"s3://content-lab/reels/packages/{reel_id}/caption_variants.txt"
    )
    assert (
        package.posting_plan.uri == f"s3://content-lab/reels/packages/{reel_id}/posting_plan.json"
    )
    assert package.provenance.uri == f"s3://content-lab/reels/packages/{reel_id}/provenance.json"
    assert (
        package.manifest.uri == f"s3://content-lab/reels/packages/{reel_id}/package_manifest.json"
    )
