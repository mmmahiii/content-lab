"""Downscaled asset representations (Quick Reel renders decoded 2.6-14 MB PNGs per frame)."""

from __future__ import annotations

import io
import uuid
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.main import app
from content_lab_api.models import Asset, Org
from content_lab_api.routes import assets as assets_route
from content_lab_api.services.asset_representations import representation_uri


@dataclass
class _Obj:
    body: bytes
    content_type: str | None = None


class _MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, _Obj] = {}
        self.gets: list[str] = []

    def get_object(self, *, storage_uri: str) -> _Obj:
        self.gets.append(storage_uri)
        return self.objects[storage_uri]

    def head_object(self, *, storage_uri: str) -> _Obj:
        if storage_uri not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return self.objects[storage_uri]

    def put_object(self, *, data: bytes, storage_uri: str, content_type: str | None = None,
                   metadata: dict[str, str] | None = None) -> _Obj:  # fmt: skip
        self.objects[storage_uri] = _Obj(data, content_type)
        return self.objects[storage_uri]


def _png(size: tuple[int, int], *, alpha: bool) -> bytes:
    image = Image.new(
        "RGBA" if alpha else "RGB", size, (200, 80, 40, 128) if alpha else (200, 80, 40)
    )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_opaque_png_becomes_a_cached_jpeg_no_larger_than_max_px() -> None:
    storage = _MemoryStorage()
    storage.objects["s3://b/assets/bg.png"] = _Obj(_png((4000, 3000), alpha=False))

    uri = representation_uri(storage_uri="s3://b/assets/bg.png", max_px=1080, storage=storage)
    again = representation_uri(storage_uri="s3://b/assets/bg.png", max_px=1080, storage=storage)

    assert uri == again == "s3://b/assets/bg.png.max1080.jpg"
    assert storage.gets == ["s3://b/assets/bg.png"]  # second call is a cache hit
    derived = storage.objects[uri]
    assert derived.content_type == "image/jpeg"
    with Image.open(io.BytesIO(derived.body)) as image:
        assert image.size == (1080, 810)


def test_transparent_cutout_keeps_alpha_as_png() -> None:
    storage = _MemoryStorage()
    storage.objects["s3://b/assets/cut.png"] = _Obj(_png((2400, 2400), alpha=True))

    uri = representation_uri(storage_uri="s3://b/assets/cut.png", max_px=1080, storage=storage)

    assert uri.endswith(".max1080.png")
    with Image.open(io.BytesIO(storage.objects[uri].body)) as image:
        assert image.mode == "RGBA"
        assert image.size == (1080, 1080)


def test_small_images_and_non_images_return_the_original() -> None:
    storage = _MemoryStorage()
    storage.objects["s3://b/assets/icon.png"] = _Obj(_png((400, 300), alpha=False))

    assert representation_uri(
        storage_uri="s3://b/assets/icon.png", max_px=1080, storage=storage
    ) == ("s3://b/assets/icon.png")
    assert representation_uri(storage_uri="s3://b/clips/a.mp4", max_px=1080, storage=storage) == (
        "s3://b/clips/a.mp4"
    )
    assert len(storage.objects) == 1


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_download_route_signs_the_representation_when_max_px_is_given(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = Org(name="Rep Org", slug=f"rep-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    db_session.flush()
    asset = Asset(
        org_id=org.id, asset_class="image", storage_uri="s3://content-lab/assets/x/bg.png"
    )
    db_session.add(asset)
    db_session.flush()
    storage = _MemoryStorage()
    storage.objects[asset.storage_uri] = _Obj(_png((3000, 3000), alpha=False))
    monkeypatch.setattr(assets_route, "_representation_storage", lambda: storage)

    plain = client.get(f"/orgs/{org.id}/assets/{asset.id}/download")
    small = client.get(f"/orgs/{org.id}/assets/{asset.id}/download?max_px=1080")
    bad = client.get(f"/orgs/{org.id}/assets/{asset.id}/download?max_px=10")

    assert plain.status_code == small.status_code == 200
    body: dict[str, Any] = small.json()
    assert plain.json()["storage_uri"] == asset.storage_uri
    assert body["storage_uri"] == f"{asset.storage_uri}.max1080.jpg"
    assert "max1080.jpg" in body["url"]
    assert bad.status_code == 422
