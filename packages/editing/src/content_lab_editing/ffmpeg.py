"""Reusable FFmpeg and FFprobe utilities for the editing package."""

from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
import tempfile
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias, cast

CommandArg: TypeAlias = str | os.PathLike[str]

DEFAULT_TIMEOUT_SECONDS = 300.0

LOGGER = logging.getLogger(__name__)


def _stringify_arg(arg: CommandArg) -> str:
    return os.fspath(arg)


def _stringify_args(args: Sequence[CommandArg]) -> tuple[str, ...]:
    return tuple(_stringify_arg(arg) for arg in args)


def _coerce_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _optional_float(value: object) -> float | None:
    if value in (None, "", "N/A"):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _optional_int(value: object) -> int | None:
    if value in (None, "", "N/A"):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            try:
                return int(float(value))
            except ValueError:
                return None
    return None


def _optional_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return {}


def _sequence(value: object) -> Sequence[object]:
    if isinstance(value, list):
        return cast(list[object], value)
    return ()


def _tags(value: object) -> dict[str, str]:
    tags = _mapping(value)
    return {str(key): str(item) for key, item in tags.items() if item is not None}


def quote_command_arg(arg: CommandArg) -> str:
    """Return a shell-safe representation of a command argument for logs."""

    return shlex.quote(_stringify_arg(arg))


def format_command(args: Sequence[CommandArg]) -> str:
    """Render a command line for logs without changing execution behavior."""

    return " ".join(quote_command_arg(arg) for arg in args)


def escape_ffconcat_path(path: CommandArg) -> str:
    """Escape a path for use in an ffconcat manifest."""

    normalized = Path(_stringify_arg(path)).as_posix()
    return normalized.replace("'", r"'\''")


def build_ffconcat_manifest(paths: Sequence[CommandArg]) -> str:
    """Build ffconcat content with safely escaped file entries."""

    entries = [f"file '{escape_ffconcat_path(path)}'" for path in paths]
    return "\n".join(entries) + ("\n" if entries else "")


@contextmanager
def temporary_path(
    *,
    suffix: str = "",
    prefix: str = "content-lab-editing-",
    directory: CommandArg | None = None,
) -> Iterator[Path]:
    """Yield a filesystem path that is cleaned up when the context exits."""

    target_dir = _stringify_arg(directory) if directory is not None else None
    with tempfile.NamedTemporaryFile(
        prefix=prefix,
        suffix=suffix,
        dir=target_dir,
        delete=False,
    ) as handle:
        path = Path(handle.name)

    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


@dataclass(frozen=True, slots=True)
class FFmpegRunResult:
    """Completed FFmpeg/FFprobe command details."""

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float

    @property
    def display_command(self) -> str:
        return format_command(self.command)


class FFmpegError(RuntimeError):
    """Base class for structured FFmpeg and FFprobe failures."""

    def __init__(
        self,
        message: str,
        *,
        executable: str,
        command: Sequence[str],
        returncode: int | None = None,
        stdout: str = "",
        stderr: str = "",
        timeout_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.executable = executable
        self.command = tuple(command)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.timeout_seconds = timeout_seconds

    @property
    def display_command(self) -> str:
        return format_command(self.command)

    def to_dict(self) -> dict[str, object]:
        return {
            "message": str(self),
            "executable": self.executable,
            "command": list(self.command),
            "display_command": self.display_command,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timeout_seconds": self.timeout_seconds,
        }


class FFmpegBinaryNotFoundError(FFmpegError):
    """Raised when FFmpeg or FFprobe is not available on PATH."""


class FFmpegProcessError(FFmpegError):
    """Raised when a command exits with a non-zero status."""


class FFmpegTimeoutError(FFmpegError):
    """Raised when a command exceeds its timeout."""


class FFprobeParseError(FFmpegError):
    """Raised when FFprobe returns invalid metadata JSON."""


@dataclass(frozen=True, slots=True)
class MediaStreamMetadata:
    """Stream-level metadata returned by FFprobe."""

    index: int | None
    codec_type: str | None
    codec_name: str | None
    codec_long_name: str | None
    width: int | None
    height: int | None
    duration_seconds: float | None
    bit_rate: int | None
    sample_rate: int | None
    channels: int | None
    avg_frame_rate: str | None
    tags: dict[str, str]


@dataclass(frozen=True, slots=True)
class MediaFormatMetadata:
    """Format-level metadata returned by FFprobe."""

    filename: str | None
    format_name: str | None
    format_long_name: str | None
    duration_seconds: float | None
    size_bytes: int | None
    bit_rate: int | None
    tags: dict[str, str]


@dataclass(frozen=True, slots=True)
class MediaMetadata:
    """Normalized media metadata returned by FFprobe."""

    format: MediaFormatMetadata
    streams: tuple[MediaStreamMetadata, ...]
    raw: Mapping[str, object]

    @property
    def video_streams(self) -> tuple[MediaStreamMetadata, ...]:
        return tuple(stream for stream in self.streams if stream.codec_type == "video")

    @property
    def audio_streams(self) -> tuple[MediaStreamMetadata, ...]:
        return tuple(stream for stream in self.streams if stream.codec_type == "audio")


def parse_ffprobe_output(payload: str) -> MediaMetadata:
    """Parse FFprobe JSON into normalized metadata objects."""

    try:
        decoded: object = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise FFprobeParseError(
            f"Unable to parse ffprobe output as JSON: {exc.msg}",
            executable="ffprobe",
            command=("ffprobe",),
            stdout=payload,
        ) from exc

    if not isinstance(decoded, dict):
        raise FFprobeParseError(
            "ffprobe output must decode to an object.",
            executable="ffprobe",
            command=("ffprobe",),
            stdout=payload,
        )

    format_data = _mapping(decoded.get("format"))
    stream_items = _sequence(decoded.get("streams"))

    media_format = MediaFormatMetadata(
        filename=_optional_str(format_data.get("filename")),
        format_name=_optional_str(format_data.get("format_name")),
        format_long_name=_optional_str(format_data.get("format_long_name")),
        duration_seconds=_optional_float(format_data.get("duration")),
        size_bytes=_optional_int(format_data.get("size")),
        bit_rate=_optional_int(format_data.get("bit_rate")),
        tags=_tags(format_data.get("tags")),
    )

    streams = tuple(
        MediaStreamMetadata(
            index=_optional_int(item_data.get("index")),
            codec_type=_optional_str(item_data.get("codec_type")),
            codec_name=_optional_str(item_data.get("codec_name")),
            codec_long_name=_optional_str(item_data.get("codec_long_name")),
            width=_optional_int(item_data.get("width")),
            height=_optional_int(item_data.get("height")),
            duration_seconds=_optional_float(item_data.get("duration")),
            bit_rate=_optional_int(item_data.get("bit_rate")),
            sample_rate=_optional_int(item_data.get("sample_rate")),
            channels=_optional_int(item_data.get("channels")),
            avg_frame_rate=_optional_str(item_data.get("avg_frame_rate")),
            tags=_tags(item_data.get("tags")),
        )
        for item_data in (_mapping(item) for item in stream_items)
    )

    return MediaMetadata(format=media_format, streams=streams, raw=cast(dict[str, object], decoded))


class FFmpegRunner:
    """Execute FFmpeg and FFprobe commands through a shared, safe interface."""

    def __init__(
        self,
        *,
        ffmpeg_bin: str = "ffmpeg",
        ffprobe_bin: str = "ffprobe",
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        logger: logging.Logger | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin
        self.timeout_seconds = timeout_seconds
        self.logger = logger if logger is not None else LOGGER
        self.env = dict(env) if env is not None else None

    def run_ffmpeg(
        self,
        args: Sequence[CommandArg],
        *,
        timeout_seconds: float | None = None,
        cwd: CommandArg | None = None,
        check: bool = True,
    ) -> FFmpegRunResult:
        return self._run(
            executable=self.ffmpeg_bin,
            args=args,
            timeout_seconds=timeout_seconds,
            cwd=cwd,
            check=check,
        )

    def run_ffprobe(
        self,
        args: Sequence[CommandArg],
        *,
        timeout_seconds: float | None = None,
        cwd: CommandArg | None = None,
        check: bool = True,
    ) -> FFmpegRunResult:
        return self._run(
            executable=self.ffprobe_bin,
            args=args,
            timeout_seconds=timeout_seconds,
            cwd=cwd,
            check=check,
        )

    def probe_media(
        self,
        input_path: CommandArg,
        *,
        timeout_seconds: float | None = None,
        cwd: CommandArg | None = None,
    ) -> MediaMetadata:
        result = self.run_ffprobe(
            [
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                input_path,
            ],
            timeout_seconds=timeout_seconds,
            cwd=cwd,
        )

        try:
            return parse_ffprobe_output(result.stdout)
        except FFprobeParseError as exc:
            raise FFprobeParseError(
                str(exc),
                executable=self.ffprobe_bin,
                command=result.command,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            ) from exc

    def _run(
        self,
        *,
        executable: str,
        args: Sequence[CommandArg],
        timeout_seconds: float | None,
        cwd: CommandArg | None,
        check: bool,
    ) -> FFmpegRunResult:
        command = (executable, *_stringify_args(args))
        effective_timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        cwd_text = _stringify_arg(cwd) if cwd is not None else None
        env = os.environ.copy()
        if self.env is not None:
            env.update(self.env)

        self.logger.info("Running media command: %s", format_command(command))
        started_at = time.perf_counter()

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=effective_timeout,
                cwd=cwd_text,
                env=env,
            )
        except FileNotFoundError as exc:
            self.logger.error("Media command executable was not found: %s", executable)
            raise FFmpegBinaryNotFoundError(
                f"Unable to find executable '{executable}'.",
                executable=executable,
                command=command,
                stderr=str(exc),
            ) from exc
        except subprocess.TimeoutExpired as exc:
            self.logger.error(
                "Media command exceeded timeout after %.2fs: %s",
                effective_timeout,
                format_command(command),
            )
            raise FFmpegTimeoutError(
                f"Command timed out after {effective_timeout:.2f}s.",
                executable=executable,
                command=command,
                stdout=_coerce_output(exc.stdout),
                stderr=_coerce_output(exc.stderr),
                timeout_seconds=effective_timeout,
            ) from exc

        duration_seconds = time.perf_counter() - started_at
        result = FFmpegRunResult(
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_seconds=duration_seconds,
        )

        if check and completed.returncode != 0:
            self.logger.error(
                "Media command failed with exit code %s: %s",
                completed.returncode,
                result.display_command,
            )
            raise FFmpegProcessError(
                f"Command exited with status {completed.returncode}.",
                executable=executable,
                command=command,
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )

        self.logger.info(
            "Media command completed in %.2fs with exit code %s.",
            duration_seconds,
            completed.returncode,
        )
        return result


def run_ffmpeg(
    args: Sequence[CommandArg],
    *,
    ffmpeg_bin: str = "ffmpeg",
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    cwd: CommandArg | None = None,
    check: bool = True,
) -> FFmpegRunResult:
    """Convenience wrapper for one-off FFmpeg commands."""

    return FFmpegRunner(ffmpeg_bin=ffmpeg_bin, timeout_seconds=timeout_seconds).run_ffmpeg(
        args,
        timeout_seconds=timeout_seconds,
        cwd=cwd,
        check=check,
    )


def probe_media(
    input_path: CommandArg,
    *,
    ffprobe_bin: str = "ffprobe",
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    cwd: CommandArg | None = None,
) -> MediaMetadata:
    """Convenience wrapper for one-off FFprobe metadata extraction."""

    return FFmpegRunner(ffprobe_bin=ffprobe_bin, timeout_seconds=timeout_seconds).probe_media(
        input_path,
        timeout_seconds=timeout_seconds,
        cwd=cwd,
    )


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "FFmpegBinaryNotFoundError",
    "FFmpegError",
    "FFmpegProcessError",
    "FFmpegRunResult",
    "FFmpegRunner",
    "FFmpegTimeoutError",
    "FFprobeParseError",
    "MediaFormatMetadata",
    "MediaMetadata",
    "MediaStreamMetadata",
    "build_ffconcat_manifest",
    "escape_ffconcat_path",
    "format_command",
    "parse_ffprobe_output",
    "probe_media",
    "quote_command_arg",
    "run_ffmpeg",
    "temporary_path",
]
