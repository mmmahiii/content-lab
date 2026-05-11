from __future__ import annotations

import importlib
from collections.abc import Mapping
from typing import Any

import pytest

asset_pack_generation_module = importlib.import_module(
    "content_lab_orchestrator.flows.asset_pack_generation"
)
asset_pack_to_reels_module = importlib.import_module(
    "content_lab_orchestrator.flows.asset_pack_to_reels"
)


class RecordingAssetPackGenerationRuntime:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.notifications: list[dict[str, Any]] = []

    def start_run(self, request_payload: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append("start_run")
        return {"run_id": request_payload.get("run_id") or "run-pack-1", "status": "running"}

    def create_pack(self, request_payload: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append("create_pack")
        return {
            "asset_pack": {
                "id": "pack-1",
                "org_id": request_payload["org_id"],
                "name": request_payload["name"],
                "status": "draft",
            },
            "created": True,
        }

    def create_plan(
        self,
        request_payload: Mapping[str, Any],
        pack_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.calls.append("create_plan")
        return {
            "asset_pack": {
                "id": pack_payload["asset_pack"]["id"],
                "org_id": request_payload["org_id"],
                "status": "planned",
            },
            "planned_asset_specs": [
                {"id": "spec-1", "asset_kind": "hook_text", "status": "planned"}
            ],
            "planning_resolution_summary": {"planned": 1, "ready_assets": 0},
        }

    def approve_or_wait(
        self,
        request_payload: Mapping[str, Any],
        plan_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.calls.append("approve_plan")
        return {
            "asset_pack_id": plan_payload["asset_pack"]["id"],
            "status": "approved",
            "auto_approved": bool(request_payload["auto_approve"]),
        }

    def resolve_existing_assets(
        self,
        request_payload: Mapping[str, Any],
        plan_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.calls.append("resolve_existing_assets")
        return {
            "asset_pack_id": plan_payload["asset_pack"]["id"],
            "resolution_summary": {"ready_assets": 0},
        }

    def generate_missing_assets(
        self,
        request_payload: Mapping[str, Any],
        approval_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.calls.append("generate_missing_assets")
        return {
            "asset_pack": {
                "id": approval_payload["asset_pack_id"],
                "org_id": request_payload["org_id"],
                "status": "generating",
            },
            "resolution_summary": {"generating": 1, "ready_assets": 0},
            "generation_decisions": [{"decision": "generate"}],
        }

    def register_assets(
        self,
        request_payload: Mapping[str, Any],
        generation_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.calls.append("register_assets")
        return {
            "asset_pack_id": generation_payload["asset_pack"]["id"],
            "status": "ready",
            "resolution_summary": {"generated": 1, "ready_assets": 1},
        }

    def mark_pack_ready(
        self,
        request_payload: Mapping[str, Any],
        registration_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.calls.append("mark_pack_ready")
        return {
            "run_id": request_payload["run_id"],
            "workflow_key": "generate_asset_pack",
            "run_status": "succeeded",
            "asset_pack_id": registration_payload["asset_pack_id"],
            "asset_pack_status": registration_payload["status"],
            "resolution_summary": registration_payload["resolution_summary"],
        }

    def emit_notification(self, summary: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append("emit_notification")
        event = {"event_type": "asset_pack.generation.completed", "emitted": True}
        self.notifications.append({**event, "summary": dict(summary)})
        return event

    def mark_failed(
        self,
        request_payload: Mapping[str, Any],
        *,
        failed_step: str,
        error_message: str,
    ) -> dict[str, Any]:
        self.calls.append("mark_failed")
        return {
            "run_id": request_payload["run_id"],
            "run_status": "failed",
            "failed_step": failed_step,
            "error_message": error_message,
        }


class RecordingAssetPackToReelsRuntime:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.notifications: list[dict[str, Any]] = []

    def start_run(self, request_payload: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append("start_run")
        return {"run_id": request_payload.get("run_id") or "run-combo-1", "status": "running"}

    def load_pack(self, request_payload: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append("load_pack")
        return {
            "id": request_payload["asset_pack_id"],
            "org_id": request_payload["org_id"],
            "name": "Reusable pack",
            "status": "ready",
        }

    def generate_candidate_combinations(
        self,
        request_payload: Mapping[str, Any],
        pack_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.calls.append("generate_candidate_combinations")
        return {
            "candidate_compositions": [
                {
                    "composition_id": "combo-1",
                    "roles": {
                        "hook": {"asset_id": "asset-hook", "asset_kind": "hook_text"},
                        "background": {
                            "asset_id": "asset-background",
                            "asset_kind": "background_video",
                        },
                    },
                    "compatibility_score": 0.9,
                    "diversity_score": 0.7,
                    "performance_score": 0.6,
                    "selection_score": 0.8,
                    "reasons": ["hook pairs with background"],
                }
            ],
            "candidate_count": int(request_payload["target_reel_count"]),
            "asset_pack": dict(pack_payload),
        }

    def create_composition_manifests(
        self,
        request_payload: Mapping[str, Any],
        candidates_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.calls.append("create_composition_manifests")
        candidate = candidates_payload["candidate_compositions"][0]
        return {
            "asset_pack_id": request_payload["asset_pack_id"],
            "composition_manifests": [
                {
                    "schema_version": "asset_composition_manifest.v1",
                    "asset_pack_id": request_payload["asset_pack_id"],
                    "composition_id": candidate["composition_id"],
                    "roles": candidate["roles"],
                    "scores": {"selection": candidate["selection_score"]},
                }
            ],
        }

    def render_selected_candidates(
        self,
        request_payload: Mapping[str, Any],
        manifests_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.calls.append("render_selected_candidates")
        assert manifests_payload["composition_manifests"][0]["schema_version"]
        return {"rendered": False, "render_submissions": [], "reason": "render_not_requested"}

    def package_outputs(
        self,
        request_payload: Mapping[str, Any],
        manifests_payload: Mapping[str, Any],
        render_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.calls.append("package_outputs")
        return {
            "run_id": request_payload["run_id"],
            "workflow_key": "asset_pack_to_reels",
            "run_status": "succeeded",
            "asset_pack_id": request_payload["asset_pack_id"],
            "candidate_count": len(manifests_payload["composition_manifests"]),
            "composition_manifests": manifests_payload["composition_manifests"],
            "render_submissions": render_payload["render_submissions"],
            "rendered": render_payload["rendered"],
        }

    def emit_notification(self, summary: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append("emit_notification")
        event = {"event_type": "asset_pack.reel_candidates.packaged", "emitted": True}
        self.notifications.append({**event, "summary": dict(summary)})
        return event

    def mark_failed(
        self,
        request_payload: Mapping[str, Any],
        *,
        failed_step: str,
        error_message: str,
    ) -> dict[str, Any]:
        self.calls.append("mark_failed")
        return {
            "run_id": request_payload["run_id"],
            "run_status": "failed",
            "failed_step": failed_step,
            "error_message": error_message,
        }


def test_generate_asset_pack_flow_orchestrates_reviewed_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = RecordingAssetPackGenerationRuntime()
    monkeypatch.setattr(
        asset_pack_generation_module,
        "build_asset_pack_generation_runtime",
        lambda: runtime,
    )

    result = asset_pack_generation_module.generate_asset_pack(
        org_id="11111111-1111-1111-1111-111111111111",
        name="Spring launch pack",
        niche="mobility coaching",
        requested_asset_count=1,
        auto_approve=True,
    )

    assert runtime.calls == [
        "start_run",
        "create_pack",
        "create_plan",
        "approve_plan",
        "resolve_existing_assets",
        "generate_missing_assets",
        "register_assets",
        "mark_pack_ready",
        "emit_notification",
    ]
    assert result["workflow_key"] == "generate_asset_pack"
    assert result["asset_pack_status"] == "ready"
    assert runtime.notifications[0]["summary"]["asset_pack_id"] == "pack-1"


def test_asset_pack_to_reels_flow_creates_manifests_without_rendering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = RecordingAssetPackToReelsRuntime()
    monkeypatch.setattr(
        asset_pack_to_reels_module,
        "build_asset_pack_to_reels_runtime",
        lambda: runtime,
    )

    result = asset_pack_to_reels_module.asset_pack_to_reels(
        org_id="11111111-1111-1111-1111-111111111111",
        asset_pack_id="22222222-2222-2222-2222-222222222222",
        target_reel_count=1,
        render_selected=False,
    )

    assert runtime.calls == [
        "start_run",
        "load_pack",
        "generate_candidate_combinations",
        "create_composition_manifests",
        "render_selected_candidates",
        "package_outputs",
        "emit_notification",
    ]
    assert result["workflow_key"] == "asset_pack_to_reels"
    assert result["rendered"] is False
    assert result["composition_manifests"][0]["schema_version"] == (
        "asset_composition_manifest.v1"
    )
    assert runtime.notifications[0]["summary"]["candidate_count"] == 1
