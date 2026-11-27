"""Fast Quick Reel export with FFmpeg (instead of screenshotting every frame in Chrome).

The Remotion export paints and screenshots all 480 frames of a 16 s reel in headless Chrome
(20-50 s on 4 cores), so Download waited long after the reel was decided. This builds the
same composed reel with the pipeline's FFmpeg editor:

* backdrop: the energy's gradient, then the page's images on the scene windows (photos fill
  the frame, cut-outs float in the middle band), with motion so nothing freezes;
* captions: the composed ``overlay_timeline`` via the editor's drawtext overlays (the
  pipeline look, not Remotion's kinetic word animation);
* sound: voiceover (configured TTS) over a ducked music bed for the reel's ``music_mood``.

The MP4 and its overlay trace are stored under the same ``quick-reel/<org>/renders/<id>``
prefix as uploaded Remotion renders and QA-checked with the same gates, so Send to Review
attaches the report unchanged. Exports are content-addressed: the same reel is built once.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import subprocess
import tempfile
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from content_lab_editing import (
    CompositionExportPreset,
    CompositionLayer,
    CompositionManifest,
    MotionTransform,
    build_music_bed,
    build_music_provider,
    build_tts_provider,
    build_voiceover_track,
    render_basic_vertical_edit,
    voiceover_lines_from_spoken_script,
)
from content_lab_editing.layered_ffmpeg import compose_layered_reel
from PIL import Image, ImageOps

from content_lab_api.services.quick_reel_media import (
    QuickReelStorage,
    read_quick_reel_qa,
    render_prefix,
    run_quick_reel_qa,
)
from content_lab_creative.generation import ComposedReel
from content_lab_shared.settings import Settings

logger = logging.getLogger(__name__)

EXPORT_SCHEMA_VERSION = 1
WIDTH, HEIGHT, FPS = 1080, 1920, 30
# Same palettes as packages/reel-templates/src/energy.ts.
ENERGY_BACKDROPS: dict[str, tuple[str, str]] = {
    "chill": ("#F6A57D", "#4A2158"),
    "punchy": ("#FF3D71", "#2B0A3D"),
    "dramatic": ("#2A0E0E", "#030303"),
}
_CUTOUT_PX = 760
_COVER_SCALE = 1.1
_COVER_PAN_PX = 40.0


def export_id_for(
    composed: ComposedReel, *, visuals: Sequence[Mapping[str, Any]], settings: Settings
) -> str:
    material = {
        "v": EXPORT_SCHEMA_VERSION,
        "composed": composed.model_dump(mode="json"),
        "visuals": [dict(v) for v in visuals],
        "tts": settings.tts_provider or "auto",
        "music": settings.music_bed_provider or "auto",
    }
    digest = hashlib.sha256(json.dumps(material, sort_keys=True).encode("utf-8")).hexdigest()
    return digest[:20]


def export_quick_reel(
    composed: ComposedReel,
    *,
    org_id: str,
    visuals: Sequence[Mapping[str, Any]],
    settings: Settings,
    storage: QuickReelStorage,
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
) -> dict[str, Any]:
    """Build (or reuse) the MP4 for ``composed``; returns the QA report incl. storage URIs.

    ``visuals`` items: ``{"asset_id", "storage_uri", "fit": "cover" | "cutout"}``.
    """

    export_id = export_id_for(composed, visuals=visuals, settings=settings)
    cached = read_quick_reel_qa(
        org_id=org_id, render_id=export_id, settings=settings, storage=storage
    )
    if cached is not None:
        return {**cached, "export_id": export_id, "cached": True}

    duration = float(composed.duration_seconds)
    with tempfile.TemporaryDirectory(prefix="quick-reel-export-") as tmp:
        workdir = Path(tmp)
        backdrop = workdir / "backdrop.png"
        _gradient(ENERGY_BACKDROPS.get(composed.pace, ENERGY_BACKDROPS["punchy"]), backdrop)
        source_video = workdir / "visuals.mp4"
        t0 = time.monotonic()
        _compose_visuals(
            composed,
            visuals=visuals,
            backdrop=backdrop,
            storage=storage,
            workdir=workdir,
            output_path=source_video,
            ffmpeg_bin=ffmpeg_bin,
        )
        t1 = time.monotonic()
        voice, music = _soundtrack(composed, settings=settings, workdir=workdir)
        t2 = time.monotonic()
        artifact = render_basic_vertical_edit(
            source_uri=source_video,
            workdir=workdir / "edit",
            overlay_timeline=[cue.model_dump(mode="json") for cue in composed.overlay_timeline],
            expected_timeline_duration_seconds=duration,
            voiceover=voice,
            music=music,
            ffmpeg_bin=ffmpeg_bin,
            ffprobe_bin=ffprobe_bin,
        )
        t3 = time.monotonic()
        prefix = render_prefix(settings, org_id=org_id, render_id=export_id)
        storage.put_object(
            data=artifact.final_video_path.read_bytes(),
            storage_uri=f"{prefix}/final_video.mp4",
            content_type="video/mp4",
        )
        trace = artifact.rendered_overlay_manifest.as_json_dict()
    t4 = time.monotonic()
    report = run_quick_reel_qa(
        org_id=org_id,
        render_id=export_id,
        overlay_render_trace=trace,
        soundtrack={
            "soundtrack_id": None,
            "voiceover": None if voice is None else voice.as_dict(),
            "expect_voiceover": bool(composed.spoken_script),
        },
        settings=settings,
        storage=storage,
        ffmpeg_bin=ffmpeg_bin,
        ffprobe_bin=ffprobe_bin,
    )
    timings = {
        "visuals_seconds": round(t1 - t0, 2),
        "soundtrack_seconds": round(t2 - t1, 2),
        "captions_and_mix_seconds": round(t3 - t2, 2),
        "qa_seconds": round(time.monotonic() - t4, 2),
    }
    logger.info("Quick Reel export %s timings %s", export_id, timings)
    return {**report, "export_id": export_id, "cached": False, "timings": timings}


def _compose_visuals(
    composed: ComposedReel,
    *,
    visuals: Sequence[Mapping[str, Any]],
    backdrop: Path,
    storage: QuickReelStorage,
    workdir: Path,
    output_path: Path,
    ffmpeg_bin: str,
) -> None:
    """Compose each scene on its own (backdrop + that scene's image), in parallel, then join.

    One FFmpeg graph for the whole reel processed every image layer on every frame (~26 s for
    16 s). Per scene, each frame has two layers, and scenes use all cores at once.
    """

    scenes = [
        (
            index,
            float(scene.start_seconds),
            min(float(scene.end_seconds), float(composed.duration_seconds)),
        )
        for index, scene in enumerate(composed.scenes)
    ]
    scenes = [item for item in scenes if item[2] > item[1]]
    # Pre-size every still once (aspect kept): FFmpeg then scales same-size frames (a no-op)
    # instead of resampling each image for every frame, and nothing is stretched.
    staged: dict[str, tuple[Path, tuple[int, int]]] = {}
    for visual in visuals:
        asset_id = str(visual["asset_id"])
        key = f"{asset_id}:{visual.get('fit')}"
        if key in staged:
            continue
        body = storage.get_object(storage_uri=str(visual["storage_uri"])).body
        with Image.open(io.BytesIO(body)) as source:
            if visual.get("fit") == "cover":
                box = (round(WIDTH * _COVER_SCALE / 2) * 2, round(HEIGHT * _COVER_SCALE / 2) * 2)
                image = ImageOps.fit(source.convert("RGB"), box, Image.Resampling.LANCZOS)
            else:
                image = source.convert("RGBA")
                image.thumbnail((_CUTOUT_PX, _CUTOUT_PX), Image.Resampling.LANCZOS)
            target = workdir / f"asset-{asset_id}-{visual.get('fit')}.png"
            image.save(target, format="PNG")
            staged[key] = (target, image.size)

    def render(item: tuple[int, float, float]) -> Path:
        index, start, end = item
        visual = visuals[index % len(visuals)] if visuals else None
        manifest, sources = _scene_composition(
            visual, staged=staged, backdrop=backdrop, duration=end - start, index=index
        )
        out = workdir / f"scene-{index + 1:02d}.mp4"
        compose_layered_reel(manifest, asset_sources=sources, output_path=out)
        return out

    with ThreadPoolExecutor(max_workers=max(1, min(len(scenes), os.cpu_count() or 2))) as pool:
        parts = list(pool.map(render, scenes))
    concat_list = workdir / "scenes.txt"
    concat_list.write_text("".join(f"file '{part.as_posix()}'\n" for part in parts))
    completed = subprocess.run(
        [ffmpeg_bin, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-c", "copy", str(output_path)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    if completed.returncode != 0:
        raise RuntimeError(f"Failed to join Quick Reel scenes: {completed.stderr.strip()}")


def _scene_composition(
    visual: Mapping[str, Any] | None,
    *,
    staged: Mapping[str, tuple[Path, tuple[int, int]]],
    backdrop: Path,
    duration: float,
    index: int,
) -> tuple[CompositionManifest, dict[str, dict[str, str]]]:
    sources: dict[str, dict[str, str]] = {
        "backdrop": {"source": str(backdrop), "media_type": "image"}
    }
    layers: list[CompositionLayer] = []
    if visual is not None:
        asset_id = str(visual["asset_id"])
        path, size = staged[f"{asset_id}:{visual.get('fit')}"]
        sources[asset_id] = {"source": str(path), "media_type": "image"}
        cover = visual.get("fit") == "cover"
        if cover:
            # Pre-sized 10% larger than the frame; the pan stays inside the spare width.
            layout = {"x": -((size[0] - WIDTH) // 2), "y": -((size[1] - HEIGHT) // 2), "scale": 1.0}
            motion = MotionTransform(preset="pan_left", amplitude=_COVER_PAN_PX)
        else:
            layout = {"x": (WIDTH - size[0]) // 2, "y": (HEIGHT - size[1]) // 2, "scale": 1.0}
            # float's frequency is cycles per layer lifetime, not per second: ~0.5 Hz bobbing
            # (the default 0.55 cycles over a 4 s scene stalled near its peak and read frozen).
            motion = MotionTransform(preset="float", amplitude=18.0, frequency=0.5 * duration)
        layers.append(
            CompositionLayer(
                layer_id=f"scene-{index + 1}",
                asset_id=asset_id,
                asset_kind="background" if cover else "transparent_cutout_png",
                media_type="image",
                z_index=10,
                start_time=0,
                end_time=duration,
                width=size[0],
                height=size[1],
                mask_mode="none" if cover else "alpha",
                motion_transform=motion,
                **layout,
            )
        )
    manifest = CompositionManifest(
        canvas_width=WIDTH,
        canvas_height=HEIGHT,
        duration=duration,
        fps=FPS,
        background_layer=CompositionLayer(
            layer_id="background",
            asset_id="backdrop",
            asset_kind="background",
            media_type="image",
            z_index=0,
            start_time=0,
            end_time=duration,
            width=WIDTH,
            height=HEIGHT,
            motion_transform=MotionTransform(preset="slow_zoom"),
        ),
        layers=layers,
        audio_layers=[],
        # Intermediate: the caption pass re-encodes it, so near-lossless and fast.
        export_preset=CompositionExportPreset(preset="ultrafast", crf=12),
    )
    return manifest, sources


def _soundtrack(composed: ComposedReel, *, settings: Settings, workdir: Path) -> tuple[Any, Any]:
    duration = float(composed.duration_seconds)
    tts = build_tts_provider(
        tts_provider=settings.tts_provider,
        runway_api_mode=settings.runway_api_mode,
        elevenlabs_api_key=settings.elevenlabs_api_key.get_secret_value(),
        elevenlabs_voice_id=settings.elevenlabs_voice_id,
        elevenlabs_model_id=settings.elevenlabs_model_id,
        elevenlabs_base_url=settings.elevenlabs_base_url,
    )
    music_provider = build_music_provider(
        music_bed_provider=settings.music_bed_provider,
        music_library_dir=settings.music_library_dir or None,
    )
    lines = voiceover_lines_from_spoken_script(
        [beat.model_dump(mode="json") for beat in composed.spoken_script]
    )
    voice = (
        build_voiceover_track(
            lines, provider=tts, duration_seconds=duration, workdir=workdir / "vo"
        )
        if tts is not None
        else None
    )
    music = (
        build_music_bed(
            provider=music_provider,
            mood=composed.music_mood,
            duration_seconds=duration,
            workdir=workdir / "music",
        )
        if music_provider is not None
        else None
    )
    return voice, music


def _gradient(colors: tuple[str, str], path: Path) -> None:
    """Diagonal gradient: a sideways pan changes every frame (a vertical one would look frozen)."""

    top, bottom = (_rgb(colors[0]), _rgb(colors[1]))
    small_w, small_h = 108, 192
    small = Image.new("RGB", (small_w, small_h))
    for y in range(small_h):
        for x in range(small_w):
            t = 0.65 * y / (small_h - 1) + 0.35 * x / (small_w - 1)
            small.putpixel(
                (x, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom, strict=True))
            )
    buffer = io.BytesIO()
    small.resize((WIDTH, HEIGHT), Image.Resampling.BICUBIC).save(buffer, format="PNG")
    path.write_bytes(buffer.getvalue())


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


__all__ = ["ENERGY_BACKDROPS", "export_id_for", "export_quick_reel"]
