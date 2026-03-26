from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import Mock

import pytest

from content_lab_storage import CanonicalStorageLayout, StoredObject
from content_lab_storage.reel_packages import (
    assert_reel_package_complete,
    expected_reel_package_filenames,
    persist_reel_package_directory,
    resolve_reel_package_directory,
)
from content_lab_storage.refs import StorageRef


def test_expected_reel_package_filenames_include_manifest_by_default() -> None:
    assert expected_reel_package_filenames() == (
        "final_video.mp4",
        "cover.png",
        "caption_variants.txt",
        "posting_plan.json",
        "provenance.json",
        "package_manifest.json",
    )


def test_resolve_reel_package_directory_requires_all_required_files(tmp_path: Path) -> None:
    for filename in expected_reel_package_filenames(include_manifest=False)[:-1]:
        (tmp_path / filename).write_text("placeholder", encoding="utf-8")

    with pytest.raises(ValueError, match="provenance.json"):
        resolve_reel_package_directory(tmp_path, include_manifest=False)


def test_assert_reel_package_complete_rejects_missing_artifacts() -> None:
    with pytest.raises(ValueError, match="caption_variants"):
        assert_reel_package_complete(
            [
                {"name": "final_video"},
                {"name": "cover"},
                {"name": "posting_plan"},
                {"name": "provenance"},
            ]
        )


def test_persist_reel_package_directory_uploads_canonical_objects(tmp_path: Path) -> None:
    client = Mock()
    reel_id = uuid.uuid4()
    layout = CanonicalStorageLayout(bucket="content-lab")

    for filename in expected_reel_package_filenames():
        (tmp_path / filename).write_bytes(f"payload:{filename}".encode())

    def _stored(
        ref: StorageRef, *, content_type: str | None, metadata: dict[str, str]
    ) -> StoredObject:
        return StoredObject(
            ref=ref,
            size_bytes=123,
            content_type=content_type,
            metadata=metadata,
            checksum_sha256="sha256:" + ("a" * 64),
        )

    client.put_object.side_effect = lambda **kwargs: _stored(
        kwargs["ref"],
        content_type=kwargs.get("content_type"),
        metadata=dict(kwargs.get("metadata", {})),
    )

    stored_package = persist_reel_package_directory(
        client=client,
        layout=layout,
        reel_id=reel_id,
        directory=tmp_path,
        metadata={"source": "pytest"},
    )

    assert stored_package.root_uri == f"s3://content-lab/reels/packages/{reel_id}"
    assert stored_package.artifact_by_name("package_manifest") is not None
    assert stored_package.artifact_uris["final_video"] == (
        f"s3://content-lab/reels/packages/{reel_id}/final_video.mp4"
    )
    assert client.put_object.call_count == 6
    first_call = client.put_object.call_args_list[0].kwargs
    assert first_call["metadata"]["source"] == "pytest"
    assert first_call["metadata"]["reel-id"] == str(reel_id)
    assert first_call["checksum_sha256"].startswith("sha256:")
