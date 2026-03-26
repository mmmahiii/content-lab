from __future__ import annotations

import os
import stat
import textwrap
from pathlib import Path

import pytest

from content_lab_editing.ffmpeg import (
    FFmpegProcessError,
    FFmpegRunner,
    FFmpegTimeoutError,
    FFprobeParseError,
    build_ffconcat_manifest,
    parse_ffprobe_output,
    temporary_path,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _create_wrapper(
    tmp_path: Path,
    name: str,
    *,
    windows_body: str,
    posix_body: str,
) -> Path:
    if os.name == "nt":
        wrapper_path = tmp_path / f"{name}.cmd"
        wrapper_path.write_text(
            textwrap.dedent(windows_body).strip() + "\r\n",
            encoding="utf-8",
        )
        return wrapper_path

    wrapper_path = tmp_path / name
    wrapper_path.write_text(textwrap.dedent(posix_body).strip() + "\n", encoding="utf-8")
    wrapper_path.chmod(wrapper_path.stat().st_mode | stat.S_IEXEC)
    return wrapper_path


class TestFFmpegRunner:
    def test_run_ffmpeg_returns_process_details(self, tmp_path: Path) -> None:
        ffmpeg_bin = _create_wrapper(
            tmp_path,
            "fake_ffmpeg_ok",
            windows_body="""
            @echo off
            echo encoded
            >&2 echo ffmpeg-warning
            exit /b 0
            """,
            posix_body="""
            #!/usr/bin/env sh
            echo encoded
            echo ffmpeg-warning 1>&2
            exit 0
            """,
        )
        runner = FFmpegRunner(ffmpeg_bin=str(ffmpeg_bin), timeout_seconds=2.0)

        result = runner.run_ffmpeg(["-i", "input.mp4", "output.mp4"])

        assert result.returncode == 0
        assert result.stdout.strip() == "encoded"
        assert result.stderr.strip() == "ffmpeg-warning"
        assert result.command[0] == str(ffmpeg_bin)
        assert result.duration_seconds >= 0

    def test_run_ffmpeg_raises_structured_error_on_non_zero_exit(self, tmp_path: Path) -> None:
        ffmpeg_bin = _create_wrapper(
            tmp_path,
            "fake_ffmpeg_fail",
            windows_body="""
            @echo off
            echo nope
            >&2 echo failed
            exit /b 7
            """,
            posix_body="""
            #!/usr/bin/env sh
            echo nope
            echo failed 1>&2
            exit 7
            """,
        )
        runner = FFmpegRunner(ffmpeg_bin=str(ffmpeg_bin), timeout_seconds=2.0)

        with pytest.raises(FFmpegProcessError) as exc_info:
            runner.run_ffmpeg(["-i", "input.mp4", "output.mp4"])

        error = exc_info.value
        assert error.returncode == 7
        assert error.stdout.strip() == "nope"
        assert error.stderr.strip() == "failed"
        assert error.to_dict()["display_command"]

    def test_run_ffmpeg_raises_timeout_error(self, tmp_path: Path) -> None:
        ffmpeg_bin = _create_wrapper(
            tmp_path,
            "fake_ffmpeg_slow",
            windows_body="""
            @echo off
            ping -n 3 127.0.0.1 > nul
            exit /b 0
            """,
            posix_body="""
            #!/usr/bin/env sh
            sleep 1
            exit 0
            """,
        )
        runner = FFmpegRunner(ffmpeg_bin=str(ffmpeg_bin), timeout_seconds=1.0)

        with pytest.raises(FFmpegTimeoutError) as exc_info:
            runner.run_ffmpeg(["-i", "input.mp4", "output.mp4"], timeout_seconds=0.1)

        assert exc_info.value.timeout_seconds == pytest.approx(0.1)
        assert exc_info.value.command[0] == str(ffmpeg_bin)

    def test_probe_media_parses_metadata_fixture(self, tmp_path: Path) -> None:
        payload_path = FIXTURES_DIR / "ffprobe_sample.json"
        argv_capture_path = tmp_path / "captured-argv.txt"
        ffprobe_bin = _create_wrapper(
            tmp_path,
            "fake_ffprobe",
            windows_body=f"""
            @echo off
            > "{argv_capture_path}" echo %~7
            type "{payload_path}"
            exit /b 0
            """,
            posix_body=f"""
            #!/usr/bin/env sh
            printf '%s\n' "$7" > "{argv_capture_path}"
            cat "{payload_path}"
            exit 0
            """,
        )
        runner = FFmpegRunner(ffprobe_bin=str(ffprobe_bin), timeout_seconds=2.0)
        media_path = tmp_path / "clip one's cut.mp4"

        metadata = runner.probe_media(media_path)

        assert metadata.format.format_name == "mov,mp4,m4a,3gp,3g2,mj2"
        assert metadata.format.duration_seconds == pytest.approx(12.345)
        assert metadata.video_streams[0].width == 1080
        assert metadata.video_streams[0].height == 1920
        assert metadata.audio_streams[0].sample_rate == 48000
        assert metadata.audio_streams[0].channels == 2
        assert argv_capture_path.read_text(encoding="utf-8").strip() == str(media_path)

    def test_parse_ffprobe_output_raises_structured_error_for_invalid_json(self) -> None:
        with pytest.raises(FFprobeParseError) as exc_info:
            parse_ffprobe_output("not-json")

        assert "Unable to parse ffprobe output" in str(exc_info.value)

    def test_build_ffconcat_manifest_and_temporary_path_are_safe(self, tmp_path: Path) -> None:
        first_path = tmp_path / "clip one's cut.mp4"
        second_path = tmp_path / "clip two.mp4"

        manifest = build_ffconcat_manifest([first_path, second_path])

        assert manifest.startswith("file '")
        assert first_path.as_posix().replace("'", r"'\''") in manifest
        assert r"'\''" in manifest
        assert second_path.as_posix() in manifest

        with temporary_path(suffix=".ffconcat", directory=tmp_path) as manifest_path:
            manifest_path.write_text(manifest, encoding="utf-8")
            assert manifest_path.exists()

        assert not manifest_path.exists()
