"""Quick Reel media: the soundtrack (voice + music bed) and the rendered MP4 with real QA.

Quick Reels render through Remotion in the web server, so they were silent, the MP4 stayed on
that server's disk, and pipeline QA never ran on them. This module is the Python side:

* :func:`build_quick_reel_soundtrack` voices the composed reel's ``spoken_script`` with the
  configured TTS provider and mixes it over a music bed for the reel's ``music_mood`` (the
  same code the pipeline editor uses). The WAV is content-addressed and cached in object
  storage, so re-rendering the same reel never re-synthesizes it.
* :func:`store_quick_reel_video` / :func:`run_quick_reel_qa` keep the exported MP4 and its
  overlay render trace in object storage and run the pipeline's decoded-media QA on them
  (format, blank/static video, silent audio, overlay coverage, overlay render trace). The
  report is stored next to the MP4; Send to Review attaches it to the reel.
"""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from botocore.exceptions import BotoCoreError, ClientError
from content_lab_editing import (
    build_music_bed,
    build_music_provider,
    build_tts_provider,
    build_voiceover_track,
    mix_soundtrack,
    voiceover_lines_from_spoken_script,
)
from content_lab_editing.cover import extract_cover_frame

from content_lab_core.types import QAVerdict
from content_lab_creative.generation import ComposedReel
from content_lab_qa import (
    analyze_media_content,
    evaluate_audio_content_qa,
    evaluate_format_qa,
    evaluate_media_content_qa,
    evaluate_overlay_coverage_qa,
    qa_result_blocks_readiness,
)
from content_lab_qa.package import validate_package_overlay_render_trace
from content_lab_shared.settings import Settings

logger = logging.getLogger(__name__)

SOUNDTRACK_SCHEMA_VERSION = 1
MAX_RENDER_BYTES = 300 * 1024 * 1024


class QuickReelStorage(Protocol):
    def get_object(self, *, storage_uri: str) -> Any: ...

    def head_object(self, *, storage_uri: str) -> Any: ...

    def put_object(
        self, *, data: bytes, storage_uri: str, content_type: str | None = None
    ) -> Any: ...


def _prefix(settings: Settings, org_id: str) -> str:
    return f"s3://{settings.minio_bucket}/quick-reel/{org_id}"


def soundtrack_uri(settings: Settings, *, org_id: str, soundtrack_id: str) -> str:
    return f"{_prefix(settings, org_id)}/soundtracks/{soundtrack_id}.wav"


def render_prefix(settings: Settings, *, org_id: str, render_id: str) -> str:
    return f"{_prefix(settings, org_id)}/renders/{render_id}"


def build_quick_reel_soundtrack(
    composed: ComposedReel,
    *,
    org_id: str,
    settings: Settings,
    storage: QuickReelStorage,
) -> dict[str, Any]:
    """Voice + music WAV for ``composed`` (cached by content). Returns its manifest."""

    tts = build_tts_provider(
        tts_provider=settings.tts_provider,
        runway_api_mode=settings.runway_api_mode,
        elevenlabs_api_key=settings.elevenlabs_api_key.get_secret_value(),
        elevenlabs_voice_id=settings.elevenlabs_voice_id,
        elevenlabs_model_id=settings.elevenlabs_model_id,
        elevenlabs_base_url=settings.elevenlabs_base_url,
    )
    music = build_music_provider(
        music_bed_provider=settings.music_bed_provider,
        music_library_dir=settings.music_library_dir or None,
    )
    lines = voiceover_lines_from_spoken_script(
        [beat.model_dump(mode="json") for beat in composed.spoken_script]
    )
    key_material = {
        "v": SOUNDTRACK_SCHEMA_VERSION,
        "duration": composed.duration_seconds,
        "lines": [(line.start_seconds, line.end_seconds, line.text) for line in lines],
        "mood": composed.music_mood,
        "tts": None if tts is None else tts.name,
        "music": None if music is None else music.name,
        "voice_id": settings.elevenlabs_voice_id if tts is not None else None,
    }
    soundtrack_id = hashlib.sha256(
        json.dumps(key_material, sort_keys=True).encode("utf-8")
    ).hexdigest()[:24]
    uri = soundtrack_uri(settings, org_id=org_id, soundtrack_id=soundtrack_id)
    manifest_uri = f"{uri}.json"
    cached = _read_json(storage, manifest_uri)
    if cached is not None:
        return cached

    manifest: dict[str, Any] = {
        "soundtrack_id": soundtrack_id,
        "duration_seconds": composed.duration_seconds,
        "storage_uri": None,
        "voiceover": None,
        "music": None,
        "expect_voiceover": bool(lines),
    }
    with tempfile.TemporaryDirectory(prefix="quick-reel-soundtrack-") as tmp:
        workdir = Path(tmp)
        voice = (
            build_voiceover_track(
                lines,
                provider=tts,
                duration_seconds=float(composed.duration_seconds),
                workdir=workdir / "voice",
            )
            if tts is not None
            else None
        )
        bed = (
            build_music_bed(
                provider=music,
                mood=composed.music_mood,
                duration_seconds=float(composed.duration_seconds),
                workdir=workdir / "music",
            )
            if music is not None
            else None
        )
        mixed = mix_soundtrack(
            voiceover=voice,
            music=bed,
            duration_seconds=float(composed.duration_seconds),
            output_path=workdir / "soundtrack.wav",
        )
        if mixed is not None:
            storage.put_object(
                data=mixed.path.read_bytes(), storage_uri=uri, content_type="audio/wav"
            )
            manifest["storage_uri"] = uri
            manifest["voiceover"] = _without_paths(mixed.voiceover)
            manifest["music"] = _without_paths(mixed.music)
    storage.put_object(
        data=json.dumps(manifest, sort_keys=True).encode("utf-8"),
        storage_uri=manifest_uri,
        content_type="application/json",
    )
    return manifest


def read_soundtrack_manifest(
    *, org_id: str, soundtrack_id: str, settings: Settings, storage: QuickReelStorage
) -> dict[str, Any] | None:
    uri = soundtrack_uri(settings, org_id=org_id, soundtrack_id=soundtrack_id)
    return _read_json(storage, f"{uri}.json")


def store_quick_reel_video(
    data: bytes, *, org_id: str, render_id: str, settings: Settings, storage: QuickReelStorage
) -> str:
    if not data:
        raise ValueError("Render upload is empty")
    if len(data) > MAX_RENDER_BYTES:
        raise ValueError(f"Render upload is larger than {MAX_RENDER_BYTES // (1024 * 1024)} MB")
    if data[4:8] != b"ftyp":
        raise ValueError("Render upload is not an MP4")
    uri = f"{render_prefix(settings, org_id=org_id, render_id=render_id)}/final_video.mp4"
    storage.put_object(data=data, storage_uri=uri, content_type="video/mp4")
    return uri


def run_quick_reel_qa(
    *,
    org_id: str,
    render_id: str,
    overlay_render_trace: Mapping[str, Any],
    soundtrack: Mapping[str, Any] | None,
    settings: Settings,
    storage: QuickReelStorage,
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
) -> dict[str, Any]:
    """Decode the stored MP4 and run pipeline QA on it; the report is stored and returned."""

    prefix = render_prefix(settings, org_id=org_id, render_id=render_id)
    video = storage.get_object(storage_uri=f"{prefix}/final_video.mp4")
    with tempfile.TemporaryDirectory(prefix="quick-reel-qa-") as tmp:
        video_path = Path(tmp) / "final_video.mp4"
        video_path.write_bytes(video.body)
        cover = extract_cover_frame(
            video_path=video_path,
            output_path=Path(tmp) / "cover.png",
            ffmpeg_bin=ffmpeg_bin,
            ffprobe_bin=ffprobe_bin,
        )
        format_report = evaluate_format_qa(
            final_video_path=video_path, cover_path=cover.image_path, ffprobe_bin=ffprobe_bin
        )
        analysis = analyze_media_content(video_path, ffmpeg_bin=ffmpeg_bin, ffprobe_bin=ffprobe_bin)
    trace_payload = dict(overlay_render_trace)
    checks = [
        *format_report.checks,
        evaluate_media_content_qa(analysis=analysis),
        evaluate_audio_content_qa(
            analysis=analysis,
            voiceover=(soundtrack or {}).get("voiceover"),
            expect_voiceover=bool((soundtrack or {}).get("expect_voiceover")),
        ),
        evaluate_overlay_coverage_qa(
            rendered_overlay_manifest=trace_payload,
            final_duration_seconds=analysis.duration_seconds,
        ),
        validate_package_overlay_render_trace(
            {"overlay_render_trace": trace_payload, "duration_seconds": analysis.duration_seconds}
        ),
    ]
    blocking = [check.as_payload() for check in checks if qa_result_blocks_readiness(check)]
    warnings = [check.gate_name for check in checks if check.verdict == QAVerdict.WARN]
    status = "fail" if blocking else ("warn" if warnings else "pass")
    report = {
        "status": status,
        "render_id": render_id,
        "video_storage_uri": f"{prefix}/final_video.mp4",
        "trace_storage_uri": f"{prefix}/overlay_render_trace.json",
        "soundtrack_id": None if soundtrack is None else soundtrack.get("soundtrack_id"),
        "duration_seconds": round(analysis.duration_seconds, 3),
        "checks": [check.as_payload() for check in checks],
        "blocking_failures": blocking,
        "warnings": warnings,
    }
    storage.put_object(
        data=json.dumps(trace_payload, sort_keys=True).encode("utf-8"),
        storage_uri=f"{prefix}/overlay_render_trace.json",
        content_type="application/json",
    )
    storage.put_object(
        data=json.dumps(report, sort_keys=True).encode("utf-8"),
        storage_uri=f"{prefix}/qa.json",
        content_type="application/json",
    )
    return report


def read_quick_reel_qa(
    *, org_id: str, render_id: str, settings: Settings, storage: QuickReelStorage
) -> dict[str, Any] | None:
    prefix = render_prefix(settings, org_id=org_id, render_id=render_id)
    return _read_json(storage, f"{prefix}/qa.json")


def _read_json(storage: QuickReelStorage, uri: str) -> dict[str, Any] | None:
    try:
        obj = storage.get_object(storage_uri=uri)
    except (ClientError, KeyError):
        return None
    except BotoCoreError as exc:  # storage unreachable: report "not found", but say why
        logger.warning("Could not read %s: %s", uri, exc)
        return None
    try:
        payload = json.loads(obj.body.decode("utf-8"))
    except (ValueError, AttributeError):
        return None
    return payload if isinstance(payload, dict) else None


def _without_paths(payload: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    return {key: value for key, value in payload.items() if key != "path"}


__all__ = [
    "MAX_RENDER_BYTES",
    "build_quick_reel_soundtrack",
    "read_quick_reel_qa",
    "read_soundtrack_manifest",
    "render_prefix",
    "run_quick_reel_qa",
    "soundtrack_uri",
    "store_quick_reel_video",
]
