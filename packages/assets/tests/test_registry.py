from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any, TypedDict

from content_lab_assets.providers.runway.jobs import build_runway_job_external_ref
from content_lab_assets.registry import (
    AssetKey,
    AssetRecord,
    AssetRegistry,
    RegistryAsset,
    RegistryAssetGenParams,
    RegistryGenerationIntentRecord,
    build_asset_key,
    build_generation_idempotency_key,
    build_generation_payload,
    resolve_phase1_asset,
)
from content_lab_core.types import AssetKind


class ResolveRequest(TypedDict):
    asset_class: str
    provider: str
    model: str
    prompt: str
    negative_prompt: str
    seed: int
    duration_seconds: float
    fps: int
    ratio: str
    motion: dict[str, Any]
    init_image_hash: str
    reference_asset_ids: list[str]
    metadata: dict[str, Any]


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


class InMemoryPhase1Store:
    def __init__(self) -> None:
        self.asset: RegistryAsset | None = None
        self.gen_params: RegistryAssetGenParams | None = None
        self.intent_creations = 0

    def get_asset_by_key_hash(
        self,
        *,
        org_id: uuid.UUID,
        asset_key_hash: str,
    ) -> RegistryAsset | None:
        if self.asset is None:
            return None
        if self.asset.org_id != org_id or self.asset.asset_key_hash != asset_key_hash:
            return None
        return self.asset.model_copy(deep=True)

    def get_generation_params(
        self,
        *,
        asset_id: uuid.UUID,
        asset_key_hash: str,
    ) -> RegistryAssetGenParams | None:
        if self.gen_params is None:
            return None
        if self.gen_params.asset_id != asset_id or self.gen_params.asset_key_hash != asset_key_hash:
            return None
        return self.gen_params.model_copy(deep=True)

    def ensure_generation_intent(
        self,
        *,
        org_id: uuid.UUID,
        asset_key: AssetKey,
        payload: Mapping[str, Any],
    ) -> RegistryGenerationIntentRecord:
        if self.asset is None:
            asset_id = uuid.uuid4()
            self.asset = RegistryAsset(
                asset_id=asset_id,
                org_id=org_id,
                asset_class=asset_key.canonical_params["asset_class"],
                status="staged",
                source=asset_key.canonical_params["provider"],
                storage_uri=f"s3://content-lab/assets/raw/{asset_id}/source.bin",
                asset_key=asset_key.asset_key,
                asset_key_hash=asset_key.asset_key_hash,
                metadata={"intent": dict(payload)},
            )
            self.gen_params = RegistryAssetGenParams(
                asset_id=asset_id,
                seq=0,
                asset_key_hash=asset_key.asset_key_hash,
                canonical_params=dict(asset_key.canonical_params),
            )
            self.intent_creations += 1

        return RegistryGenerationIntentRecord(
            asset_id=self.asset.asset_id,
            org_id=self.asset.org_id,
            asset_class=self.asset.asset_class,
            status=self.asset.status,
            source=self.asset.source,
            storage_uri=self.asset.storage_uri,
            asset_key=asset_key.asset_key,
            asset_key_hash=asset_key.asset_key_hash,
            idempotency_key=build_generation_idempotency_key(
                asset_key_hash=asset_key.asset_key_hash
            ),
            payload=dict(self.asset.metadata.get("intent", payload)),
            canonical_params=dict(self.gen_params.canonical_params if self.gen_params else {}),
            created=self.intent_creations == 1,
        )


def _resolve_request() -> ResolveRequest:
    return {
        "asset_class": "clip",
        "provider": "Runway",
        "model": "GEN4.5",
        "prompt": "  Hero   launch  shot ",
        "negative_prompt": "  no text overlays ",
        "seed": 7,
        "duration_seconds": 6.0,
        "fps": 24,
        "ratio": " 9:16 ",
        "motion": {"camera": {"pan": " slow left "}, "strength": 0.6},
        "init_image_hash": " ABC123 ",
        "reference_asset_ids": [str(uuid.uuid4())],
        "metadata": {"shot_id": "hero-1"},
    }


def test_resolve_phase1_asset_reuses_ready_asset_without_creating_new_intent() -> None:
    org_id = uuid.uuid4()
    store = InMemoryPhase1Store()
    request = _resolve_request()

    generated = resolve_phase1_asset(
        store,
        org_id=org_id,
        asset_class=str(request["asset_class"]),
        provider=str(request["provider"]),
        model=str(request["model"]),
        prompt=str(request["prompt"]),
        negative_prompt=str(request["negative_prompt"]),
        seed=int(request["seed"]),
        duration_seconds=float(request["duration_seconds"]),
        fps=int(request["fps"]),
        ratio=str(request["ratio"]),
        motion=request["motion"],
        init_image_hash=str(request["init_image_hash"]),
        reference_asset_ids=request["reference_asset_ids"],
        request_payload=request,
    )
    assert generated.decision == "generate"
    assert store.asset is not None
    store.asset = store.asset.model_copy(
        update={
            "status": "ready",
            "storage_uri": "s3://content-lab/assets/derived/existing.mp4",
        }
    )
    store.intent_creations = 1

    reused = resolve_phase1_asset(
        store,
        org_id=org_id,
        asset_class="clip",
        provider="runway",
        model="gen4.5",
        prompt="Hero launch shot",
        negative_prompt="no text overlays",
        seed=7,
        duration_seconds=6,
        fps=24,
        ratio="9:16",
        motion=request["motion"],
        init_image_hash="abc123",
        reference_asset_ids=request["reference_asset_ids"],
        request_payload=request,
    )

    assert reused.decision == "reuse_exact"
    assert reused.asset_id == generated.generation_intent.asset_id
    assert reused.storage_uri == "s3://content-lab/assets/derived/existing.mp4"
    assert store.intent_creations == 1


def test_resolve_phase1_asset_reuses_existing_staged_intent_for_identical_request() -> None:
    org_id = uuid.uuid4()
    store = InMemoryPhase1Store()
    request = _resolve_request()

    first = resolve_phase1_asset(
        store,
        org_id=org_id,
        asset_class=str(request["asset_class"]),
        provider=str(request["provider"]),
        model=str(request["model"]),
        prompt=str(request["prompt"]),
        negative_prompt=str(request["negative_prompt"]),
        seed=int(request["seed"]),
        duration_seconds=float(request["duration_seconds"]),
        fps=int(request["fps"]),
        ratio=str(request["ratio"]),
        motion=request["motion"],
        init_image_hash=str(request["init_image_hash"]),
        reference_asset_ids=request["reference_asset_ids"],
        request_payload=request,
    )
    second = resolve_phase1_asset(
        store,
        org_id=org_id,
        asset_class="clip",
        provider=" runway ",
        model=" gen4.5 ",
        prompt="Hero launch shot",
        negative_prompt="no text overlays",
        seed=7,
        duration_seconds=6,
        fps=24,
        ratio="9:16",
        motion=request["motion"],
        init_image_hash="abc123",
        reference_asset_ids=request["reference_asset_ids"],
        request_payload=_resolve_request(),
    )

    assert first.decision == "generate"
    assert second.decision == "generate"
    assert first.generation_intent.asset_id == second.generation_intent.asset_id
    assert first.generation_intent.idempotency_key == second.generation_intent.idempotency_key
    assert store.intent_creations == 1
    assert store.gen_params is not None
    assert store.gen_params.seq == 0


def test_build_generation_payload_stays_provider_submission_ready() -> None:
    request = _resolve_request()
    asset_key = build_asset_key(
        asset_class=str(request["asset_class"]),
        provider=str(request["provider"]),
        model=str(request["model"]),
        prompt=str(request["prompt"]),
        negative_prompt=str(request["negative_prompt"]),
        seed=int(request["seed"]),
        duration_seconds=float(request["duration_seconds"]),
        fps=int(request["fps"]),
        ratio=str(request["ratio"]),
        motion=request["motion"],
        init_image_hash=str(request["init_image_hash"]),
        reference_asset_ids=request["reference_asset_ids"],
    )
    payload = build_generation_payload(asset_key=asset_key, request_payload=request)
    assert payload["asset_key_hash"] == asset_key.asset_key_hash
    assert payload["canonical_params"]["provider"] == "runway"
    assert payload["provider_submission"] == {
        "provider": "runway",
        "model": "gen4.5",
        "asset_class": "clip",
        "external_ref": build_runway_job_external_ref(asset_key_hash=asset_key.asset_key_hash),
        "status": "submitted",
    }
    assert payload["provenance"]["source"] == "asset_registry.resolve"
