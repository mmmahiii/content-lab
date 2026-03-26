from __future__ import annotations

import subprocess
from pathlib import Path

from content_lab_core.types import QAVerdict
from content_lab_qa.format import (
    FormatQAConstraints,
    evaluate_format_qa,
    evaluate_reel_package_format,
)


def test_evaluate_format_qa_passes_for_canonical_outputs(tmp_path: Path) -> None:
    final_video_path = tmp_path / "final-video.mp4"
    cover_path = tmp_path / "cover.png"

    _build_fixture_clip(
        output_path=final_video_path,
        width=1080,
        height=1920,
        include_audio=True,
        duration_seconds=1.2,
    )
    _build_fixture_cover(output_path=cover_path, width=1080, height=1920)

    report = evaluate_format_qa(
        final_video_path=final_video_path,
        cover_path=cover_path,
    )

    assert report.passed
    assert report.verdict == QAVerdict.PASS
    assert report.failure_reasons == ()
    assert [check.gate_name for check in report.checks] == [
        "final_video_dimensions",
        "final_video_duration",
        "final_video_audio",
        "cover_exists",
        "cover_dimensions",
    ]
    assert all(check.verdict == QAVerdict.PASS for check in report.checks)
    assert report.final_video.width == 1080
    assert report.final_video.height == 1920
    assert report.final_video.has_audio is True
    assert report.cover.width == 1080
    assert report.cover.height == 1920


def test_evaluate_format_qa_reports_explicit_failures(tmp_path: Path) -> None:
    final_video_path = tmp_path / "bad-video.mp4"

    _build_fixture_clip(
        output_path=final_video_path,
        width=720,
        height=1280,
        include_audio=False,
        duration_seconds=1.6,
    )

    report = evaluate_format_qa(
        final_video_path=final_video_path,
        cover_path=tmp_path / "missing-cover.png",
        constraints=FormatQAConstraints(max_duration_seconds=1.0),
    )

    check_by_name = {check.gate_name: check for check in report.checks}

    assert not report.passed
    assert report.verdict == QAVerdict.FAIL
    assert check_by_name["final_video_dimensions"].verdict == QAVerdict.FAIL
    assert check_by_name["final_video_duration"].verdict == QAVerdict.FAIL
    assert check_by_name["final_video_audio"].verdict == QAVerdict.FAIL
    assert check_by_name["cover_exists"].verdict == QAVerdict.FAIL
    assert check_by_name["cover_dimensions"].verdict == QAVerdict.SKIP
    assert any("720x1280" in reason for reason in report.failure_reasons)
    assert any("between 0.100s and 1.000s" in reason for reason in report.failure_reasons)
    assert any("audio track" in reason for reason in report.failure_reasons)
    assert any("Cover image is missing" in reason for reason in report.failure_reasons)


def test_evaluate_format_qa_fails_for_wrong_cover_dimensions(tmp_path: Path) -> None:
    final_video_path = tmp_path / "final-video.mp4"
    cover_path = tmp_path / "cover.png"

    _build_fixture_clip(
        output_path=final_video_path,
        width=1080,
        height=1920,
        include_audio=True,
        duration_seconds=1.2,
    )
    _build_fixture_cover(output_path=cover_path, width=640, height=640)

    report = evaluate_format_qa(
        final_video_path=final_video_path,
        cover_path=cover_path,
    )

    check_by_name = {check.gate_name: check for check in report.checks}

    assert not report.passed
    assert check_by_name["cover_exists"].verdict == QAVerdict.PASS
    assert check_by_name["cover_dimensions"].verdict == QAVerdict.FAIL
    assert "640x640" in check_by_name["cover_dimensions"].message


def test_evaluate_reel_package_format_uses_canonical_filenames(tmp_path: Path) -> None:
    package_directory = tmp_path / "package"
    package_directory.mkdir()

    _build_fixture_clip(
        output_path=package_directory / "final_video.mp4",
        width=1080,
        height=1920,
        include_audio=True,
        duration_seconds=1.2,
    )
    _build_fixture_cover(
        output_path=package_directory / "cover.png",
        width=1080,
        height=1920,
    )

    report = evaluate_reel_package_format(package_directory)

    assert report.passed
    assert report.verdict == QAVerdict.PASS


def _build_fixture_clip(
    *,
    output_path: Path,
    width: int,
    height: int,
    include_audio: bool,
    duration_seconds: float,
) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size={width}x{height}:rate=24",
    ]
    if include_audio:
        command.extend(
            [
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=880:sample_rate=48000",
            ]
        )

    command.extend(["-t", f"{duration_seconds:.3f}"])
    if include_audio:
        command.extend(["-map", "0:v:0", "-map", "1:a:0"])

    command.extend(
        [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
        ]
    )
    if include_audio:
        command.extend(["-c:a", "aac", "-ac", "2", "-ar", "48000"])

    command.append(str(output_path))
    _run_command(command)


def _build_fixture_cover(*, output_path: Path, width: int, height: int) -> None:
    _run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=blue:size={width}x{height}:rate=1",
            "-frames:v",
            "1",
            str(output_path),
        ]
    )


def _run_command(command: list[str]) -> None:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip() or "no output captured"
        raise RuntimeError(details)
