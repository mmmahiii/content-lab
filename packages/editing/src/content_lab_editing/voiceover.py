"""Voiceover synthesis: a TTS provider interface, a deterministic mock, and track assembly.

Scripts have always carried ``spoken_script`` beats (start, end, narration) and the canonical
timeline lists ``narration-NNN`` audio tracks, but nothing turned the text into sound, so every
reel was silent. :func:`build_voiceover_track` synthesizes one clip per beat through a
:class:`TTSProvider`, fits each clip inside its beat and lays them on one WAV the length of
the reel. The editor mixes that WAV over the clip audio.

Providers:

* ``mock`` (:class:`MockToneTTSProvider`): a short tone per beat, deterministic for the same
  text, so smoke runs have audible, correctly timed "speech" without a network call. Reels with
  a mock voiceover are tagged so QA reports them as mock audio instead of real speech.
* ``elevenlabs`` (:class:`ElevenLabsTTSProvider`): real speech over HTTPS; needs
  ``ELEVENLABS_API_KEY``.
* ``none``: no voiceover (QA then fails reels whose script has narration).

Selection (:func:`resolve_tts_provider_name`): ``TTS_PROVIDER`` wins; otherwise ``mock`` when
``RUNWAY_API_MODE=mock`` (smoke tests), ``elevenlabs`` when a key is set, else ``none``.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen

VOICEOVER_SAMPLE_RATE = 48_000
VOICEOVER_FILENAME = "voiceover.wav"
MOCK_PROVIDER_NAME = "mock"
ELEVENLABS_PROVIDER_NAME = "elevenlabs"
NO_PROVIDER_NAME = "none"
# Format tag the editor writes on the final MP4 when the voiceover is the mock (see packages/qa).
MOCK_VOICEOVER_TAG = "content_lab_voiceover=mock"

_MOCK_WORDS_PER_SECOND = 2.6
_MOCK_MIN_SECONDS = 0.6
_LINE_FADE_SECONDS = 0.04
_MAX_SPEEDUP = 1.25
_BEAT_LEAD_IN_SECONDS = 0.05


class TTSProvider(Protocol):
    """Turns one line of narration into an audio file."""

    @property
    def name(self) -> str: ...

    def synthesize(self, text: str, *, output_path: Path) -> Path:
        """Write speech for ``text`` to ``output_path`` (any FFmpeg-readable format)."""
        ...


@dataclass(frozen=True, slots=True)
class VoiceoverLine:
    start_seconds: float
    end_seconds: float
    text: str


@dataclass(frozen=True, slots=True)
class PlacedVoiceoverLine:
    start_seconds: float
    end_seconds: float
    text: str
    synthesized_seconds: float
    placed_seconds: float
    tempo: float
    trimmed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "start_seconds": round(self.start_seconds, 3),
            "end_seconds": round(self.end_seconds, 3),
            "text": self.text,
            "synthesized_seconds": round(self.synthesized_seconds, 3),
            "placed_seconds": round(self.placed_seconds, 3),
            "tempo": round(self.tempo, 3),
            "trimmed": self.trimmed,
        }


@dataclass(frozen=True, slots=True)
class VoiceoverTrack:
    path: Path
    provider: str
    duration_seconds: float
    lines: tuple[PlacedVoiceoverLine, ...] = field(default_factory=tuple)

    @property
    def is_mock(self) -> bool:
        return self.provider == MOCK_PROVIDER_NAME

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "mock": self.is_mock,
            "path": str(self.path),
            "duration_seconds": round(self.duration_seconds, 3),
            "lines": [line.as_dict() for line in self.lines],
        }


class MockToneTTSProvider:
    """Deterministic stand-in for speech: a soft tone whose pitch and length follow the text.

    Length is the time the line would take at ~2.6 words/s; pitch is derived from a hash of the
    text. Identical text always produces identical audio for a given FFmpeg build.
    """

    def __init__(self, *, ffmpeg_bin: str = "ffmpeg") -> None:
        self._ffmpeg_bin = ffmpeg_bin

    @property
    def name(self) -> str:
        return MOCK_PROVIDER_NAME

    def synthesize(self, text: str, *, output_path: Path) -> Path:
        words = max(len(text.split()), 1)
        seconds = max(words / _MOCK_WORDS_PER_SECOND, _MOCK_MIN_SECONDS)
        digest = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)
        frequency = 220 + digest % 220  # 220-439 Hz, speech-ish register
        fade = min(0.08, seconds / 4)
        _run(
            [
                self._ffmpeg_bin,
                "-y",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={frequency}:sample_rate={VOICEOVER_SAMPLE_RATE}:duration={seconds:.3f}",
                "-af",
                (
                    # lavfi sine is already 1/8 full scale (~-21 dBFS RMS): speech level.
                    f"afade=t=in:d={fade:.3f},"
                    f"afade=t=out:st={max(seconds - fade, 0):.3f}:d={fade:.3f}"
                ),
                "-ac",
                "1",
                str(output_path),
            ],
            failure_prefix="Mock TTS failed",
        )
        return output_path


class ElevenLabsTTSProvider:
    """ElevenLabs text-to-speech over HTTPS (stdlib only)."""

    def __init__(
        self,
        *,
        api_key: str,
        voice_id: str,
        model_id: str = "eleven_multilingual_v2",
        base_url: str = "https://api.elevenlabs.io",
        timeout_seconds: float = 60.0,
    ) -> None:
        if not api_key.strip():
            raise ValueError("ElevenLabs API key must not be blank")
        if not voice_id.strip():
            raise ValueError("ElevenLabs voice id must not be blank")
        self._api_key = api_key.strip()
        self._voice_id = voice_id.strip()
        self._model_id = model_id
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        return ELEVENLABS_PROVIDER_NAME

    def synthesize(self, text: str, *, output_path: Path) -> Path:
        request = Request(
            f"{self._base_url}/v1/text-to-speech/{self._voice_id}?output_format=mp3_44100_128",
            data=json.dumps({"text": text, "model_id": self._model_id}).encode("utf-8"),
            method="POST",
            headers={
                "xi-api-key": self._api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                body = response.read()
        except HTTPError as err:
            detail = err.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"ElevenLabs TTS HTTP {err.code}: {detail}") from err
        if not body:
            raise RuntimeError("ElevenLabs TTS returned an empty body")
        target = output_path.with_suffix(".mp3")
        target.write_bytes(body)
        return target


def resolve_tts_provider_name(
    *,
    tts_provider: str | None,
    runway_api_mode: str | None,
    elevenlabs_api_key: str | None,
) -> str:
    explicit = (tts_provider or "").strip().lower()
    if explicit:
        if explicit not in {MOCK_PROVIDER_NAME, ELEVENLABS_PROVIDER_NAME, NO_PROVIDER_NAME}:
            raise ValueError(f"Unknown TTS_PROVIDER {explicit!r} (use mock, elevenlabs or none)")
        return explicit
    if (runway_api_mode or "").strip().lower() == "mock":
        return MOCK_PROVIDER_NAME
    if (elevenlabs_api_key or "").strip():
        return ELEVENLABS_PROVIDER_NAME
    return NO_PROVIDER_NAME


def build_tts_provider(
    *,
    tts_provider: str | None,
    runway_api_mode: str | None,
    elevenlabs_api_key: str | None = None,
    elevenlabs_voice_id: str = "",
    elevenlabs_model_id: str = "eleven_multilingual_v2",
    elevenlabs_base_url: str = "https://api.elevenlabs.io",
    ffmpeg_bin: str = "ffmpeg",
) -> TTSProvider | None:
    """Build the configured provider, or ``None`` when voiceover is disabled."""

    name = resolve_tts_provider_name(
        tts_provider=tts_provider,
        runway_api_mode=runway_api_mode,
        elevenlabs_api_key=elevenlabs_api_key,
    )
    if name == MOCK_PROVIDER_NAME:
        return MockToneTTSProvider(ffmpeg_bin=ffmpeg_bin)
    if name == ELEVENLABS_PROVIDER_NAME:
        return ElevenLabsTTSProvider(
            api_key=elevenlabs_api_key or "",
            voice_id=elevenlabs_voice_id,
            model_id=elevenlabs_model_id,
            base_url=elevenlabs_base_url,
        )
    return None


def voiceover_lines_from_spoken_script(
    spoken_script: Sequence[Mapping[str, Any]] | None,
) -> list[VoiceoverLine]:
    lines: list[VoiceoverLine] = []
    for beat in spoken_script or ():
        if not isinstance(beat, Mapping):
            continue
        text = " ".join(str(beat.get("narration") or "").split())
        try:
            start = float(beat.get("start_seconds"))  # type: ignore[arg-type]
            end = float(beat.get("end_seconds"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if text and end > start:
            lines.append(VoiceoverLine(start_seconds=start, end_seconds=end, text=text))
    return lines


def retime_voiceover_lines(
    lines: Sequence[VoiceoverLine],
    *,
    source_duration_seconds: float,
    target_duration_seconds: float,
) -> list[VoiceoverLine]:
    """Scale beat timings when the edit is retimed (e.g. cinematic composition length)."""

    if (
        source_duration_seconds <= 0
        or abs(source_duration_seconds - target_duration_seconds) < 1e-6
    ):
        return list(lines)
    scale = target_duration_seconds / source_duration_seconds
    return [
        VoiceoverLine(line.start_seconds * scale, line.end_seconds * scale, line.text)
        for line in lines
    ]


def build_voiceover_track(
    lines: Sequence[VoiceoverLine],
    *,
    provider: TTSProvider,
    duration_seconds: float,
    workdir: Path,
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
) -> VoiceoverTrack | None:
    """Synthesize each beat and lay the clips on one WAV of exactly ``duration_seconds``.

    A clip longer than its beat is sped up (up to 1.25x) and then trimmed with a short fade,
    so narration never runs into the next beat or past the end of the reel.
    """

    usable = [line for line in lines if line.start_seconds < duration_seconds]
    if not usable:
        return None
    workdir.mkdir(parents=True, exist_ok=True)
    placed: list[PlacedVoiceoverLine] = []
    inputs: list[str] = []
    filters: list[str] = []
    for index, line in enumerate(usable):
        raw_path = provider.synthesize(line.text, output_path=workdir / f"line-{index:03d}.wav")
        synthesized = _probe_duration(raw_path, ffprobe_bin=ffprobe_bin)
        start = min(line.start_seconds + _BEAT_LEAD_IN_SECONDS, duration_seconds)
        slot = max(min(line.end_seconds, duration_seconds) - start, 0.05)
        tempo = 1.0
        if synthesized > slot:
            tempo = min(synthesized / slot, _MAX_SPEEDUP)
        placed_seconds = min(synthesized / tempo, slot)
        trimmed = synthesized / tempo > slot + 1e-3
        inputs += ["-i", str(raw_path)]
        chain = [
            f"aresample={VOICEOVER_SAMPLE_RATE}",
            "aformat=channel_layouts=stereo",
        ]
        if tempo > 1.0:
            chain.append(f"atempo={tempo:.4f}")
        chain.append(f"atrim=0:{placed_seconds:.3f}")
        if trimmed:
            fade_start = max(placed_seconds - 0.12, 0.0)
            chain.append(f"afade=t=out:st={fade_start:.3f}:d=0.12")
        chain.append(f"afade=t=in:d={_LINE_FADE_SECONDS:.3f}")
        delay_ms = int(round(start * 1000))
        chain.append(f"adelay={delay_ms}|{delay_ms}")
        filters.append(f"[{index}:a]{','.join(chain)}[l{index}]")
        placed.append(
            PlacedVoiceoverLine(
                start_seconds=start,
                end_seconds=start + placed_seconds,
                text=line.text,
                synthesized_seconds=synthesized,
                placed_seconds=placed_seconds,
                tempo=tempo,
                trimmed=trimmed,
            )
        )
    labels = "".join(f"[l{index}]" for index in range(len(usable)))
    filters.append(
        f"{labels}amix=inputs={len(usable)}:duration=longest:normalize=0,"
        f"apad,atrim=0:{duration_seconds:.3f},asetpts=N/SR/TB[vo]"
    )
    output_path = workdir / VOICEOVER_FILENAME
    _run(
        [
            ffmpeg_bin,
            "-y",
            "-v",
            "error",
            *inputs,
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[vo]",
            "-ar",
            str(VOICEOVER_SAMPLE_RATE),
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ],
        failure_prefix="Failed to assemble voiceover track",
    )
    return VoiceoverTrack(
        path=output_path,
        provider=provider.name,
        duration_seconds=duration_seconds,
        lines=tuple(placed),
    )


def _probe_duration(path: Path, *, ffprobe_bin: str) -> float:
    completed = _run(
        [
            ffprobe_bin,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        failure_prefix=f"Failed to probe voiceover clip {path}",
    )
    try:
        return float(completed.stdout.strip())
    except ValueError as err:
        raise RuntimeError(f"Voiceover clip {path} has no duration") from err


def _run(command: list[str], *, failure_prefix: str) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"{failure_prefix}: {completed.stderr.strip() or completed.stdout}")
    return completed


__all__ = [
    "ELEVENLABS_PROVIDER_NAME",
    "MOCK_PROVIDER_NAME",
    "MOCK_VOICEOVER_TAG",
    "NO_PROVIDER_NAME",
    "ElevenLabsTTSProvider",
    "MockToneTTSProvider",
    "PlacedVoiceoverLine",
    "TTSProvider",
    "VoiceoverLine",
    "VoiceoverTrack",
    "build_tts_provider",
    "build_voiceover_track",
    "resolve_tts_provider_name",
    "retime_voiceover_lines",
    "voiceover_lines_from_spoken_script",
]
