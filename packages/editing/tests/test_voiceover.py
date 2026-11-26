from __future__ import annotations

import io
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from content_lab_editing import render_basic_vertical_edit
from content_lab_editing.voiceover import (
    MOCK_VOICEOVER_TAG,
    ElevenLabsTTSProvider,
    MockToneTTSProvider,
    VoiceoverLine,
    build_tts_provider,
    build_voiceover_track,
    resolve_tts_provider_name,
    retime_voiceover_lines,
    voiceover_lines_from_spoken_script,
)


def _mean_volume_db(path: Path, *, start: float, end: float) -> float:
    completed = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            f"atrim={start}:{end},volumedetect",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    match = re.search(r"mean_volume:\s*(-?[0-9.]+|-inf)", completed.stderr)
    assert match is not None, completed.stderr
    return -120.0 if match.group(1) == "-inf" else float(match.group(1))


def _duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(out.stdout.strip())


def test_mock_tts_is_deterministic_and_length_follows_word_count(tmp_path: Path) -> None:
    provider = MockToneTTSProvider()
    first = provider.synthesize("Try one useful shift today", output_path=tmp_path / "a.wav")
    again = provider.synthesize("Try one useful shift today", output_path=tmp_path / "b.wav")
    longer = provider.synthesize(
        "Close with one concrete next step the viewer can try tonight",
        output_path=tmp_path / "c.wav",
    )

    assert first.read_bytes() == again.read_bytes()
    assert _duration(first) == pytest.approx(5 / 2.6, abs=0.05)
    assert _duration(longer) > _duration(first)


def test_voiceover_track_places_each_beat_and_matches_reel_length(tmp_path: Path) -> None:
    lines = [
        VoiceoverLine(0.0, 3.0, "What would make this worth following"),
        VoiceoverLine(3.0, 7.0, "Try one useful shift today"),
        VoiceoverLine(7.0, 10.0, "Save it for later"),
    ]

    track = build_voiceover_track(
        lines, provider=MockToneTTSProvider(), duration_seconds=10.0, workdir=tmp_path
    )

    assert track is not None
    assert track.is_mock
    assert _duration(track.path) == pytest.approx(10.0, abs=0.02)
    for placed in track.lines:
        assert (
            _mean_volume_db(
                track.path, start=placed.start_seconds + 0.1, end=placed.start_seconds + 0.5
            )
            > -30
        )
    # Silence between the end of beat 1's line and the next beat start.
    gap_start = track.lines[0].end_seconds + 0.05
    assert gap_start < 3.0
    assert _mean_volume_db(track.path, start=gap_start, end=3.0) < -60


def test_long_lines_are_sped_up_then_trimmed_inside_their_beat(tmp_path: Path) -> None:
    long_text = " ".join(["word"] * 20)  # ~7.7 s of mock speech
    track = build_voiceover_track(
        [VoiceoverLine(0.0, 2.0, long_text), VoiceoverLine(2.0, 4.0, "short line")],
        provider=MockToneTTSProvider(),
        duration_seconds=4.0,
        workdir=tmp_path,
    )

    assert track is not None
    first = track.lines[0]
    assert first.tempo == pytest.approx(1.25)
    assert first.trimmed
    assert first.end_seconds <= 2.0 + 1e-6
    assert track.lines[1].start_seconds >= 2.0


def test_lines_starting_after_the_reel_end_are_dropped(tmp_path: Path) -> None:
    track = build_voiceover_track(
        [VoiceoverLine(0.0, 2.0, "hello there"), VoiceoverLine(5.0, 7.0, "too late")],
        provider=MockToneTTSProvider(),
        duration_seconds=3.0,
        workdir=tmp_path,
    )

    assert track is not None
    assert [line.text for line in track.lines] == ["hello there"]


def test_lines_from_spoken_script_skip_blank_and_invalid_beats() -> None:
    lines = voiceover_lines_from_spoken_script(
        [
            {"start_seconds": 0, "end_seconds": 3, "narration": "  Hook   line "},
            {"start_seconds": 3, "end_seconds": 3, "narration": "zero length"},
            {"start_seconds": 3, "end_seconds": 6, "narration": ""},
            {"start_seconds": "x", "end_seconds": 6, "narration": "bad"},
            {"start_seconds": 6, "end_seconds": 9, "narration": "Close"},
        ]
    )

    assert lines == [VoiceoverLine(0.0, 3.0, "Hook line"), VoiceoverLine(6.0, 9.0, "Close")]


def test_retime_scales_beats_to_the_rendered_duration() -> None:
    lines = [VoiceoverLine(0, 5, "a"), VoiceoverLine(5, 10, "b")]

    assert retime_voiceover_lines(lines, source_duration_seconds=10, target_duration_seconds=8) == [
        VoiceoverLine(0, 4, "a"),
        VoiceoverLine(4, 8, "b"),
    ]


@pytest.mark.parametrize(
    ("explicit", "runway_mode", "key", "expected"),
    [
        ("", "mock", "", "mock"),
        ("", "mock", "sk-test", "mock"),  # smoke tests never call a paid provider
        ("", "live", "sk-test", "elevenlabs"),
        ("", "live", "", "none"),
        ("mock", "live", "", "mock"),
        ("none", "mock", "sk-test", "none"),
        ("ELEVENLABS", "mock", "sk-test", "elevenlabs"),
    ],
)
def test_tts_provider_selection(explicit: str, runway_mode: str, key: str, expected: str) -> None:
    assert (
        resolve_tts_provider_name(
            tts_provider=explicit, runway_api_mode=runway_mode, elevenlabs_api_key=key
        )
        == expected
    )


def test_unknown_tts_provider_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown TTS_PROVIDER"):
        build_tts_provider(tts_provider="polly", runway_api_mode="live")


def test_elevenlabs_provider_posts_text_and_writes_mp3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    class _Response(io.BytesIO):
        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

    def _fake_urlopen(request: Any, timeout: float) -> _Response:
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return _Response(b"ID3fake-mp3")

    monkeypatch.setattr("content_lab_editing.voiceover.urlopen", _fake_urlopen)
    provider = build_tts_provider(
        tts_provider="",
        runway_api_mode="live",
        elevenlabs_api_key="sk-test",
        elevenlabs_voice_id="voice-1",
    )

    assert isinstance(provider, ElevenLabsTTSProvider)
    written = provider.synthesize("Hello there", output_path=tmp_path / "line.wav")

    assert written.suffix == ".mp3"
    assert written.read_bytes() == b"ID3fake-mp3"
    assert captured["url"].startswith("https://api.elevenlabs.io/v1/text-to-speech/voice-1")
    assert captured["headers"]["Xi-api-key"] == "sk-test"
    assert captured["body"] == {"text": "Hello there", "model_id": "eleven_multilingual_v2"}


def test_editor_mixes_voiceover_over_a_silent_clip_and_tags_mock_audio(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=180x320:r=24:d=6",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        check=True,
    )
    track = build_voiceover_track(
        [VoiceoverLine(0, 3, "First beat here"), VoiceoverLine(3, 6, "Second beat")],
        provider=MockToneTTSProvider(),
        duration_seconds=6.0,
        workdir=tmp_path / "vo",
    )
    assert track is not None

    artifact = render_basic_vertical_edit(
        source_uri=source,
        workdir=tmp_path / "edit",
        overlay_timeline=[{"text": "Hook", "start_seconds": 0, "end_seconds": 6}],
        voiceover=track,
    )

    tags = json.loads(
        subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format_tags",
                "-of",
                "json",
                str(artifact.final_video_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )["format"]["tags"]
    assert tags.get("comment") == MOCK_VOICEOVER_TAG
    assert artifact.voiceover is not None and artifact.voiceover["provider"] == "mock"
    assert artifact.audio_duration_seconds == pytest.approx(6.0, abs=0.1)
    assert _mean_volume_db(artifact.final_video_path, start=0.2, end=0.8) > -35
