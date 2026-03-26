from __future__ import annotations

from content_lab_qa.provenance import validate_package_provenance


def test_validate_package_provenance_passes_with_required_lineage() -> None:
    result = validate_package_provenance(
        {
            "editor_version": "basic_vertical_v1",
            "assets": [
                {
                    "role": "source_clip",
                    "storage_uri": "s3://content-lab/assets/source.mp4",
                },
                {
                    "role": "final_video",
                    "storage_uri": "s3://content-lab/reels/packages/reel-123/final_video.mp4",
                },
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
                {"role": "source_clip", "storage_uri": "s3://content-lab/assets/source.mp4"}
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
            "assets": [{"storage_uri": "s3://content-lab/assets/source.mp4"}],
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
                {"role": "source_clip", "storage_uri": "s3://content-lab/assets/source.mp4"}
            ],
            "provider_jobs": [],
        }
    )

    assert not result.passed
    assert result.message == "Package provenance must include at least one provider lineage entry."
