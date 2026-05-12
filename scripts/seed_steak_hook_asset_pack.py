#!/usr/bin/env python3
"""Seed the steakpagetest Instagram-hook recreation pack from online assets."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (
    REPO_ROOT / "apps" / "api" / "src",
    REPO_ROOT / "packages" / "assets" / "src",
    REPO_ROOT / "packages" / "shared" / "py" / "src",
    REPO_ROOT / "packages" / "storage" / "src",
):
    sys.path.insert(0, str(path))

from content_lab_api.models import (  # noqa: E402
    AssetPack,
    AssetPackStatus,
    Org,
    Page,
    PageKind,
    PlannedAssetSpec,
    PlannedAssetSpecStatus,
)
from content_lab_api.schemas.asset_packs import SourceAssetRegisterRequest  # noqa: E402
from content_lab_api.services.asset_packs import register_source_asset_for_pack  # noqa: E402
from content_lab_assets.combinator import AssetCompatibilityMetadata  # noqa: E402
from content_lab_assets.types import (  # noqa: E402
    AssetKind,
    AssetSource,
    AssetSourceMetadata,
    AssetSourceType,
    MediaType,
)
from content_lab_shared.settings import Settings  # noqa: E402

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
ORG_SLUG = "testorg1"
PAGE_HANDLE = "@steakpagetest"
PACK_NAME = "steakpagetest Instagram steak hook recreation"


@dataclass(frozen=True)
class SteakHookSeed:
    title: str
    local_name: str
    asset_kind: AssetKind
    media_type: MediaType
    content_type: str
    pack_role: str
    working_title: str
    purpose: str
    category: str
    tags: tuple[str, ...]
    performance_score: float
    priority: int
    text_payload: str | None = None
    preview_tone: str | None = None


ASSET_SEEDS: tuple[SteakHookSeed, ...] = (
    SteakHookSeed(
        title="File:Beef round top round steak in pan, raw.jpg",
        local_name="steak_in_pan_background.jpg",
        asset_kind=AssetKind.BACKGROUND_IMAGE,
        media_type=MediaType.IMAGE,
        content_type="image/jpeg",
        pack_role="background",
        working_title="Steak in pan hook background",
        purpose="Primary cooking-pan visual for recreating the uploaded Instagram hook screenshot.",
        category="native_reel_background",
        tags=("steakpagetest", "steak", "pan", "instagram-hook"),
        performance_score=0.97,
        priority=0,
        preview_tone="linear-gradient(180deg, #d9c4a1 0%, #f3ead8 38%, #161b1d 39%, #0d1113 100%)",
    ),
    SteakHookSeed(
        title="File:Basil.png",
        local_name="basil_herb_planter_cue.png",
        asset_kind=AssetKind.TRANSPARENT_CUTOUT_PNG,
        media_type=MediaType.IMAGE,
        content_type="image/png",
        pack_role="foreground",
        working_title="Countertop herb planter cue",
        purpose="Green herb foreground motif matching the plant tray in the reference hook.",
        category="foreground_herbs",
        tags=("steakpagetest", "herbs", "countertop", "foreground"),
        performance_score=0.92,
        priority=1,
        preview_tone="radial-gradient(circle at 50% 40%, #86a85e 0 23%, #36522b 24% 45%, #2c2118 46%)",
    ),
    SteakHookSeed(
        title="File:Instagram logo 2022.svg",
        local_name="instagram_native_ui_reference.svg",
        asset_kind=AssetKind.PROP_IMAGE,
        media_type=MediaType.IMAGE,
        content_type="image/svg+xml",
        pack_role="native_ui_prop",
        working_title="Instagram native UI reference",
        purpose="Native interface reference for the right rail, profile badge, and bottom navigation chrome.",
        category="native_platform_ui",
        tags=("steakpagetest", "instagram", "ui", "reference"),
        performance_score=0.88,
        priority=2,
        preview_tone="linear-gradient(135deg, #833ab4, #fd1d1d, #fcb045)",
    ),
    SteakHookSeed(
        title="steakpagetest hook text",
        local_name="steakpagetest_hook_text.txt",
        asset_kind=AssetKind.HOOK_TEXT,
        media_type=MediaType.TEXT,
        content_type="text/plain",
        pack_role="hook",
        working_title="Verse kruiden binnen handbereik",
        purpose="Lower-caption hook copy from the uploaded reference screenshot.",
        category="native_caption_hook",
        tags=("steakpagetest", "dutch-caption", "native-ui"),
        performance_score=0.95,
        priority=3,
        text_payload="Verse kruiden binnen handbereik 🌿 ...",
        preview_tone="linear-gradient(135deg, #0f172a, #f97316)",
    ),
)


def main() -> None:
    args = parse_args()
    settings = Settings()
    database_url = args.database_url or settings.database_url
    artifact_dir = Path(args.artifact_dir or REPO_ROOT / "artifacts" / "asset_packs" / "steak_hook")
    run_dir = artifact_dir / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    image_infos = fetch_commons_image_infos(
        [seed.title for seed in ASSET_SEEDS if seed.text_payload is None]
    )
    downloads = download_assets(run_dir, image_infos)

    engine = create_engine(database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    with SessionLocal() as db:
        org = ensure_org(db)
        page = ensure_page(db, org_id=org.id)
        pack = create_pack(db, org_id=org.id)
        request = SimpleNamespace(state=SimpleNamespace(actor="seed_steak_hook_asset_pack"))
        summary_assets: list[dict[str, Any]] = []

        for seed in ASSET_SEEDS:
            info = image_infos.get(seed.title)
            data = (
                seed.text_payload.encode("utf-8")
                if seed.text_payload is not None
                else downloads[seed.title].read_bytes()
            )
            spec = create_planned_spec(db, asset_pack_id=pack.id, seed=seed)
            body = source_register_request(seed=seed, info=info, data=data, spec_id=spec.id)
            asset, item, reused = register_source_asset_for_pack(
                db,
                request,
                org_id=org.id,
                asset_pack_id=pack.id,
                body=body,
                settings=settings,
            )
            summary_assets.append(
                {
                    "asset_id": str(asset.id),
                    "asset_pack_item_id": str(item.id),
                    "planned_asset_spec_id": str(spec.id),
                    "asset_kind": seed.asset_kind.value,
                    "pack_role": seed.pack_role,
                    "title": seed.working_title,
                    "storage_uri": asset.storage_uri,
                    "source_page": None if info is None else info["descriptionurl"],
                    "download_url": None if info is None else info["url"],
                    "reused_existing_asset": reused,
                }
            )

        pack = db.get(AssetPack, pack.id)
        if pack is None:
            raise RuntimeError("Asset pack disappeared during seed")
        pack.status = AssetPackStatus.READY.value
        db.commit()

        result = {
            "status": "seeded",
            "org_id": str(org.id),
            "org_slug": org.slug,
            "page_id": str(page.id),
            "page_name": page.display_name,
            "asset_pack_id": str(pack.id),
            "asset_pack_name": pack.name,
            "asset_count": len(summary_assets),
            "artifact_dir": str(run_dir),
            "assets": summary_assets,
        }
        (run_dir / "summary.json").write_text(
            json.dumps(result, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(json.dumps(result, indent=2, sort_keys=True))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed testorg1/steakpagetest with one steak hook recreation asset pack."
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--artifact-dir", default=None)
    return parser.parse_args()


def ensure_org(db: Session) -> Org:
    org = db.scalars(select(Org).where(Org.slug == ORG_SLUG)).one_or_none()
    if org is None:
        org = Org(name="testorg1", slug=ORG_SLUG)
        db.add(org)
        db.commit()
        db.refresh(org)
    return org


def ensure_page(db: Session, *, org_id: uuid.UUID) -> Page:
    metadata: dict[str, object] = {
        "persona": {
            "label": "steakpagetest",
            "audience": "Home cooks watching premium kitchen and steak prep reels.",
            "brand_tone": ["warm", "practical", "native-social"],
            "content_pillars": ["steak cooking", "fresh herbs", "countertop kitchen tips"],
            "differentiators": ["Instagram-native", "real kitchen setting", "ingredient-first"],
            "primary_call_to_action": "Follow for practical steak and herb prep ideas.",
            "extensions": {},
        },
        "constraints": {
            "banned_topics": [],
            "blocked_phrases": [],
            "required_disclosures": [],
            "prohibited_claims": [],
            "preferred_languages": ["nl", "en"],
            "allow_direct_cta": True,
            "max_script_words": 80,
            "max_hashtags": 4,
        },
    }
    page = db.scalars(select(Page).where(Page.org_id == org_id, Page.handle == PAGE_HANDLE)).one_or_none()
    if page is None:
        page = Page(
            org_id=org_id,
            platform="instagram",
            display_name="steakpagetest",
            external_page_id="steakpagetest",
            handle=PAGE_HANDLE,
            kind=PageKind.OWNED.value,
            metadata_=metadata,
        )
        db.add(page)
    else:
        page.platform = "instagram"
        page.display_name = "steakpagetest"
        page.external_page_id = "steakpagetest"
        page.kind = PageKind.OWNED.value
        page.metadata_ = metadata
    db.commit()
    db.refresh(page)
    return page


def create_pack(db: Session, *, org_id: uuid.UUID) -> AssetPack:
    asset_mix = {
        AssetKind.BACKGROUND_IMAGE.value: 1,
        AssetKind.TRANSPARENT_CUTOUT_PNG.value: 1,
        AssetKind.PROP_IMAGE.value: 1,
        AssetKind.HOOK_TEXT.value: 1,
    }
    pack = AssetPack(
        org_id=org_id,
        name=PACK_NAME,
        niche="Instagram steak hook recreation",
        purpose=(
            "Single ready asset pack for recreating the uploaded steak-pan Instagram hook "
            "screenshot in the live hook creator and asset-pack generation preview."
        ),
        target_audience="Operators building realistic cooking hook covers for steakpagetest.",
        requested_asset_count=len(ASSET_SEEDS),
        asset_mix_requested_json=asset_mix,
        asset_mix_final_json=asset_mix,
        status=AssetPackStatus.APPROVED.value,
        strategy_summary=(
            "Uses approved online reference assets for the pan, herbs, and Instagram-native UI "
            "with local hook copy matching the uploaded screenshot."
        ),
    )
    db.add(pack)
    db.commit()
    db.refresh(pack)
    return pack


def create_planned_spec(
    db: Session,
    *,
    asset_pack_id: uuid.UUID,
    seed: SteakHookSeed,
) -> PlannedAssetSpec:
    compatibility = compatibility_for_seed(seed).model_dump(mode="python")
    spec = PlannedAssetSpec(
        asset_pack_id=asset_pack_id,
        asset_kind=seed.asset_kind.value,
        media_type=seed.media_type.value,
        working_title=seed.working_title,
        purpose=seed.purpose,
        prompt_or_description=(
            f"Recreate the uploaded steak-pan Instagram hook screenshot role: {seed.pack_role}."
        ),
        required_traits={
            "category": seed.category,
            "tags": list(seed.tags),
            "reference_page": "steakpagetest",
            "template": "instagram_steak_hook",
            "online_source_only": seed.text_payload is None,
        },
        compatible_with={
            "reel_formats": ["native Instagram hook", "steak cooking cover"],
            "works_with": ["right rail reactions", "bottom caption", "safe-area mobile UI"],
        },
        compatibility_metadata=compatibility,
        intended_reel_formats=["native Instagram hook", "steak cooking cover"],
        priority=seed.priority,
        estimated_reuse_count=8,
        status=PlannedAssetSpecStatus.PLANNED.value,
    )
    db.add(spec)
    db.commit()
    db.refresh(spec)
    return spec


def source_register_request(
    *,
    seed: SteakHookSeed,
    info: Mapping[str, Any] | None,
    data: bytes,
    spec_id: uuid.UUID,
) -> SourceAssetRegisterRequest:
    source_url = None if info is None else str(info["descriptionurl"])
    download_url = None if info is None else str(info["url"])
    metadata = {
        "title": seed.working_title,
        "asset_pack_niche": "Instagram steak hook recreation",
        "pack_role": seed.pack_role,
        "category": seed.category,
        "tags": list(seed.tags),
        "performance_score": seed.performance_score,
        "preview_tone": seed.preview_tone,
        "template": "instagram_steak_hook",
        "page_slug": "steakpagetest",
        "image_url": download_url,
        "source": {
            "provider": "Wikimedia Commons" if info is not None else "operator reference",
            "file_title": seed.title,
            "file_page": source_url,
            "download_url": download_url,
            "license": None if info is None else info["license_short_name"],
            "license_url": None if info is None else info["license_url"],
            "online_imported": info is not None,
            "generation_used": False,
        },
        "compatibility": compatibility_for_seed(seed).model_dump(mode="python"),
    }
    attribution_required = bool(info and info["attribution_required"])
    source_meta = AssetSourceMetadata(
        source_type=AssetSourceType.APPROVED_EXTERNAL_SOURCE,
        source_provider="Wikimedia Commons" if info is not None else "operator reference",
        external_source_url=source_url,
        source_reference_id=seed.title,
        licence_type=None if info is None else info["license_short_name"],
        licence_notes=None if info is None else info["license_url"],
        usage_allowed=True,
        commercial_use_allowed=True,
        attribution_required=attribution_required,
        attribution_text=None if not attribution_required else info["attribution_text"],
        imported_by="seed_steak_hook_asset_pack",
        original_content_hash=hashlib.sha256(data).hexdigest(),
        source_quality_score=0.9,
        source_risk_notes="Imported for local screenshot-recreation testing; no generation used.",
    )
    return SourceAssetRegisterRequest(
        asset_class="component",
        asset_kind=seed.asset_kind,
        media_type=seed.media_type,
        asset_source=AssetSource.IMPORTED,
        pack_role=seed.pack_role,
        reuse_purpose=seed.purpose,
        priority=seed.priority,
        planned_asset_spec_id=spec_id,
        filename=seed.local_name,
        content_type=seed.content_type,
        data_base64=base64.b64encode(data).decode("ascii"),
        width=None if info is None else info.get("width"),
        height=None if info is None else info.get("height"),
        metadata=metadata,
        source_metadata=source_meta,
    )


def compatibility_for_seed(seed: SteakHookSeed) -> AssetCompatibilityMetadata:
    base: dict[str, Any] = {
        "niche": ["Instagram steak hook recreation"],
        "topic": ["steak cooking", "fresh herbs", "kitchen countertop"],
        "theme": ["native Instagram hook", *seed.tags],
        "emotion": ["warm", "appetizing", "practical"],
        "visual_style": ["real food", "mobile screenshot", "native UI"],
        "pace": ["snappy", "social-first"],
        "format_type": ["native Instagram hook", "steak cooking cover"],
        "works_with_hook_types": ["native Instagram hook", "dutch-caption", "steakpagetest"],
    }
    if seed.asset_kind is AssetKind.BACKGROUND_IMAGE:
        base["works_as_background_for"] = [
            AssetKind.TRANSPARENT_CUTOUT_PNG.value,
            AssetKind.PROP_IMAGE.value,
            "foreground",
            "native_ui_prop",
        ]
        base["requires_safe_area"] = True
    elif seed.asset_kind is AssetKind.TRANSPARENT_CUTOUT_PNG:
        base["works_with_object_types"] = ["foreground", "herbs", "countertop"]
        base["requires_transparency"] = True
    else:
        base["works_with_object_types"] = [seed.category, seed.pack_role]
    return AssetCompatibilityMetadata.model_validate(base)


def fetch_commons_image_infos(titles: list[str]) -> dict[str, dict[str, Any]]:
    if not titles:
        return {}
    params = {
        "action": "query",
        "format": "json",
        "prop": "imageinfo",
        "iiprop": "url|mime|size|extmetadata",
        "titles": "|".join(titles),
    }
    url = f"{COMMONS_API}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(request(url), timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
    infos: dict[str, dict[str, Any]] = {}
    for page in payload["query"]["pages"].values():
        title = page["title"]
        if "missing" in page:
            raise RuntimeError(f"Commons file not found: {title}")
        imageinfo = page["imageinfo"][0]
        ext = imageinfo.get("extmetadata", {})
        infos[title] = {
            "url": imageinfo["url"],
            "descriptionurl": imageinfo["descriptionurl"],
            "mime": imageinfo.get("mime"),
            "width": imageinfo.get("width"),
            "height": imageinfo.get("height"),
            "license_short_name": ext_value(ext, "LicenseShortName") or "unknown",
            "license_url": ext_value(ext, "LicenseUrl"),
            "artist": strip_html(ext_value(ext, "Artist")),
            "credit": strip_html(ext_value(ext, "Credit")),
        }
    missing = sorted(set(titles) - set(infos))
    if missing:
        raise RuntimeError(f"Missing Commons metadata for: {missing}")
    for title, info in infos.items():
        info["attribution_required"] = is_attribution_required(info["license_short_name"])
        info["attribution_text"] = attribution_text(title, info)
    return infos


def download_assets(run_dir: Path, infos: Mapping[str, Mapping[str, Any]]) -> dict[str, Path]:
    downloads: dict[str, Path] = {}
    for seed in ASSET_SEEDS:
        if seed.text_payload is not None:
            continue
        info = infos[seed.title]
        path = run_dir / seed.local_name
        data = download_with_retry(str(info["url"]))
        path.write_bytes(data)
        downloads[seed.title] = path
    return downloads


def download_with_retry(url: str) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, 5):
        try:
            with urllib.request.urlopen(request(url), timeout=180) as response:
                return response.read()
        except OSError as exc:
            last_error = exc
            time.sleep(2 * attempt)
    raise RuntimeError(f"Could not download {url}: {last_error}") from last_error


def request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url)


def ext_value(ext: Mapping[str, Any], key: str) -> str | None:
    value = ext.get(key)
    if isinstance(value, Mapping):
        raw = value.get("value")
        return None if raw is None else str(raw)
    return None


def strip_html(value: str | None) -> str | None:
    if value is None:
        return None
    text = value
    for token in ("<span>", "</span>", "<p>", "</p>", "<b>", "</b>", "<i>", "</i>"):
        text = text.replace(token, "")
    return " ".join(text.split())


def is_attribution_required(license_name: str | None) -> bool:
    normalized = (license_name or "").lower()
    return not any(marker in normalized for marker in ("public domain", "cc0", "pd"))


def attribution_text(title: str, info: Mapping[str, Any]) -> str:
    parts = [title]
    artist = info.get("artist")
    if artist:
        parts.append(f"by {artist}")
    license_name = info.get("license_short_name")
    if license_name:
        parts.append(str(license_name))
    return " - ".join(parts)


if __name__ == "__main__":
    main()
