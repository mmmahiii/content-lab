from __future__ import annotations

from typing import Any

from content_lab_api.services import (
    InMemoryProcessReelRepository,
    ProcessReelExecution,
    ProcessReelQAResult,
    ProcessReelService,
)


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
        return {
            "reel_id": execution.reel_id,
            "package_root_uri": f"s3://content-lab/reels/packages/{execution.reel_id}",
            "manifest_uri": (
                f"s3://content-lab/reels/packages/{execution.reel_id}/package_manifest.json"
            ),
            "manifest": {
                "version": 1,
                "artifact_count": 5,
                "complete": True,
            },
            "provenance_uri": f"s3://content-lab/reels/packages/{execution.reel_id}/provenance.json",
            "provenance": {
                "source_run_id": execution.run_id,
                "asset_ids": ["asset-1", "asset-2"],
                "upstream_refs": {
                    "timeline_uri": execution.outputs["editing"]["timeline_uri"],
                },
            },
            "artifacts": [
                {
                    "name": "final_video",
                    "storage_uri": f"s3://content-lab/reels/packages/{execution.reel_id}/final_video.mp4",
                },
                {
                    "name": "cover",
                    "storage_uri": f"s3://content-lab/reels/packages/{execution.reel_id}/cover.png",
                },
                {
                    "name": "caption_variants",
                    "storage_uri": (
                        f"s3://content-lab/reels/packages/{execution.reel_id}/caption_variants.txt"
                    ),
                },
                {
                    "name": "posting_plan",
                    "storage_uri": (
                        f"s3://content-lab/reels/packages/{execution.reel_id}/posting_plan.json"
                    ),
                },
                {
                    "name": "provenance",
                    "storage_uri": (
                        f"s3://content-lab/reels/packages/{execution.reel_id}/provenance.json"
                    ),
                },
            ],
        }


def test_process_reel_service_persists_package_payload_on_reel_metadata() -> None:
    repository = InMemoryProcessReelRepository()
    repository.seed_reel(
        reel_id="reel-42",
        org_id="org-1",
        page_id="page-7",
        reel_family_id="family-9",
    )
    service = ProcessReelService(repository=repository, executor=_PackagingExecutor())

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
        {"path": "source_run_id", "value": summary["run_id"]},
        {
            "path": "upstream_refs.timeline_uri",
            "value": "memory://edits/reel-42.json",
        },
    ]
    assert summary["package"]["manifest"]["complete"] is True
