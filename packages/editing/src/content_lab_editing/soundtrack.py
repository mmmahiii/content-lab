"""Voiceover + music bed mixing, shared by the pipeline editor and Quick Reel.

The music bed is ducked while the voice speaks (sidechain compression keyed on the voice), so
narration stays intelligible and the gaps between lines are filled instead of silent.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content_lab_editing.music import MusicBed
from content_lab_editing.voiceover import MOCK_VOICEOVER_TAG, VoiceoverTrack

SOUNDTRACK_FILENAME = "soundtrack.wav"
SAMPLE_RATE = 48_000
# Bed level with nobody speaking (~-30 dB mean for the generated pad); ducked further under voice.
MUSIC_BED_GAIN = 0.45
_DUCK = "sidechaincompress=threshold=0.02:ratio=8:attack=15:release=400"


def normalized_input(index: int, *, duration_seconds: float) -> str:
    """Filter chain turning input ``index`` into 48 kHz stereo of exactly the reel length."""

    return (
        f"[{index}:a:0]aresample={SAMPLE_RATE},aformat=channel_layouts=stereo,"
        f"apad,atrim=0:{duration_seconds:.3f},asetpts=N/SR/TB"
    )


def soundtrack_filter(
    *,
    voice_index: int | None,
    music_index: int | None,
    duration_seconds: float,
    output_label: str,
) -> str | None:
    """filter_complex fragment mixing voice and (ducked) music into ``[output_label]``."""

    if voice_index is None and music_index is None:
        return None
    parts: list[str] = []
    if voice_index is not None and music_index is not None:
        parts.append(
            f"{normalized_input(voice_index, duration_seconds=duration_seconds)},asplit=2[st_v][st_key]"
        )
        parts.append(
            f"{normalized_input(music_index, duration_seconds=duration_seconds)},"
            f"volume={MUSIC_BED_GAIN}[st_m]"
        )
        parts.append(f"[st_m][st_key]{_DUCK}[st_md]")
        parts.append(f"[st_v][st_md]amix=inputs=2:duration=first:normalize=0[{output_label}]")
    elif voice_index is not None:
        parts.append(
            f"{normalized_input(voice_index, duration_seconds=duration_seconds)}[{output_label}]"
        )
    else:
        assert music_index is not None
        parts.append(
            f"{normalized_input(music_index, duration_seconds=duration_seconds)},"
            f"volume={MUSIC_BED_GAIN}[{output_label}]"
        )
    return ";".join(parts)


@dataclass(frozen=True, slots=True)
class Soundtrack:
    path: Path
    duration_seconds: float
    voiceover: dict[str, Any] | None
    music: dict[str, Any] | None

    @property
    def is_mock_voiceover(self) -> bool:
        return bool(self.voiceover and self.voiceover.get("mock"))

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "duration_seconds": round(self.duration_seconds, 3),
            "voiceover": self.voiceover,
            "music": self.music,
        }


def mix_soundtrack(
    *,
    voiceover: VoiceoverTrack | None,
    music: MusicBed | None,
    duration_seconds: float,
    output_path: Path,
    ffmpeg_bin: str = "ffmpeg",
) -> Soundtrack | None:
    """Render voice + ducked music to one WAV (Quick Reel attaches it to the Remotion render)."""

    inputs: list[str] = []
    voice_index = music_index = None
    if voiceover is not None:
        voice_index = len(inputs) // 2
        inputs += ["-i", str(voiceover.path)]
    if music is not None:
        music_index = len(inputs) // 2
        inputs += ["-i", str(music.path)]
    graph = soundtrack_filter(
        voice_index=voice_index,
        music_index=music_index,
        duration_seconds=duration_seconds,
        output_label="out",
    )
    if graph is None:
        return None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [ffmpeg_bin, "-y", "-v", "error", *inputs, "-filter_complex", graph]
    command += ["-map", "[out]", "-ar", str(SAMPLE_RATE), "-ac", "2", "-c:a", "pcm_s16le"]
    if voiceover is not None and voiceover.is_mock:
        command += ["-metadata", f"comment={MOCK_VOICEOVER_TAG}"]
    command.append(str(output_path))
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Failed to mix soundtrack: {completed.stderr.strip()}")
    return Soundtrack(
        path=output_path,
        duration_seconds=float(duration_seconds),
        voiceover=voiceover.as_dict() if voiceover is not None else None,
        music=music.as_dict() if music is not None else None,
    )


__all__ = [
    "MUSIC_BED_GAIN",
    "SOUNDTRACK_FILENAME",
    "Soundtrack",
    "mix_soundtrack",
    "normalized_input",
    "soundtrack_filter",
]
