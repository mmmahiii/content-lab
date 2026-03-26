from __future__ import annotations

from typing import Any

from content_lab_qa.package import evaluate_package, validate_package_completeness

_SHA256_A = "sha256:" + ("a" * 64)
_SHA256_B = "sha256:" + ("b" * 64)
_SHA256_C = "sha256:" + ("c" * 64)
_SHA256_D = "sha256:" + ("d" * 64)
_SHA256_E = "sha256:" + ("e" * 64)


def _valid_package_payload() -> dict[str, Any]:
    return {
        "reel_id": "reel-123",
        "package_root_uri": "s3://content-lab/reels/packages/reel-123",
        "manifest_uri": "s3://content-lab/reels/packages/reel-123/package_manifest.json",
        "manifest": {
            "version": 1,
            "artifact_count": 5,
            "complete": True,
            "artifacts": [
                {
                    "name": "final_video",
                    "filename": "final_video.mp4",
                    "checksum_sha256": _SHA256_A,
                },
                {
                    "name": "cover",
                    "filename": "cover.png",
                    "checksum_sha256": _SHA256_B,
                },
                {
                    "name": "caption_variants",
                    "filename": "caption_variants.txt",
                    "checksum_sha256": _SHA256_C,
                },
                {
                    "name": "posting_plan",
                    "filename": "posting_plan.json",
                    "checksum_sha256": _SHA256_D,
                },
                {
                    "name": "provenance",
                    "filename": "provenance.json",
                    "checksum_sha256": _SHA256_E,
                },
            ],
        },
        "provenance": {
            "editor_version": "basic_vertical_v1",
            "assets": [
                {
                    "role": "source_clip",
                    "storage_uri": "s3://content-lab/assets/source.mp4",
                }
            ],
            "provider_jobs": [{"provider": "runway", "status": "succeeded"}],
        },
        "artifacts": [
            {
                "name": "final_video",
                "filename": "final_video.mp4",
                "storage_uri": "s3://content-lab/reels/packages/reel-123/final_video.mp4",
                "checksum_sha256": _SHA256_A,
            },
            {
                "name": "cover",
                "filename": "cover.png",
                "storage_uri": "s3://content-lab/reels/packages/reel-123/cover.png",
                "checksum_sha256": _SHA256_B,
            },
            {
                "name": "caption_variants",
                "filename": "caption_variants.txt",
                "storage_uri": "s3://content-lab/reels/packages/reel-123/caption_variants.txt",
                "checksum_sha256": _SHA256_C,
            },
            {
                "name": "posting_plan",
                "filename": "posting_plan.json",
                "storage_uri": "s3://content-lab/reels/packages/reel-123/posting_plan.json",
                "checksum_sha256": _SHA256_D,
            },
            {
                "name": "provenance",
                "filename": "provenance.json",
                "storage_uri": "s3://content-lab/reels/packages/reel-123/provenance.json",
                "checksum_sha256": _SHA256_E,
            },
            {
                "name": "package_manifest",
                "filename": "package_manifest.json",
                "storage_uri": "s3://content-lab/reels/packages/reel-123/package_manifest.json",
                "checksum_sha256": "sha256:" + ("f" * 64),
            },
        ],
    }


def test_validate_package_completeness_passes_for_complete_package() -> None:
    result = validate_package_completeness(_valid_package_payload())

    assert result.passed
    assert result.message == "Package includes the required files and manifest checksums match."


def test_validate_package_completeness_fails_for_missing_required_files() -> None:
    package_payload = _valid_package_payload()
    package_payload["artifacts"] = [
        artifact
        for artifact in package_payload["artifacts"]
        if artifact["name"] != "caption_variants"
    ]

    result = validate_package_completeness(package_payload)

    assert not result.passed
    assert result.message == "Package is missing required files: caption_variants.txt."
    assert result.details["missing_files"] == ["caption_variants.txt"]


def test_validate_package_completeness_fails_for_manifest_checksum_mismatch() -> None:
    package_payload = _valid_package_payload()
    package_payload["manifest"]["artifacts"][0]["checksum_sha256"] = _SHA256_B

    result = validate_package_completeness(package_payload)

    assert not result.passed
    assert result.message == "Package manifest checksum mismatch for: final_video."
    assert result.details["checksum_mismatches"] == [
        {
            "artifact": "final_video",
            "package_checksum": _SHA256_A,
            "manifest_checksum": _SHA256_B,
        }
    ]


def test_evaluate_package_aggregates_package_and_provenance_checks() -> None:
    package_payload = _valid_package_payload()
    package_payload["provenance"]["provider_jobs"] = []

    result = evaluate_package(package_payload)
    payload = result.as_payload()

    assert not result.passed
    assert result.errors == ["Package provenance must include at least one provider lineage entry."]
    assert payload["checks"][0]["gate_name"] == "package_completeness"
    assert payload["checks"][1]["gate_name"] == "package_provenance"
