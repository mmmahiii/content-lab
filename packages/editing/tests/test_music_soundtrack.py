from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from content_lab_editing import render_basic_vertical_edit
from content_lab_editing.music import (
    GeneratedPadMusicBed,
    LibraryMusicBed,
    build_music_bed,
    build_music_provider,
    resolve_music_provider_name,
)
from content_lab_editing.soundtrack import mix_soundtrack
from content_lab_editing.voiceover import (
    MOCK_VOICEOVER_TAG,
    MockToneTTSProvider,
    VoiceoverLine,
    build_voiceover_track,
)


def _mean_db(path: Path, start: float, end: float) -> float:
    err = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
         f"atrim={start}:{end},volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    ).stderr  # fmt: skip
    match = re.search(r"mean_volume:\s*(-?[0-9.]+|-inf)", err)
    assert match is not None, err
    return -120.0 if match.group(1) == "-inf" else float(match.group(1))


def _duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    return float(out.strip())


def test_generated_bed_is_deterministic_audible_and_exact_length(tmp_path: Path) -> None:
    provider = GeneratedPadMusicBed()
    first = build_music_bed(
        provider=provider, mood="Warm lo-fi", duration_seconds=6, workdir=tmp_path / "a"
    )
    again = build_music_bed(
        provider=provider, mood="warm  lo-fi", duration_seconds=6, workdir=tmp_path / "b"
    )
    other = build_music_bed(provider=provider, mood="calm", duration_seconds=6, workdir=tmp_path / "c")  # fmt: skip

    assert first.path.read_bytes() == again.path.read_bytes()
    assert first.path.read_bytes() != other.path.read_bytes()
    assert _duration(first.path) == pytest.approx(6.0, abs=0.02)
    assert -40 < _mean_db(first.path, 1, 5) < -15
    assert first.mood == "warm lo-fi"


def test_library_bed_picks_a_track_by_mood_word_and_loops_it(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    for name, freq in [("calm-piano.wav", 300), ("upbeat-percussive.wav", 500)]:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=f={freq}:d=2",
             str(library / name)],
            check=True,
        )  # fmt: skip
    (library / "notes.txt").write_text("not audio")

    assert resolve_music_provider_name(music_bed_provider="", music_library_dir=str(library)) == (
        "library"
    )
    provider = build_music_provider(music_bed_provider="", music_library_dir=str(library))
    assert isinstance(provider, LibraryMusicBed)
    assert provider.choose_track("Upbeat percussive").name == "upbeat-percussive.wav"
    assert provider.choose_track("something else").name in {
        "calm-piano.wav",
        "upbeat-percussive.wav",
    }

    bed = build_music_bed(
        provider=provider, mood="upbeat", duration_seconds=5, workdir=tmp_path / "w"
    )

    assert bed.source == "upbeat-percussive.wav"
    assert _duration(bed.path) == pytest.approx(5.0, abs=0.02)  # looped past the 2 s track
    assert _mean_db(bed.path, 2.5, 4.0) > -40


@pytest.mark.parametrize(
    ("explicit", "library", "expected"),
    [("", None, "generated"), ("none", None, "none"), ("GENERATED", None, "generated")],
)
def test_music_provider_selection(explicit: str, library: str | None, expected: str) -> None:
    assert resolve_music_provider_name(music_bed_provider=explicit, music_library_dir=library) == (
        expected
    )


def test_unknown_or_unconfigured_music_provider_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown MUSIC_BED_PROVIDER"):
        resolve_music_provider_name(music_bed_provider="spotify", music_library_dir=None)
    with pytest.raises(ValueError, match="needs MUSIC_LIBRARY_DIR"):
        build_music_provider(music_bed_provider="library", music_library_dir=None)
    with pytest.raises(ValueError, match="no audio files"):
        build_music_provider(music_bed_provider="library", music_library_dir=str(tmp_path))


def test_soundtrack_fills_gaps_between_lines_and_ducks_music_under_voice(tmp_path: Path) -> None:
    voice = build_voiceover_track(
        [VoiceoverLine(0, 2.5, "one two three four five"), VoiceoverLine(5, 8, "six seven eight")],
        provider=MockToneTTSProvider(),
        duration_seconds=8,
        workdir=tmp_path / "vo",
    )
    music = build_music_bed(
        provider=GeneratedPadMusicBed(),
        mood="warm lo-fi",
        duration_seconds=8,
        workdir=tmp_path / "mb",
    )
    assert voice is not None

    mixed = mix_soundtrack(
        voiceover=voice, music=music, duration_seconds=8, output_path=tmp_path / "st.wav"
    )

    assert mixed is not None and mixed.is_mock_voiceover
    gap = _mean_db(mixed.path, 2.6, 4.9)
    speech = _mean_db(mixed.path, 0.2, 1.8)
    assert _mean_db(voice.path, 2.6, 4.9) < -80  # the voice alone is silent here
    assert -45 < gap < -25  # the bed fills the gap
    assert speech - gap > 5  # and sits clearly under the voice
    tags = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format_tags=comment", "-of", "csv=p=0",
         str(mixed.path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip
    assert tags == MOCK_VOICEOVER_TAG


def test_soundtrack_is_none_without_voice_or_music(tmp_path: Path) -> None:
    assert (
        mix_soundtrack(
            voiceover=None, music=None, duration_seconds=3, output_path=tmp_path / "x.wav"
        )
        is None
    )


def test_editor_mixes_music_without_voice_so_the_reel_is_not_silent(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=180x320:r=24:d=4",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)],
        check=True,
    )  # fmt: skip
    music = build_music_bed(
        provider=GeneratedPadMusicBed(), mood="calm", duration_seconds=4, workdir=tmp_path / "mb"
    )

    artifact = render_basic_vertical_edit(
        source_uri=source,
        workdir=tmp_path / "edit",
        overlay_timeline=[{"text": "Hook", "start_seconds": 0, "end_seconds": 4}],
        music=music,
    )

    assert artifact.music is not None and artifact.music["provider"] == "generated"
    assert _mean_db(artifact.final_video_path, 0.5, 3.5) > -45
