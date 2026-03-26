from __future__ import annotations

import json
import subprocess
from pathlib import Path


def build_fixture_clip(
    *,
    output_path: Path,
    width: int,
    height: int,
    include_audio: bool,
    duration_seconds: float = 1.2,
    video_source: str | None = None,
) -> None:
    source = video_source or f"testsrc=size={width}x{height}:rate=24"
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        source,
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
    run_command(command)


def probe_media(path: Path) -> dict[str, object]:
    completed = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    )
    payload = json.loads(completed.stdout)
    streams = payload["streams"]
    video_stream = next(stream for stream in streams if stream["codec_type"] == "video")
    return {
        "width": int(video_stream["width"]),
        "height": int(video_stream["height"]),
        "has_audio_track": any(stream["codec_type"] == "audio" for stream in streams),
    }


def extract_png_bytes(path: Path, *, timestamp_seconds: float) -> bytes:
    completed = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(path),
            "-ss",
            f"{timestamp_seconds:.3f}",
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "-",
        ],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        details = (
            completed.stderr.decode("utf-8", errors="replace").strip()
            or completed.stdout.decode("utf-8", errors="replace").strip()
            or "no output captured"
        )
        raise RuntimeError(details)
    return completed.stdout


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip() or "no output captured"
        raise RuntimeError(details)
    return completed
