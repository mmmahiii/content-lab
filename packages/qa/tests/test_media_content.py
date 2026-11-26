"""Decoded-media QA: silent audio, blank/static video, uncovered overlays.

Regression for the 2026-11-25 smoke run: a reel with black footage, text only for 0-6 s of
10 s and -91 dB audio passed every QA gate.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from content_lab_core.types import QAVerdict
from content_lab_qa.gate import qa_result_blocks_readiness
from content_lab_qa.media_content import (
    MOCK_VOICEOVER_TAG_VALUE,
    MediaContentAnalysis,
    MediaInterval,
    _parse_marker_segments,
    analyze_media_content,
    evaluate_audio_content_qa,
    evaluate_media_content_qa,
    evaluate_overlay_coverage_qa,
)

_SIZE = "180x320"


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def _encode(path: Path, *inputs: str, filter_complex: str | None = None, tag: str | None = None):
    args = [*inputs]
    if filter_complex is not None:
        args += ["-filter_complex", filter_complex, "-map", "[v]", "-map", "[a]"]
    if tag is not None:
        args += ["-metadata", f"comment={tag}"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ac", "2", str(path)]
    _ffmpeg(*args)
    return path


def _moving(seconds: float) -> list[str]:
    return ["-f", "lavfi", "-i", f"testsrc2=s={_SIZE}:r=24:d={seconds}"]


def _tone(seconds: float) -> list[str]:
    return ["-f", "lavfi", "-i", f"sine=f=440:r=48000:d={seconds}"]


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("media_content")
    black = ["-f", "lavfi", "-i", f"color=black:s={_SIZE}:r=24:d=4"]
    silence = ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo:d=10"]
    still = ["-f", "lavfi", "-i", f"color=gray:s={_SIZE}:r=24:d=3"]
    return {
        "good": _encode(
            root / "good.mp4",
            *_moving(6),
            *_tone(6),
            filter_complex="[0:v]null[v];[1:a]anull[a]",
        ),
        # Moving footage then a 4 s black tail: the shape of the blank-tail bug.
        "black_tail": _encode(
            root / "black_tail.mp4",
            *_moving(6),
            *black,
            *_tone(10),
            filter_complex="[0:v][1:v]concat=n=2:v=1[v];[2:a]anull[a]",
        ),
        "frozen_middle": _encode(
            root / "frozen_middle.mp4",
            *_moving(3),
            *still,
            *_moving(3),
            *_tone(9),
            filter_complex="[0:v][1:v][2:v]concat=n=3:v=1[v];[3:a]anull[a]",
        ),
        "silent": _encode(
            root / "silent.mp4",
            *_moving(10),
            *silence,
            filter_complex="[0:v]null[v];[1:a]anull[a]",
        ),
        "mock_voice": _encode(
            root / "mock_voice.mp4",
            *_moving(4),
            *_tone(4),
            filter_complex="[0:v]null[v];[1:a]anull[a]",
            tag=MOCK_VOICEOVER_TAG_VALUE,
        ),
    }


def test_good_reel_passes_video_and_audio_checks(media: dict[str, Path]) -> None:
    analysis = analyze_media_content(media["good"])

    assert evaluate_media_content_qa(analysis=analysis).verdict == QAVerdict.PASS
    assert evaluate_audio_content_qa(analysis=analysis).verdict == QAVerdict.PASS
    assert analysis.mean_volume_db is not None and analysis.mean_volume_db > -40


def test_black_tail_fails_and_blocks_readiness(media: dict[str, Path]) -> None:
    result = evaluate_media_content_qa(analysis=analyze_media_content(media["black_tail"]))

    assert result.verdict == QAVerdict.FAIL
    assert qa_result_blocks_readiness(result)
    blank = [f for f in result.details["findings"] if f["code"] == "video_blank_segment"]  # type: ignore[union-attr]
    assert blank, result.details
    assert blank[0]["details"]["start_seconds"] == pytest.approx(6.0, abs=0.1)
    assert blank[0]["details"]["duration_seconds"] == pytest.approx(4.0, abs=0.15)


def test_frozen_middle_fails_as_static(media: dict[str, Path]) -> None:
    result = evaluate_media_content_qa(analysis=analyze_media_content(media["frozen_middle"]))

    codes = [f["code"] for f in result.details["findings"]]  # type: ignore[union-attr]
    assert result.verdict == QAVerdict.FAIL
    assert "video_static_segment" in codes


def test_silent_audio_fails_and_blocks_readiness(media: dict[str, Path]) -> None:
    analysis = analyze_media_content(media["silent"])
    result = evaluate_audio_content_qa(analysis=analysis)

    assert analysis.mean_volume_db is not None and analysis.mean_volume_db < -60
    assert result.verdict == QAVerdict.FAIL
    assert qa_result_blocks_readiness(result)
    assert result.details["findings"][0]["code"] == "audio_silent"  # type: ignore[index]


def test_mock_voiceover_is_recognised_from_the_file_tag(media: dict[str, Path]) -> None:
    analysis = analyze_media_content(media["mock_voice"])
    result = evaluate_audio_content_qa(analysis=analysis, expect_voiceover=False)

    assert analysis.is_mock_voiceover
    assert result.verdict == QAVerdict.WARN
    assert not qa_result_blocks_readiness(result)
    assert result.details["mock_voiceover"] is True


def test_missing_voiceover_fails_when_script_has_narration() -> None:
    analysis = MediaContentAnalysis(duration_seconds=10, has_audio=True, mean_volume_db=-20.0)

    result = evaluate_audio_content_qa(analysis=analysis, voiceover=None, expect_voiceover=True)

    assert result.verdict == QAVerdict.FAIL
    assert [f["code"] for f in result.details["findings"]] == ["voiceover_missing"]  # type: ignore[union-attr]


def test_long_silent_gap_inside_audible_audio_warns() -> None:
    analysis = MediaContentAnalysis(
        duration_seconds=10,
        has_audio=True,
        mean_volume_db=-25.0,
        silent_segments=(MediaInterval(6.0, 10.0),),
    )

    result = evaluate_audio_content_qa(analysis=analysis)

    assert result.verdict == QAVerdict.WARN
    assert not qa_result_blocks_readiness(result)
    assert result.details["findings"][0]["code"] == "audio_silent_segment"  # type: ignore[index]


def test_unterminated_freeze_runs_to_the_end_of_the_media() -> None:
    log = "\n".join(
        [
            "[freezedetect @ 0x1] lavfi.freezedetect.freeze_start: 1.5",
            "[freezedetect @ 0x1] lavfi.freezedetect.freeze_duration: 2",
            "[freezedetect @ 0x1] lavfi.freezedetect.freeze_end: 3.5",
            "[freezedetect @ 0x1] lavfi.freezedetect.freeze_start: 7",
        ]
    )

    segments = _parse_marker_segments(
        log,
        start_pattern=r"lavfi\.freezedetect\.freeze_start:\s*([0-9.]+)",
        end_pattern=r"lavfi\.freezedetect\.freeze_end:\s*([0-9.]+)",
        duration_seconds=10.0,
    )

    assert segments == (MediaInterval(1.5, 3.5), MediaInterval(7.0, 10.0))


def _manifest(*spans: tuple[float, float]) -> dict[str, object]:
    return {
        "overlays": [
            {"visible_start_seconds": start, "visible_end_seconds": end} for start, end in spans
        ]
    }


def test_overlay_coverage_fails_on_the_old_blank_tail_shape() -> None:
    # Three cues pinned to scenes 1-3 of five 2 s scenes: text for 0-6 s only.
    result = evaluate_overlay_coverage_qa(
        rendered_overlay_manifest=_manifest((0, 2), (2, 4), (4, 6)),
        final_duration_seconds=10.0,
    )

    assert result.verdict == QAVerdict.FAIL
    assert qa_result_blocks_readiness(result)
    assert result.details["gaps"] == [
        {"start_seconds": 6.0, "end_seconds": 10.0, "duration_seconds": 4.0}
    ]


def test_overlay_coverage_passes_for_full_coverage_and_tolerates_tiny_gaps() -> None:
    result = evaluate_overlay_coverage_qa(
        rendered_overlay_manifest=_manifest((0, 3), (3.2, 7), (7, 10)),
        final_duration_seconds=10.0,
    )

    assert result.verdict == QAVerdict.PASS
    assert result.details["covered_seconds"] == pytest.approx(9.8)


def test_overlay_coverage_fails_when_the_manifest_has_no_overlays() -> None:
    result = evaluate_overlay_coverage_qa(
        rendered_overlay_manifest={"overlays": []}, final_duration_seconds=8
    )

    assert result.verdict == QAVerdict.FAIL
    assert result.details["gaps"] == [
        {"start_seconds": 0.0, "end_seconds": 8.0, "duration_seconds": 8.0}
    ]


def test_overlay_coverage_skips_without_a_manifest() -> None:
    result = evaluate_overlay_coverage_qa(rendered_overlay_manifest=None, final_duration_seconds=8)

    assert result.verdict == QAVerdict.SKIP
    assert not qa_result_blocks_readiness(result)


def test_rendered_three_beat_reel_has_text_until_the_last_frame(tmp_path: Path) -> None:
    """Render through the real editor: canonical timeline -> drawtext -> coverage QA."""

    from content_lab_editing import build_canonical_timeline, render_basic_vertical_edit

    source = _encode(
        tmp_path / "source.mp4",
        *_moving(10),
        *_tone(10),
        filter_complex="[0:v]null[v];[1:a]anull[a]",
    )
    timeline = build_canonical_timeline(
        timeline_id="timeline-render",
        duration_seconds=10.0,
        source_uri=str(source),
        scene_plan={
            "scenes": [
                {"scene_id": f"s{i}", "start_seconds": 2 * i, "end_seconds": 2 * i + 2}
                for i in range(5)
            ]
        },
        overlay_timeline=[
            {"text": "Hook line", "emphasis": "hook", "start_seconds": 0, "end_seconds": 3},
            {"text": "Useful shift", "emphasis": "value", "start_seconds": 3, "end_seconds": 7},
            {"text": "Next step", "emphasis": "cta", "start_seconds": 7, "end_seconds": 10},
        ],
        spoken_script=None,
    )
    artifact = render_basic_vertical_edit(
        source_uri=source,
        workdir=tmp_path / "edit",
        overlay_timeline=timeline.as_overlay_timeline(),
        expected_timeline_duration_seconds=10.0,
    )

    coverage = evaluate_overlay_coverage_qa(
        rendered_overlay_manifest=artifact.rendered_overlay_manifest.as_json_dict(),
        final_duration_seconds=artifact.duration_seconds,
    )
    content = evaluate_media_content_qa(analysis=analyze_media_content(artifact.final_video_path))

    assert coverage.verdict == QAVerdict.PASS, coverage.details
    assert content.verdict == QAVerdict.PASS, content.details
