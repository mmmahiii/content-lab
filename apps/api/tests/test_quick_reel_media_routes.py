"""Quick Reel soundtrack, render upload and QA (PostgreSQL; MinIO replaced by memory)."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_quick_reel_review_routes import _payload, client, scope  # noqa: F401

from content_lab_api.routes import quick_reels as quick_reels_route

RENDER_ID = "0123456789abcdef0123"


@dataclass
class _Obj:
    body: bytes
    content_type: str | None = None


class _MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, _Obj] = {}
        self.puts: list[str] = []

    def get_object(self, *, storage_uri: str) -> _Obj:
        if storage_uri not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return self.objects[storage_uri]

    def head_object(self, *, storage_uri: str) -> _Obj:
        return self.get_object(storage_uri=storage_uri)

    def put_object(self, *, data: bytes, storage_uri: str, content_type: str | None = None) -> _Obj:
        self.puts.append(storage_uri)
        self.objects[storage_uri] = _Obj(data, content_type)
        return self.objects[storage_uri]


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> _MemoryStorage:
    memory = _MemoryStorage()
    monkeypatch.setattr(quick_reels_route, "_quick_reel_storage", lambda: memory)
    monkeypatch.setenv("TTS_PROVIDER", "mock")
    monkeypatch.setenv("MUSIC_BED_PROVIDER", "generated")
    return memory


def _compose_body() -> dict[str, Any]:
    body = _payload()
    return {key: body[key] for key in ("hook", "branches", "selection", "duration_seconds")}


def _page_url(scope: dict[str, Any], suffix: str) -> str:  # noqa: F811
    return f"/orgs/{scope['org']}/pages/{scope['page']}/quick-reel/{suffix}"


def _mean_db(path: Path) -> float:
    err = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "volumedetect", "-f",
         "null", "-"],
        capture_output=True, text=True, check=True,
    ).stderr  # fmt: skip
    match = re.search(r"mean_volume:\s*(-?[0-9.]+)", err)
    assert match is not None
    return float(match.group(1))


def _video(path: Path, *, moving: bool, seconds: float = 4) -> bytes:
    video = (
        f"testsrc2=s=1080x1920:r=30:d={seconds}"
        if moving
        else f"color=black:s=1080x1920:r=30:d={seconds}"
    )
    audio = (
        f"sine=f=330:r=48000:d={seconds}" if moving else f"anullsrc=r=48000:cl=stereo:d={seconds}"
    )
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", video, "-f", "lavfi", "-i", audio,
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-ac", "2", "-shortest", str(path)],
        check=True,
    )  # fmt: skip
    return path.read_bytes()


def _trace(seconds: float) -> dict[str, Any]:
    return {
        "status": "pass",
        "clip_duration_seconds": seconds,
        "frame_height_px": 1920,
        "overlays": [
            {
                "index": 0,
                "role": "hook",
                "source_text": "Crispy potatoes",
                "rendered_text": "Crispy potatoes",
                "visible_start_seconds": 0.0,
                "visible_end_seconds": seconds,
                "clipped": False,
                "safe_area_passed": True,
                "collision_check": "passed",
                "font_size": 72,
            }
        ],
    }


def test_soundtrack_voices_the_reel_over_a_music_bed_and_is_cached(
    client: TestClient,  # noqa: F811
    scope: dict[str, Any],  # noqa: F811
    storage: _MemoryStorage,
    tmp_path: Path,
) -> None:
    first = client.post(_page_url(scope, "soundtrack"), json=_compose_body())
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["voiceover"]["provider"] == "mock"
    assert body["music"]["provider"] == "generated"
    assert body["expect_voiceover"] is True
    composed = client.post(_page_url(scope, "compose"), json=_compose_body())
    assert body["duration_seconds"] == composed.json()["duration_seconds"]
    assert body["download_path"] == (
        f"/orgs/{scope['org']}/quick-reel/soundtracks/{body['soundtrack_id']}/download"
    )
    wav = tmp_path / "soundtrack.wav"
    wav.write_bytes(storage.objects[body["storage_uri"]].body)
    assert _mean_db(wav) > -40

    puts_before = len(storage.puts)
    again = client.post(_page_url(scope, "soundtrack"), json=_compose_body())
    assert again.json()["soundtrack_id"] == body["soundtrack_id"]
    assert len(storage.puts) == puts_before  # cache hit: nothing re-synthesized

    download = client.get(body["download_path"])
    assert download.status_code == 200
    assert body["soundtrack_id"] in download.json()["url"]
    missing = client.get(f"/orgs/{scope['org']}/quick-reel/soundtracks/{'f' * 24}/download")
    assert missing.status_code == 404


def test_uploaded_render_is_stored_qa_checked_and_attached_on_send_to_review(
    client: TestClient,  # noqa: F811
    scope: dict[str, Any],  # noqa: F811
    storage: _MemoryStorage,
    tmp_path: Path,
) -> None:
    upload = client.put(
        _page_url(scope, f"renders/{RENDER_ID}/video"),
        content=_video(tmp_path / "good.mp4", moving=True),
        headers={"content-type": "video/mp4"},
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["video_storage_uri"].endswith(f"/renders/{RENDER_ID}/final_video.mp4")

    qa = client.post(
        _page_url(scope, f"renders/{RENDER_ID}/qa"), json={"overlay_render_trace": _trace(4)}
    )
    assert qa.status_code == 200, qa.text
    report = qa.json()
    gates = {check["gate_name"]: check["verdict"] for check in report["checks"]}
    assert report["status"] == "pass", report["blocking_failures"]
    assert gates["media_content"] == "pass"
    assert gates["audio_content"] == "pass"
    assert gates["overlay_coverage"] == "pass"
    assert gates["package_overlay_render_trace"] == "pass"
    assert any(uri.endswith(f"{RENDER_ID}/qa.json") for uri in storage.objects)

    sent = client.post(
        _page_url(scope, "reels"),
        json=_payload(
            render={
                "render_id": RENDER_ID,
                "duration_seconds": 4,
                "width": 1080,
                "height": 1920,
                "fps": 30,
                "overlay_trace_status": "pass",
            }
        ),
    )
    assert sent.status_code == 201, sent.text
    stored_qa = sent.json()["metadata"]["quick_reel"]["qa"]
    assert sent.json()["status"] == "ready"
    assert stored_qa["status"] == "pass"
    assert stored_qa["video_storage_uri"] == report["video_storage_uri"]
    assert stored_qa["blocking_gates"] == []


def test_a_silent_black_render_fails_qa_and_is_saved_as_qa_failed(
    client: TestClient,  # noqa: F811
    scope: dict[str, Any],  # noqa: F811
    storage: _MemoryStorage,
    tmp_path: Path,
) -> None:
    client.put(
        _page_url(scope, f"renders/{RENDER_ID}/video"),
        content=_video(tmp_path / "bad.mp4", moving=False),
    )
    report = client.post(
        _page_url(scope, f"renders/{RENDER_ID}/qa"), json={"overlay_render_trace": _trace(4)}
    ).json()

    assert report["status"] == "fail"
    assert {item["gate_name"] for item in report["blocking_failures"]} >= {
        "media_content",
        "audio_content",
    }
    sent = client.post(
        _page_url(scope, "reels"),
        json=_payload(
            render={
                "render_id": RENDER_ID,
                "duration_seconds": 4,
                "width": 1080,
                "height": 1920,
                "fps": 30,
                "overlay_trace_status": "pass",
            }
        ),
    )
    assert sent.json()["status"] == "qa_failed"
    assert set(sent.json()["metadata"]["quick_reel"]["qa"]["blocking_gates"]) >= {"media_content"}


def test_upload_and_qa_reject_bad_input(
    client: TestClient,  # noqa: F811
    scope: dict[str, Any],  # noqa: F811
    storage: _MemoryStorage,
    db_session: Session,
) -> None:
    not_mp4 = client.put(_page_url(scope, f"renders/{RENDER_ID}/video"), content=b"not a video")
    bad_id = client.put(_page_url(scope, "renders/NOT-HEX/video"), content=b"x")
    qa_first = client.post(
        _page_url(scope, f"renders/{'a' * 20}/qa"), json={"overlay_render_trace": _trace(4)}
    )
    unknown_soundtrack = client.post(
        _page_url(scope, f"renders/{RENDER_ID}/qa"),
        json={"overlay_render_trace": _trace(4), "soundtrack_id": "b" * 24},
    )

    assert not_mp4.status_code == 422
    assert bad_id.status_code == 422
    assert qa_first.status_code == 409
    assert unknown_soundtrack.status_code == 422


def test_ffmpeg_export_builds_a_voiced_mp4_quickly_and_feeds_send_to_review(
    client: TestClient,  # noqa: F811
    scope: dict[str, Any],  # noqa: F811
    storage: _MemoryStorage,
    db_session: Session,
    tmp_path: Path,
) -> None:
    import io
    import time
    import uuid as uuid_mod

    from PIL import Image

    from content_lab_api.models import Asset

    def png(alpha: bool) -> bytes:
        # Textured, like a real photo: a panned flat colour would honestly look frozen.
        image = Image.effect_noise((900, 900), 60).convert("RGBA" if alpha else "RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    cutout = Asset(
        org_id=scope["org"],
        asset_class="image",
        storage_uri=f"s3://content-lab/a/{uuid_mod.uuid4()}.png",
    )
    photo = Asset(
        org_id=scope["org"],
        asset_class="image",
        storage_uri=f"s3://content-lab/a/{uuid_mod.uuid4()}.png",
    )
    db_session.add_all([cutout, photo])
    db_session.flush()
    storage.objects[cutout.storage_uri] = _Obj(png(True))
    storage.objects[photo.storage_uri] = _Obj(png(False))
    body = {
        **_compose_body(),
        "visuals": [
            {"asset_id": str(cutout.id), "fit": "cutout"},
            {"asset_id": str(photo.id), "fit": "cover"},
        ],
    }

    started = time.monotonic()
    first = client.post(_page_url(scope, "exports"), json=body)
    elapsed = time.monotonic() - started
    assert first.status_code == 200, first.text
    report = first.json()
    gates = {check["gate_name"]: check["verdict"] for check in report["checks"]}
    assert report["cached"] is False
    assert report["status"] in {"pass", "warn"}, report["blocking_failures"]
    assert gates["media_content"] == "pass"
    assert gates["overlay_coverage"] == "pass"
    assert gates["audio_content"] == "warn"  # mock voice
    assert report["duration_seconds"] == pytest.approx(report["duration_seconds"])
    assert elapsed < 120

    again = client.post(_page_url(scope, "exports"), json=body).json()
    assert again["cached"] is True and again["export_id"] == report["export_id"]
    download = client.get(report["download_path"])
    assert download.status_code == 200 and report["export_id"] in download.json()["url"]

    sent = client.post(
        _page_url(scope, "reels"),
        json=_payload(
            visuals=body["visuals"],
            render={
                "render_id": report["export_id"],
                "duration_seconds": report["duration_seconds"],
                "width": 1080,
                "height": 1920,
                "fps": 30,
                "overlay_trace_status": "pass",
            },
        ),
    )
    assert sent.status_code == 201, sent.text
    assert (
        sent.json()["metadata"]["quick_reel"]["qa"]["video_storage_uri"]
        == report["video_storage_uri"]
    )
