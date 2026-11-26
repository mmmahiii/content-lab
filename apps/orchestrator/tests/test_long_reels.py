"""Reels longer than one provider clip (Runway gen4.5 caps a clip at 10 s).

The reel used to be clamped to 10 s end to end. Creative planning now keeps the plan length
(5-60 s), asks for one 5-10 s clip per part of the reel, and editing chains the clips.
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import Any, cast

import pytest
from content_lab_assets.providers.runway import render_mock_clip
from content_lab_creative import PolicyStateDocument
from content_lab_editing import MockToneTTSProvider
from content_lab_storage import CanonicalStorageLayout

from content_lab_api.services.process_reel import ProcessReelExecution
from content_lab_core.types import Platform
from content_lab_orchestrator.flows.process_reel import (
    MAX_REEL_DURATION_SECONDS,
    PhaseOnePlanningContext,
    PhaseOneProcessReelExecutor,
    _clip_plan,
    _reel_duration_seconds,
)


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        (5, [(0, 5)]),
        (7, [(0, 7)]),
        (10, [(0, 10)]),
        (12, [(0, 6), (6, 12)]),
        (15, [(0, 8), (8, 15)]),
        (20, [(0, 10), (10, 20)]),
        (21, [(0, 7), (7, 14), (14, 21)]),
        (30, [(0, 10), (10, 20), (20, 30)]),
    ],
)
def test_clip_plan_uses_fewest_provider_sized_clips(
    duration: int, expected: list[tuple[int, int]]
) -> None:
    spans = _clip_plan(duration)

    assert spans == expected
    assert all(5 <= end - start <= 10 for start, end in spans)


def test_reel_duration_is_bounded_but_not_by_the_provider_clip() -> None:
    assert _reel_duration_seconds(3) == 5
    assert _reel_duration_seconds(25) == 25
    assert _reel_duration_seconds(500) == MAX_REEL_DURATION_SECONDS


class _Loader:
    def __init__(self, context: PhaseOnePlanningContext) -> None:
        self._context = context

    def load(self, execution: ProcessReelExecution) -> PhaseOnePlanningContext:
        _ = execution
        return self._context


def _probe(path: Path) -> dict[str, str]:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height,duration",
            "-of",
            "default=noprint_wrappers=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    values: dict[str, str] = {}
    for line in out.splitlines():
        key, _, value = line.partition("=")
        values.setdefault(key, value)
    return values


def test_twenty_second_idea_plan_renders_from_two_clips_and_passes_media_qa(
    tmp_path: Path,
) -> None:
    source_plan: dict[str, Any] = {
        "hook": "What would make @test worth following this week?",
        "angle": "Turn one practical page insight into a clear update.",
        "title": "long plan",
        "beats": [
            {
                "text": "Open with the problem.",
                "label": "Hook",
                "seconds": 5,
                "narration": "Here is the problem most pages have.",
            },
            {
                "text": "Show the shift.",
                "label": "Proof",
                "seconds": 10,
                "narration": "Swap the vague post for one concrete example people can copy.",
            },
            {
                "text": "Close with a step.",
                "label": "Action",
                "seconds": 5,
                "narration": "Try it on your next post.",
            },
        ],
        "caption_angles": ["Save this.", "A simple approach.", "Try it today."],
    }
    context = PhaseOnePlanningContext(
        page_name="test",
        page_metadata={},
        family_name="long plan",
        family_mode="explore",
        variant_label="Smoke test",
        brief_index=0,
        target_platforms=(Platform.INSTAGRAM,),
        timezone="UTC",
        locale="en",
        policy=PolicyStateDocument(),
        duration_seconds=20,
        source_plan=source_plan,
    )
    executor = PhaseOneProcessReelExecutor(
        planning_context_loader=_Loader(context),
        asset_resolver=cast(Any, None),
        storage_client=cast(Any, None),
        package_layout=CanonicalStorageLayout(bucket="test"),
        temp_root=tmp_path / "runs",
        tts_provider=MockToneTTSProvider(),
    )
    execution = ProcessReelExecution(
        reel_id=str(uuid.uuid4()),
        org_id=str(uuid.uuid4()),
        page_id=str(uuid.uuid4()),
        reel_family_id=str(uuid.uuid4()),
        run_id=str(uuid.uuid4()),
        dry_run=False,
    )
    creative = executor.create_creative_plan(execution)
    requests = [creative["primary_asset_request"], *creative["supplementary_asset_requests"]]
    assert creative["canonical_timeline"]["duration_seconds"] == 20
    assert [r["duration_seconds"] for r in requests] == [10, 10]

    # What the resolver returns after generating both clips through the mock provider.
    clip_paths = []
    for index, request in enumerate(requests):
        path = tmp_path / f"clip-{index}.mp4"
        path.write_bytes(
            render_mock_clip(duration_seconds=request["duration_seconds"], seed=request["seed"])
        )
        clip_paths.append(path)
    execution.outputs["creative_planning"] = creative
    execution.outputs["asset_resolution"] = {
        "storage_uri": str(clip_paths[0]),
        "asset_key_hash": "long-reel",
        "policy": {},
        "source_clips": [
            {
                "clip_index": index,
                "storage_uri": str(path),
                "requested_duration_seconds": requests[index]["duration_seconds"],
            }
            for index, path in enumerate(clip_paths)
        ],
    }

    editing = executor.edit_reel(execution)
    execution.outputs["editing"] = editing
    qa = executor.run_qa(execution)

    probe = _probe(Path(editing["final_video_path"]))
    assert float(probe["duration"]) == pytest.approx(20.0, abs=0.1)
    assert (probe["width"], probe["height"]) == ("1080", "1920")
    assert editing["source_composition"]["mode"] == "chain"
    assert [p["timeline_start_seconds"] for p in editing["source_composition"]["placements"]] == [
        0.0,
        10.0,
    ]
    assert editing["duration_contract"]["status"] == "pass"
    details = qa.as_payload()
    assert details["media_content"]["verdict"] == "pass", details["media_content"]
    assert details["overlay_coverage"]["verdict"] == "pass", details["overlay_coverage"]
    assert details["audio_content"]["verdict"] == "warn", details["audio_content"]
    assert details["timeline_timing"]["verdict"] in {"pass", "warn"}, details["timeline_timing"]
