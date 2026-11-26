"""Music bed under the voiceover.

Without a bed, every pause between narration lines was dead air (QA measured 6.5 s of
silence in a 20 s reel). A bed is a WAV the length of the reel; the editor mixes it under the
voice and ducks it while someone speaks (sidechain compression), see ``editor_basic``.

Providers:

* ``generated`` (:class:`GeneratedPadMusicBed`): a soft three-note pad with a slow swell, built
  with FFmpeg. Deterministic for the same mood and length and free of licensing questions; it
  is a placeholder-quality bed, not a soundtrack.
* ``library`` (:class:`LibraryMusicBed`): tracks you are licensed to use, from a folder
  (``MUSIC_LIBRARY_DIR``). The track is chosen deterministically: a file whose name contains a
  word of the mood (e.g. ``upbeat-percussive-01.mp3`` for "upbeat percussive"), otherwise by a
  hash of the mood. It is looped or cut to the reel and faded in and out.
* ``none``: no bed.

Selection (:func:`resolve_music_provider_name`): ``MUSIC_BED_PROVIDER`` wins; otherwise
``library`` when ``MUSIC_LIBRARY_DIR`` points at a folder with audio, else ``generated``.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

MUSIC_BED_FILENAME = "music_bed.wav"
GENERATED_PROVIDER_NAME = "generated"
LIBRARY_PROVIDER_NAME = "library"
NO_MUSIC_PROVIDER_NAME = "none"
DEFAULT_MOOD = "warm lo-fi"
_SAMPLE_RATE = 48_000
_AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"})
# Semitone offsets for a soft major-seventh-ish pad; root comes from the mood.
_PAD_INTERVALS = (0, 4, 7, 11)
_FADE_SECONDS = 1.0


class MusicBedProvider(Protocol):
    @property
    def name(self) -> str: ...

    def render(self, *, mood: str, duration_seconds: float, output_path: Path) -> Path:
        """Write a bed of exactly ``duration_seconds`` (48 kHz stereo WAV) to ``output_path``."""
        ...


@dataclass(frozen=True, slots=True)
class MusicBed:
    path: Path
    provider: str
    mood: str
    duration_seconds: float
    source: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "mood": self.mood,
            "path": str(self.path),
            "duration_seconds": round(self.duration_seconds, 3),
            "source": self.source,
        }


class GeneratedPadMusicBed:
    def __init__(self, *, ffmpeg_bin: str = "ffmpeg") -> None:
        self._ffmpeg_bin = ffmpeg_bin
        self.last_source: str | None = None

    @property
    def name(self) -> str:
        return GENERATED_PROVIDER_NAME

    def render(self, *, mood: str, duration_seconds: float, output_path: Path) -> Path:
        duration = max(float(duration_seconds), 0.1)
        digest = int(hashlib.sha256(_normalize_mood(mood).encode("utf-8")).hexdigest()[:8], 16)
        root = 110.0 * 2 ** ((digest % 12) / 12)  # A2..G#3
        swell = 0.15 + ((digest >> 8) % 5) * 0.05  # 0.15-0.35 Hz
        inputs: list[str] = []
        for interval in _PAD_INTERVALS:
            frequency = root * 2 ** (interval / 12)
            inputs += [
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={frequency:.3f}:sample_rate={_SAMPLE_RATE}:duration={duration:.3f}",
            ]
        voices = len(_PAD_INTERVALS)
        fade = min(_FADE_SECONDS, duration / 4)
        mix = (
            "".join(f"[{i}:a]" for i in range(voices)) + f"amix=inputs={voices}:normalize=0,"
            # Slow swell so the pad is not a frozen drone; level sits well under speech.
            f"tremolo=f={swell:.2f}:d=0.35,volume=0.5,"
            "aformat=channel_layouts=stereo,"
            f"afade=t=in:d={fade:.3f},afade=t=out:st={max(duration - fade, 0):.3f}:d={fade:.3f},"
            f"atrim=0:{duration:.3f}[out]"
        )
        _run(
            [
                self._ffmpeg_bin,
                "-y",
                "-v",
                "error",
                *inputs,
                "-filter_complex",
                mix,
                "-map",
                "[out]",
                "-ar",
                str(_SAMPLE_RATE),
                "-c:a",
                "pcm_s16le",
                str(output_path),
            ],
            failure_prefix="Failed to generate music bed",
        )
        self.last_source = f"generated pad, root {root:.1f} Hz, swell {swell:.2f} Hz"
        return output_path


class LibraryMusicBed:
    def __init__(self, library_dir: Path, *, ffmpeg_bin: str = "ffmpeg") -> None:
        tracks = library_tracks(library_dir)
        if not tracks:
            raise ValueError(f"MUSIC_LIBRARY_DIR {library_dir} has no audio files")
        self._tracks = tracks
        self._ffmpeg_bin = ffmpeg_bin
        self.last_source: str | None = None

    @property
    def name(self) -> str:
        return LIBRARY_PROVIDER_NAME

    def choose_track(self, mood: str) -> Path:
        words = [word for word in re.split(r"[^a-z0-9]+", _normalize_mood(mood)) if word]
        for word in words:
            for track in self._tracks:
                if word in track.stem.lower():
                    return track
        digest = int(hashlib.sha256(_normalize_mood(mood).encode("utf-8")).hexdigest()[:8], 16)
        return self._tracks[digest % len(self._tracks)]

    def render(self, *, mood: str, duration_seconds: float, output_path: Path) -> Path:
        duration = max(float(duration_seconds), 0.1)
        track = self.choose_track(mood)
        fade = min(_FADE_SECONDS, duration / 4)
        _run(
            [
                self._ffmpeg_bin,
                "-y",
                "-v",
                "error",
                "-stream_loop",
                "-1",
                "-i",
                str(track),
                "-af",
                (
                    f"aresample={_SAMPLE_RATE},aformat=channel_layouts=stereo,"
                    f"atrim=0:{duration:.3f},asetpts=N/SR/TB,"
                    f"afade=t=in:d={fade:.3f},"
                    f"afade=t=out:st={max(duration - fade, 0):.3f}:d={fade:.3f}"
                ),
                "-t",
                f"{duration:.3f}",
                "-ar",
                str(_SAMPLE_RATE),
                "-c:a",
                "pcm_s16le",
                str(output_path),
            ],
            failure_prefix=f"Failed to prepare music bed from {track}",
        )
        self.last_source = track.name
        return output_path


def library_tracks(library_dir: Path | None) -> list[Path]:
    if library_dir is None or not library_dir.is_dir():
        return []
    return sorted(
        path
        for path in library_dir.iterdir()
        if path.is_file() and path.suffix.lower() in _AUDIO_EXTENSIONS
    )


def resolve_music_provider_name(
    *,
    music_bed_provider: str | None,
    music_library_dir: str | None,
) -> str:
    explicit = (music_bed_provider or "").strip().lower()
    if explicit:
        if explicit not in {GENERATED_PROVIDER_NAME, LIBRARY_PROVIDER_NAME, NO_MUSIC_PROVIDER_NAME}:
            raise ValueError(
                f"Unknown MUSIC_BED_PROVIDER {explicit!r} (use generated, library or none)"
            )
        return explicit
    if music_library_dir and library_tracks(Path(music_library_dir)):
        return LIBRARY_PROVIDER_NAME
    return GENERATED_PROVIDER_NAME


def build_music_provider(
    *,
    music_bed_provider: str | None,
    music_library_dir: str | None,
    ffmpeg_bin: str = "ffmpeg",
) -> MusicBedProvider | None:
    name = resolve_music_provider_name(
        music_bed_provider=music_bed_provider, music_library_dir=music_library_dir
    )
    if name == GENERATED_PROVIDER_NAME:
        return GeneratedPadMusicBed(ffmpeg_bin=ffmpeg_bin)
    if name == LIBRARY_PROVIDER_NAME:
        if not music_library_dir:
            raise ValueError("MUSIC_BED_PROVIDER=library needs MUSIC_LIBRARY_DIR")
        return LibraryMusicBed(Path(music_library_dir), ffmpeg_bin=ffmpeg_bin)
    return None


def build_music_bed(
    *,
    provider: MusicBedProvider,
    mood: str | None,
    duration_seconds: float,
    workdir: Path,
) -> MusicBed:
    workdir.mkdir(parents=True, exist_ok=True)
    resolved_mood = _normalize_mood(mood or DEFAULT_MOOD)
    path = provider.render(
        mood=resolved_mood,
        duration_seconds=duration_seconds,
        output_path=workdir / MUSIC_BED_FILENAME,
    )
    return MusicBed(
        path=path,
        provider=provider.name,
        mood=resolved_mood,
        duration_seconds=float(duration_seconds),
        source=getattr(provider, "last_source", None),
    )


def _normalize_mood(mood: str) -> str:
    return " ".join(str(mood).lower().split()) or DEFAULT_MOOD


def _run(command: list[str], *, failure_prefix: str) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"{failure_prefix}: {completed.stderr.strip() or completed.stdout}")
    return completed


__all__ = [
    "DEFAULT_MOOD",
    "GENERATED_PROVIDER_NAME",
    "LIBRARY_PROVIDER_NAME",
    "NO_MUSIC_PROVIDER_NAME",
    "GeneratedPadMusicBed",
    "LibraryMusicBed",
    "MusicBed",
    "MusicBedProvider",
    "build_music_bed",
    "build_music_provider",
    "library_tracks",
    "resolve_music_provider_name",
]
