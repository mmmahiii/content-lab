from __future__ import annotations

from content_lab_assets.registry import AssetRecord, AssetRegistry
from content_lab_core.types import AssetKind


class TestAssetRecord:
    def test_creation(self) -> None:
        rec = AssetRecord(
            name="hero.png",
            kind=AssetKind.IMAGE,
            content_hash="sha256:abc123",
            storage_uri="s3://content-lab/assets/hero.png",
            size_bytes=2048,
            tags=["hero", "banner"],
        )
        assert rec.name == "hero.png"
        assert rec.kind == AssetKind.IMAGE
        assert rec.size_bytes == 2048
        assert "hero" in rec.tags

    def test_default_tags(self) -> None:
        rec = AssetRecord(
            name="clip.mp4",
            kind=AssetKind.VIDEO,
            content_hash="sha256:def456",
            storage_uri="s3://content-lab/assets/clip.mp4",
        )
        assert rec.tags == []
        assert rec.size_bytes == 0


class TestAssetRegistryProtocol:
    def test_is_runtime_checkable(self) -> None:
        assert hasattr(AssetRegistry, "__protocol_attrs__") or hasattr(
            AssetRegistry, "__abstractmethods__"
        )

    def test_dummy_implementation(self) -> None:
        class InMemoryRegistry:
            def __init__(self) -> None:
                self._store: dict[str, AssetRecord] = {}

            def register(self, record: AssetRecord) -> AssetRecord:
                self._store[record.content_hash] = record
                return record

            def lookup_by_hash(self, content_hash: str) -> AssetRecord | None:
                return self._store.get(content_hash)

        registry = InMemoryRegistry()
        rec = AssetRecord(
            name="test.png",
            kind=AssetKind.IMAGE,
            content_hash="sha256:xyz",
            storage_uri="s3://b/k",
        )
        registered = registry.register(rec)
        assert registered.content_hash == rec.content_hash
        assert registry.lookup_by_hash("sha256:xyz") is not None
        assert registry.lookup_by_hash("sha256:missing") is None
