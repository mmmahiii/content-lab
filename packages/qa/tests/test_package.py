from __future__ import annotations

from typing import Any

from content_lab_qa.package import (
    evaluate_package,
    validate_layered_output_format,
    validate_package_completeness,
)
from content_lab_qa.text import lint_caption_texts, validate_caption_meta_language

_SHA256_A = "sha256:" + ("a" * 64)
_SHA256_B = "sha256:" + ("b" * 64)
_SHA256_C = "sha256:" + ("c" * 64)
_SHA256_D = "sha256:" + ("d" * 64)
_SHA256_E = "sha256:" + ("e" * 64)
_SHA256_T = "sha256:" + ("0" * 64)
_SHA256_R = "sha256:" + ("1" * 64)
_SHA256_O = "sha256:" + ("2" * 64)


def _valid_package_payload() -> dict[str, Any]:
    return {
        "reel_id": "reel-123",
        "package_root_uri": "s3://content-lab/reels/packages/reel-123",
        "manifest_uri": "s3://content-lab/reels/packages/reel-123/package_manifest.json",
        "caption_variants": [
            {"variant": "primary", "text": "Ship-day recap with three quick tips."},
        ],
        "manifest": {
            "version": 1,
            "artifact_count": 8,
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
                {
                    "name": "timeline",
                    "filename": "timeline.json",
                    "checksum_sha256": _SHA256_T,
                },
                {
                    "name": "timeline_render_trace",
                    "filename": "timeline_render_trace.json",
                    "checksum_sha256": _SHA256_R,
                },
                {
                    "name": "overlay_render_trace",
                    "filename": "overlay_render_trace.json",
                    "checksum_sha256": _SHA256_O,
                },
            ],
        },
        "provenance": {
            "editor_version": "basic_vertical_v1",
            "assets": [
                {
                    "role": "source_clip",
                    "asset_id": "asset-source",
                    "asset_kind": "source_clip",
                    "media_type": "video",
                    "source_type": "generated",
                    "storage_uri": "s3://content-lab/assets/source.mp4",
                    "stored_content_hash": _SHA256_A,
                    "used_as_component_role": "source_clip",
                }
            ],
            "provider_jobs": [{"provider": "runway", "status": "succeeded"}],
        },
        "timeline": {"version": "med-001.v1", "timeline_id": "timeline-1"},
        "timeline_render_trace": {
            "schema_version": "media_timeline_v1",
            "checks": {
                "duration_alignment": {
                    "passed": True,
                    "code": "editing_duration_mismatch",
                    "message": "ok",
                },
                "audio_video_sync": {
                    "passed": True,
                    "code": "audio_video_duration_mismatch",
                    "message": "ok",
                },
            },
        },
        "overlay_render_trace": {
            "artifact_type": "overlay_render_trace",
            "schema_version": "rendered_overlay_manifest_v1",
            "frame_width_px": 1080,
            "frame_height_px": 1920,
            "clip_duration_seconds": 12.0,
            "overlay_count": 0,
            "overlays": [],
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
                "name": "timeline",
                "filename": "timeline.json",
                "storage_uri": "s3://content-lab/reels/packages/reel-123/timeline.json",
                "checksum_sha256": _SHA256_T,
            },
            {
                "name": "timeline_render_trace",
                "filename": "timeline_render_trace.json",
                "storage_uri": "s3://content-lab/reels/packages/reel-123/timeline_render_trace.json",
                "checksum_sha256": _SHA256_R,
            },
            {
                "name": "overlay_render_trace",
                "filename": "overlay_render_trace.json",
                "storage_uri": "s3://content-lab/reels/packages/reel-123/overlay_render_trace.json",
                "checksum_sha256": _SHA256_O,
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
    assert payload["checks"][1]["gate_name"] == "package_layered_output"
    assert payload["checks"][2]["gate_name"] == "package_media_timeline"
    assert payload["checks"][3]["gate_name"] == "package_overlay_render_trace"
    assert payload["checks"][4]["gate_name"] == "caption_meta_language"
    assert payload["checks"][5]["gate_name"] == "package_provenance"
    assert payload["checks"][6]["gate_name"] == "source_rights"
    assert payload["checks"][7]["gate_name"] == "package_script_semantics"
    assert payload["checks"][6]["verdict"] == "pass"


def test_validate_layered_output_format_passes_for_valid_reel_output() -> None:
    payload = _valid_package_payload()
    payload["composition_manifest"] = {"schema_version": "composition_manifest_v1"}
    payload["duration_seconds"] = 12.0
    payload["layered_output"] = {
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "duration_seconds": 12.02,
        "streams": [
            {"codec_type": "video", "width": 1080, "height": 1920},
            {"codec_type": "audio", "codec_name": "aac"},
        ],
    }

    result = validate_layered_output_format(payload)

    assert result.passed
    assert result.details["findings"] == []


def test_validate_layered_output_format_blocks_broken_render_package() -> None:
    payload = _valid_package_payload()
    payload["composition_manifest"] = {"schema_version": "composition_manifest_v1"}
    payload["duration_seconds"] = 12.0
    payload["layered_output"] = {
        "format_name": "matroska,webm",
        "duration_seconds": 9.0,
        "streams": [{"codec_type": "video", "width": 720, "height": 1280}],
    }
    payload["artifacts"] = [
        artifact for artifact in payload["artifacts"] if artifact["name"] != "cover"
    ]

    result = validate_layered_output_format(payload)
    codes = {str(finding["code"]) for finding in result.details["findings"]}

    assert not result.passed
    assert "final_video_not_valid_mp4" in codes
    assert "final_video_dimensions_invalid" in codes
    assert "final_video_duration_invalid" in codes
    assert "final_video_missing_audio" in codes
    assert "cover_image_missing" in codes
    assert "package_artifacts_incomplete" in codes


def test_validate_caption_meta_language_fails_for_clear_caption_bug() -> None:
    payload = _valid_package_payload()
    payload["caption_variants"] = [
        {
            "variant": "broken",
            "text": "We saved the clear caption for editors to replace before publish.",
        },
    ]
    result = validate_caption_meta_language(payload)

    assert not result.passed
    assert result.details["failure_code"] == "caption_internal_system"
    findings = result.details["findings"]
    assert isinstance(findings, list) and findings
    assert findings[0]["code"] == "caption_internal_system"
    assert "clear caption" in findings[0]["caption_text"].lower()


def test_evaluate_package_warns_when_caption_meta_language_invalid() -> None:
    payload = _valid_package_payload()
    payload["caption_variants"] = [{"variant": "x", "text": "Internal caption — draft only."}]
    result = evaluate_package(payload)

    assert result.passed
    assert result.verdict.value == "pass"
    assert result.errors == []
    assert result.checks[4].gate_name == "caption_meta_language"
    assert not result.checks[4].passed
    assert result.checks[4].as_payload()["blocks_readiness"] is False
    findings = result.checks[4].details["findings"]
    assert isinstance(findings, list)
    first_finding = findings[0]
    assert isinstance(first_finding, dict)
    assert "caption_text" in first_finding


def test_evaluate_package_warns_when_caption_sources_missing() -> None:
    payload = _valid_package_payload()
    del payload["caption_variants"]
    payload["creative_trace"] = {}
    result = evaluate_package(payload)

    assert result.passed
    assert result.errors == []
    assert result.checks[4].gate_name == "caption_meta_language"
    assert result.checks[4].verdict.value == "fail"
    assert result.checks[4].as_payload()["blocks_readiness"] is False
    assert result.checks[4].details["errors"] == ["missing_caption_sources"]


def test_lint_caption_texts_deduplicates_repeated_rows() -> None:
    duplicate_text = "We saved the clear caption for editors to replace."
    entries = [
        ("caption_variants[0]/a", duplicate_text),
        ("caption_variants[0]/a", duplicate_text),
    ]
    findings = lint_caption_texts(entries)
    assert len(findings) == 1
