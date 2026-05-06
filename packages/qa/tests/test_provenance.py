from __future__ import annotations

from content_lab_qa.provenance import validate_package_provenance


def _asset_lineage(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "role": "source_clip",
        "asset_id": "asset-source",
        "asset_kind": "source_clip",
        "media_type": "video",
        "source_type": "generated",
        "storage_uri": "s3://content-lab/assets/source.mp4",
        "stored_content_hash": "sha256:" + ("a" * 64),
        "used_as_component_role": "source_clip",
    }
    payload.update(updates)
    return payload


def test_validate_package_provenance_passes_with_required_lineage() -> None:
    result = validate_package_provenance(
        {
            "editor_version": "basic_vertical_v1",
            "assets": [
                _asset_lineage(),
                _asset_lineage(
                    role="final_video",
                    asset_id="asset-output",
                    asset_kind="final_render",
                    storage_uri="s3://content-lab/reels/packages/reel-123/final_video.mp4",
                    used_as_component_role="final_video",
                ),
            ],
            "provider_jobs": [
                {
                    "provider": "runway",
                    "status": "succeeded",
                }
            ],
        }
    )

    assert result.passed
    assert result.details == {"asset_count": 2, "provider_job_count": 1}


def test_validate_package_provenance_fails_when_editor_lineage_missing() -> None:
    result = validate_package_provenance(
        {
            "assets": [
                _asset_lineage(),
            ],
            "provider_jobs": [{"provider": "runway", "status": "succeeded"}],
        }
    )

    assert not result.passed
    assert result.message == "Package provenance is missing required fields: editor_version."


def test_validate_package_provenance_fails_for_invalid_asset_entry() -> None:
    result = validate_package_provenance(
        {
            "editor_version": "basic_vertical_v1",
            "assets": [_asset_lineage(role="")],
            "provider_jobs": [{"provider": "runway", "status": "succeeded"}],
        }
    )

    assert not result.passed
    assert result.message == "Asset lineage entry 1 is missing required fields: role."


def test_validate_package_provenance_fails_for_missing_provider_lineage() -> None:
    result = validate_package_provenance(
        {
            "editor_version": "basic_vertical_v1",
            "assets": [
                _asset_lineage(),
            ],
            "provider_jobs": [],
        }
    )

    assert not result.passed
    assert result.message == "Package provenance must include at least one provider lineage entry."
