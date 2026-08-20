#!/usr/bin/env python
"""Validate a generated CinematicReelPlan through QA and renderer preflight."""

from __future__ import annotations

import argparse
import json
import sys
import types
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
for relative in (
    "packages/shared/py/src",
    "packages/core/src",
    "packages/creative/src",
    "packages/editing/src",
    "packages/storage/src",
    "packages/qa/src",
):
    src_path = REPO_ROOT / relative
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

editing_pkg = types.ModuleType("content_lab_editing")
editing_pkg.__path__ = [str(REPO_ROOT / "packages/editing/src/content_lab_editing")]
sys.modules.setdefault("content_lab_editing", editing_pkg)

from content_lab_creative.planning_schema import CinematicReelPlan  # noqa: E402
from content_lab_creative.single_prompt_reel_planner import build_plan_artifacts  # noqa: E402
from content_lab_editing.compositor import preflight_compositor_timeline  # noqa: E402
from content_lab_editing.support_surface_overlap import OverlapValidationContext  # noqa: E402
from content_lab_qa.plan_realism import validate_cinematic_plan_realism  # noqa: E402
from content_lab_qa.placement_overlap_lookup import (  # noqa: E402
    build_overlap_validation_context,
    collect_mask_uris_from_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run schema, scene QA, and renderer relationship checks on a plan JSON file."
    )
    parser.add_argument("plan_json", type=Path)
    parser.add_argument("--output-report", type=Path)
    parser.add_argument(
        "--masks-dir",
        type=Path,
        default=None,
        help="Directory of support-surface mask files keyed by URI basename (optional).",
    )
    args = parser.parse_args()

    payload = json.loads(args.plan_json.read_text(encoding="utf-8"))
    plan = CinematicReelPlan.model_validate(payload)
    overlap_context = _overlap_context_from_masks_dir(plan, args.masks_dir)
    realism_report = validate_cinematic_plan_realism(plan, overlap_context=overlap_context)
    artifacts = build_plan_artifacts(plan, realism_qa={"plan_realism": realism_report.as_dict()})
    compositor_report = preflight_compositor_timeline(
        artifacts["reel_timeline.json"],
        overlap_context=overlap_context,
    )
    report: dict[str, Any] = {
        "schema_version": "e2e_plan_validation_smoke_v1",
        "passed": realism_report.passed and compositor_report.passed,
        "plan_realism": realism_report.as_dict(),
        "compositor_preflight": compositor_report.as_dict(),
    }
    if args.output_report:
        args.output_report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


def _overlap_context_from_masks_dir(
    plan: CinematicReelPlan,
    masks_dir: Path | None,
) -> OverlapValidationContext | None:
    if masks_dir is None or not masks_dir.is_dir():
        return None

    def fetch_bytes(uri: str) -> bytes | None:
        candidate = masks_dir / Path(uri).name
        if not candidate.is_file():
            return None
        return candidate.read_bytes()

    uris = collect_mask_uris_from_plan(plan)
    if not uris:
        return None
    return build_overlap_validation_context(assets_by_id={}, mask_uris=uris, fetch_bytes=fetch_bytes)


if __name__ == "__main__":
    raise SystemExit(main())
