from __future__ import annotations

from typing import Any

from content_lab_api.services import (
    InMemoryProcessReelRepository,
    ProcessReelExecution,
    ProcessReelQAResult,
    ProcessReelService,
)

_SHA256_A = "sha256:" + ("a" * 64)
_SHA256_B = "sha256:" + ("b" * 64)
_SHA256_C = "sha256:" + ("c" * 64)
_SHA256_D = "sha256:" + ("d" * 64)
_SHA256_E = "sha256:" + ("e" * 64)


def _package_payload(reel_id: str, run_id: str) -> dict[str, Any]:
    return {
        "reel_id": reel_id,
        "package_root_uri": f"s3://content-lab/reels/packages/{reel_id}",
        "manifest_uri": f"s3://content-lab/reels/packages/{reel_id}/package_manifest.json",
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
        "provenance_uri": f"s3://content-lab/reels/packages/{reel_id}/provenance.json",
        "provenance": {
            "editor_version": "basic_vertical_v1",
            "assets": [
                {
                    "role": "source_clip",
                    "storage_uri": f"s3://content-lab/assets/{reel_id}/source.mp4",
                }
            ],
            "provider_jobs": [
                {
                    "provider": "runway",
                    "status": "succeeded",
                    "job_id": f"job-{reel_id}",
                }
            ],
            "source_run_id": run_id,
            "asset_ids": ["asset-1", "asset-2"],
            "upstream_refs": {
                "timeline_uri": f"memory://edits/{reel_id}.json",
            },
        },
        "artifacts": [
            {
                "name": "final_video",
                "filename": "final_video.mp4",
                "storage_uri": f"s3://content-lab/reels/packages/{reel_id}/final_video.mp4",
                "checksum_sha256": _SHA256_A,
            },
            {
                "name": "cover",
                "filename": "cover.png",
                "storage_uri": f"s3://content-lab/reels/packages/{reel_id}/cover.png",
                "checksum_sha256": _SHA256_B,
            },
            {
                "name": "caption_variants",
                "filename": "caption_variants.txt",
                "storage_uri": f"s3://content-lab/reels/packages/{reel_id}/caption_variants.txt",
                "checksum_sha256": _SHA256_C,
            },
            {
                "name": "posting_plan",
                "filename": "posting_plan.json",
                "storage_uri": f"s3://content-lab/reels/packages/{reel_id}/posting_plan.json",
                "checksum_sha256": _SHA256_D,
            },
            {
                "name": "provenance",
                "filename": "provenance.json",
                "storage_uri": f"s3://content-lab/reels/packages/{reel_id}/provenance.json",
                "checksum_sha256": _SHA256_E,
            },
            {
                "name": "package_manifest",
                "filename": "package_manifest.json",
                "storage_uri": f"s3://content-lab/reels/packages/{reel_id}/package_manifest.json",
                "checksum_sha256": "sha256:" + ("f" * 64),
            },
        ],
    }


class _PackagingExecutor:
    def create_creative_plan(self, execution: ProcessReelExecution) -> dict[str, Any]:
        return {"brief_id": f"brief-{execution.reel_id}"}

    def resolve_assets(self, execution: ProcessReelExecution) -> dict[str, Any]:
        return {"asset_refs": [f"asset://{execution.reel_id}/primary"]}

    def edit_reel(self, execution: ProcessReelExecution) -> dict[str, Any]:
        return {"timeline_uri": f"memory://edits/{execution.reel_id}.json"}

    def run_qa(self, execution: ProcessReelExecution) -> ProcessReelQAResult:
        return ProcessReelQAResult(passed=True, details={"verdict": "pass"})

    def package_reel(self, execution: ProcessReelExecution) -> dict[str, Any]:
        return _package_payload(execution.reel_id, execution.run_id)


def _seed_service(
    executor: _PackagingExecutor,
) -> tuple[ProcessReelService, InMemoryProcessReelRepository]:
    repository = InMemoryProcessReelRepository()
    repository.seed_reel(
        reel_id="reel-42",
        org_id="org-1",
        page_id="page-7",
        reel_family_id="family-9",
    )
    return ProcessReelService(repository=repository, executor=executor), repository


def test_process_reel_service_persists_package_payload_on_reel_metadata() -> None:
    service, repository = _seed_service(_PackagingExecutor())

    execution = service.start_execution(reel_id="reel-42", dry_run=False)
    execution = service.run_creative_planning(execution)
    execution = service.run_asset_resolution(execution)
    execution = service.run_editing(execution)
    execution = service.run_qa(execution)
    execution = service.run_packaging(execution)
    summary = service.mark_ready(execution)

    reel = repository.reels["reel-42"]
    package_metadata = reel.metadata["package"]
    assert package_metadata["package_root_uri"] == "s3://content-lab/reels/packages/reel-42"
    assert reel.metadata["package_artifact_uris"]["final_video"] == (
        "s3://content-lab/reels/packages/reel-42/final_video.mp4"
    )
    assert reel.metadata["package_provenance_refs"] == [
        {"path": "asset_ids[0]", "value": "asset-1"},
        {"path": "asset_ids[1]", "value": "asset-2"},
        {"path": "assets[0].storage_uri", "value": "s3://content-lab/assets/reel-42/source.mp4"},
        {"path": "provider_jobs[0].job_id", "value": "job-reel-42"},
        {"path": "source_run_id", "value": summary["run_id"]},
        {
            "path": "upstream_refs.timeline_uri",
            "value": "memory://edits/reel-42.json",
        },
    ]
    assert summary["package"]["manifest"]["complete"] is True
    assert summary["package"]["package_qa"]["passed"] is True


def test_process_reel_service_fails_packaging_for_incomplete_package() -> None:
    class _IncompletePackagingExecutor(_PackagingExecutor):
        def package_reel(self, execution: ProcessReelExecution) -> dict[str, Any]:
            payload = _package_payload(execution.reel_id, execution.run_id)
            payload["artifacts"] = [
                artifact
                for artifact in payload["artifacts"]
                if artifact["name"] != "caption_variants"
            ]
            return payload

    service, repository = _seed_service(_IncompletePackagingExecutor())

    execution = service.start_execution(reel_id="reel-42", dry_run=False)
    execution = service.run_creative_planning(execution)
    execution = service.run_asset_resolution(execution)
    execution = service.run_editing(execution)
    execution = service.run_qa(execution)

    try:
        service.run_packaging(execution)
    except ValueError as exc:
        assert str(exc) == "Package is missing required files: caption_variants.txt."
    else:
        raise AssertionError("Expected package QA failure for incomplete package")

    packaging_result = repository.tasks[(execution.run_id, "packaging")].result
    assert packaging_result is not None
    assert packaging_result["error"] == "Package is missing required files: caption_variants.txt."
    assert packaging_result["package_qa"]["passed"] is False
    assert packaging_result["package_qa"]["checks"][0]["message"] == (
        "Package is missing required files: caption_variants.txt."
    )


def test_process_reel_service_fails_packaging_for_invalid_provenance() -> None:
    class _InvalidProvenancePackagingExecutor(_PackagingExecutor):
        def package_reel(self, execution: ProcessReelExecution) -> dict[str, Any]:
            payload = _package_payload(execution.reel_id, execution.run_id)
            payload["provenance"]["provider_jobs"] = []
            return payload

    service, repository = _seed_service(_InvalidProvenancePackagingExecutor())

    execution = service.start_execution(reel_id="reel-42", dry_run=False)
    execution = service.run_creative_planning(execution)
    execution = service.run_asset_resolution(execution)
    execution = service.run_editing(execution)
    execution = service.run_qa(execution)

    try:
        service.run_packaging(execution)
    except ValueError as exc:
        assert str(exc) == "Package provenance must include at least one provider lineage entry."
    else:
        raise AssertionError("Expected package QA failure for invalid provenance")

    packaging_result = repository.tasks[(execution.run_id, "packaging")].result
    assert packaging_result is not None
    assert packaging_result["package_qa"]["checks"][1]["message"] == (
        "Package provenance must include at least one provider lineage entry."
    )
