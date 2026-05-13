"""Seed testorg1 / steakpagetest with a Wikimedia-sourced multi-layer steak hook asset pack.

This persists to the API database (org, page, asset pack, imported assets). Hook canvas positions
live in browser localStorage; ``artifacts/seed_steakpagetest/hook_canvas_layout.json`` plus
``--hook-json-out`` reproduce the saved generation JSON for the Live hook image creator.

``artifacts/seed_steakpagetest/saved_hook_generations.json`` is a reference snapshot from one
seed run. Regenerate it after re-seeding if org, page, or asset UUIDs change.

Run (from repo root, API stack + infra + migrations up, DATABASE_URL in .env or supplied):

  cd apps/api && poetry run python ../../scripts/seed_steakpagetest_reel_pack.py

Optional:

  --hook-json-out path/to/saved_generations.json   # operator localStorage array fragment
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
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
    Asset,
    AssetPack,
    AssetPackItem,
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
    detect_png_transparency,
    detect_png_visual_metadata,
)
from content_lab_shared.settings import Settings  # noqa: E402

USER_AGENT = "ContentLabSteakSeed/1.0"  # pragma: allowlist secret

LAYOUT_PATH = REPO_ROOT / "artifacts" / "seed_steakpagetest" / "hook_canvas_layout.json"

ORG_SLUG = "testorg1"
PAGE_HANDLE = "@steakpagetest"
PAGE_DISPLAY = "steakpagetest"

TEST_REQUEST = SimpleNamespace(state=SimpleNamespace(actor="seed_steakpagetest_reel_pack"))


@dataclass(frozen=True)
class SteakSeed:
    slot: str
    commons_title: str
    upload_url: str
    local_filename: str
    asset_kind: AssetKind
    pack_role: str
    working_title: str
    purpose: str
    category: str
    tags: tuple[str, ...]
    performance_score: float


STEAK_SEEDS: tuple[SteakSeed, ...] = (
    SteakSeed(
        slot="background",
        commons_title="File:California Kitchen Cooktop.jpg",
        upload_url="https://upload.wikimedia.org/wikipedia/commons/9/9c/California_Kitchen_Cooktop.jpg",
        local_filename="california_kitchen_cooktop.jpg",
        asset_kind=AssetKind.BACKGROUND_IMAGE,
        pack_role="kitchen wide background",
        working_title="California kitchen cooktop backdrop",
        purpose="Full-frame kitchen scene for multi-layer hook composition tests.",
        category="scene_setter",
        tags=("kitchen", "cooktop", "interior"),
        performance_score=0.86,
    ),
    SteakSeed(
        slot="induction",
        commons_title="File:Induction Cooktop Rolling Boil Cropped.jpg",
        upload_url="https://upload.wikimedia.org/wikipedia/commons/c/c5/Induction_Cooktop_Rolling_Boil_Cropped.jpg",
        local_filename="induction_cooktop_rolling_boil.jpg",
        asset_kind=AssetKind.OBJECT_IMAGE,
        pack_role="induction cooktop surface",
        working_title="Induction cooktop (rolling boil crop)",
        purpose="Foreground appliance layer for counter-level hook compositions.",
        category="appliance",
        tags=("cooktop", "induction", "kitchen"),
        performance_score=0.84,
    ),
    SteakSeed(
        slot="pan",
        commons_title="File:Pfanne (Edelstahl).jpg",
        upload_url="https://upload.wikimedia.org/wikipedia/commons/5/5c/Pfanne_%28Edelstahl%29.jpg",
        local_filename="stainless_frying_pan.jpg",
        asset_kind=AssetKind.OBJECT_IMAGE,
        pack_role="stainless frying pan",
        working_title="Stainless steel frying pan",
        purpose="Prop layer for stove-top prep scenes.",
        category="prop",
        tags=("pan", "cookware", "metal"),
        performance_score=0.82,
    ),
    SteakSeed(
        slot="steak_raw",
        commons_title="File:Raw beef steak, 2011.jpg",
        upload_url="https://upload.wikimedia.org/wikipedia/commons/9/95/Raw_beef_steak%2C_2011.jpg",
        local_filename="raw_beef_steak_2011.jpg",
        asset_kind=AssetKind.OBJECT_IMAGE,
        pack_role="raw beef steak",
        working_title="Raw beef steak",
        purpose="Protein focal layer for prep and ingredient beats.",
        category="ingredient",
        tags=("steak", "beef", "raw"),
        performance_score=0.88,
    ),
    SteakSeed(
        slot="steak_grill",
        commons_title="File:Grilling steak.jpg",
        upload_url="https://upload.wikimedia.org/wikipedia/commons/e/e8/Grilling_steak.jpg",
        local_filename="grilling_steak.jpg",
        asset_kind=AssetKind.OBJECT_IMAGE,
        pack_role="grilling steak",
        working_title="Grilling steak",
        purpose="Secondary steak layer for action-oriented compositions.",
        category="ingredient",
        tags=("steak", "grill", "cook"),
        performance_score=0.85,
    ),
    SteakSeed(
        slot="basil",
        commons_title="File:Basil plant in a pot 01.jpg",
        upload_url="https://upload.wikimedia.org/wikipedia/commons/0/01/Basil_plant_in_a_pot_01.jpg",
        local_filename="basil_plant_pot.jpg",
        asset_kind=AssetKind.OBJECT_IMAGE,
        pack_role="basil plant in pot",
        working_title="Basil plant in pot",
        purpose="Herb cluster layer for counter depth.",
        category="herb",
        tags=("basil", "herb", "plant"),
        performance_score=0.8,
    ),
    SteakSeed(
        slot="rosemary",
        commons_title="File:Rosemary, Δενδρολίβανο.jpg",
        upload_url="https://upload.wikimedia.org/wikipedia/commons/e/ed/Rosemary%2C_%CE%94%CE%B5%CE%BD%CE%B4%CF%81%CE%BF%CE%BB%CE%AF%CE%B2%CE%B1%CE%BD%CE%BF.jpg",
        local_filename="rosemary_sprig.jpg",
        asset_kind=AssetKind.OBJECT_IMAGE,
        pack_role="rosemary sprig",
        working_title="Rosemary sprig",
        purpose="Secondary herb cluster for layering tests.",
        category="herb",
        tags=("rosemary", "herb", "aromatic"),
        performance_score=0.78,
    ),
    SteakSeed(
        slot="parsley",
        commons_title="File:Parsley plant in a pot 05.jpg",
        upload_url="https://upload.wikimedia.org/wikipedia/commons/3/30/Parsley_plant_in_a_pot_05.jpg",
        local_filename="parsley_plant_pot.jpg",
        asset_kind=AssetKind.OBJECT_IMAGE,
        pack_role="parsley plant in pot",
        working_title="Parsley plant in pot",
        purpose="Tertiary herb layer.",
        category="herb",
        tags=("parsley", "herb", "plant"),
        performance_score=0.79,
    ),
    SteakSeed(
        slot="wine",
        commons_title="File:Red wine in glass.jpg",
        upload_url="https://upload.wikimedia.org/wikipedia/commons/9/9d/Red_wine_in_glass.jpg",
        local_filename="red_wine_in_glass.jpg",
        asset_kind=AssetKind.OBJECT_IMAGE,
        pack_role="red wine glass",
        working_title="Red wine in glass",
        purpose="Foreground glassware prop.",
        category="prop",
        tags=("wine", "glass", "drink"),
        performance_score=0.81,
    ),
    SteakSeed(
        slot="decanter",
        commons_title="File:New Decanter.jpg",
        upload_url="https://upload.wikimedia.org/wikipedia/commons/5/5b/New_Decanter.jpg",
        local_filename="wine_decanter.jpg",
        asset_kind=AssetKind.OBJECT_IMAGE,
        pack_role="wine decanter",
        working_title="Wine decanter",
        purpose="Secondary glassware prop for counter balance.",
        category="prop",
        tags=("decanter", "wine", "vessel"),
        performance_score=0.8,
    ),
    SteakSeed(
        slot="mint",
        commons_title="File:Mint.png",
        upload_url="https://upload.wikimedia.org/wikipedia/commons/1/13/Mint.png",
        local_filename="mint_cutout.png",
        asset_kind=AssetKind.TRANSPARENT_CUTOUT_PNG,
        pack_role="mint herb cutout",
        working_title="Mint herb (transparent PNG)",
        purpose="Layerable transparent herb cut-out.",
        category="layerable_cutout",
        tags=("mint", "herb", "transparent"),
        performance_score=0.83,
    ),
)


def commons_wiki_url(commons_title: str) -> str:
    name = commons_title.replace(" ", "_")
    return f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(name)}"


def download_with_retry(url: str, *, expect_prefixes: tuple[bytes, ...]) -> bytes:
    last_err: Exception | None = None
    for attempt in range(1, 8):
        try:
            request_obj = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request_obj, timeout=180) as response:
                data = response.read()
            if not any(data.startswith(p) for p in expect_prefixes):
                starts = data[:16]
                raise RuntimeError(f"Unexpected file signature from {url!r}: {starts!r}")
            return data
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code not in {429, 500, 502, 503, 504}:
                raise
            retry_after = exc.headers.get("Retry-After")
            delay = int(retry_after) if retry_after and retry_after.isdigit() else 5 * attempt
            time.sleep(delay)
        except urllib.error.URLError as exc:
            last_err = exc
            time.sleep(5 * attempt)
    raise RuntimeError(f"Unable to download after retries: {url}") from last_err


def validate_seed_bytes(seed: SteakSeed, data: bytes) -> None:
    if seed.asset_kind is AssetKind.TRANSPARENT_CUTOUT_PNG:
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError(f"{seed.slot} must be PNG")
        t = detect_png_transparency(data)
        if not bool(t.has_transparency):
            raise RuntimeError(f"{seed.slot} PNG has no transparency (expected cutout)")
    elif data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8\xff"):
        return
    else:
        raise RuntimeError(f"{seed.slot} is neither JPEG nor PNG")


def compatibility_for_seed(seed: SteakSeed) -> AssetCompatibilityMetadata:
    base: dict[str, Any] = {
        "niche": ["steak cooking", "hook composition test"],
        "topic": ["kitchen", "protein", "herbs"],
        "theme": ["prep", "ingredients", *seed.tags],
        "emotion": ["useful", "tactile"],
        "visual_style": ["real photo", "layered"],
        "pace": ["medium"],
        "format_type": ["hook composition"],
    }
    if seed.asset_kind is AssetKind.BACKGROUND_IMAGE:
        base["works_as_background_for"] = [
            AssetKind.OBJECT_IMAGE.value,
            AssetKind.TRANSPARENT_CUTOUT_PNG.value,
        ]
    else:
        base["works_with_object_types"] = [seed.category, *seed.tags]
    return AssetCompatibilityMetadata.model_validate(base)


def load_layout(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_org(db: Session) -> Org:
    org = db.scalars(select(Org).where(Org.slug == ORG_SLUG)).one_or_none()
    if org:
        return org
    org = Org(name=ORG_SLUG, slug=ORG_SLUG)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def ensure_page(db: Session, org_id: uuid.UUID) -> Page:
    page = db.scalars(
        select(Page).where(Page.org_id == org_id, Page.handle == PAGE_HANDLE)
    ).one_or_none()
    if page:
        return page
    page = Page(
        org_id=org_id,
        platform="instagram",
        display_name=PAGE_DISPLAY,
        external_page_id=None,
        handle=PAGE_HANDLE,
        kind=PageKind.OWNED.value,
        metadata_={
            "purpose": "steakpagetest hook layout QA",
            "seed": "seed_steakpagetest_reel_pack.py",
        },
    )
    db.add(page)
    db.commit()
    db.refresh(page)
    return page


def create_pack(
    db: Session, *, org_id: uuid.UUID, name: str, niche: str, summary: str
) -> AssetPack:
    mix: dict[str, int] = {}
    for seed in STEAK_SEEDS:
        mix[seed.asset_kind.value] = mix.get(seed.asset_kind.value, 0) + 1
    pack = AssetPack(
        org_id=org_id,
        name=name,
        niche=niche,
        purpose="Imported commons photos for multi-layer steak hook testing (no generation).",
        target_audience="Content Lab operators validating hook canvas layering.",
        requested_asset_count=len(STEAK_SEEDS),
        asset_mix_requested_json=mix,
        asset_mix_final_json=mix,
        status=AssetPackStatus.APPROVED.value,
        strategy_summary=summary,
    )
    db.add(pack)
    db.commit()
    db.refresh(pack)
    return pack


def get_existing_slot_map(db: Session, pack_id: uuid.UUID) -> dict[str, uuid.UUID]:
    rows = db.execute(
        select(Asset.id, Asset.metadata_)
        .join(AssetPackItem, AssetPackItem.asset_id == Asset.id)
        .where(AssetPackItem.asset_pack_id == pack_id)
    ).all()
    out: dict[str, uuid.UUID] = {}
    for aid, meta in rows:
        slot = (meta or {}).get("seed_slot")
        if isinstance(slot, str):
            out[slot] = aid
    return out


def create_planned_spec(
    db: Session, *, asset_pack_id: uuid.UUID, seed: SteakSeed
) -> PlannedAssetSpec:
    compatibility = compatibility_for_seed(seed).model_dump(mode="python")
    spec = PlannedAssetSpec(
        asset_pack_id=asset_pack_id,
        asset_kind=seed.asset_kind.value,
        media_type=MediaType.IMAGE.value,
        working_title=seed.working_title,
        purpose=seed.purpose,
        prompt_or_description=(
            f"Imported media for {seed.working_title}; no model generation. "
            f"Slot `{seed.slot}` for reproducible hook layout tests."
        ),
        required_traits={
            "category": seed.category,
            "seed_slot": seed.slot,
            "steak_reel_seed": True,
            "online_source_only": True,
            "generation_allowed": False,
            "tags": list(seed.tags),
            "output_potential": {
                "score": round(seed.performance_score * 100, 2),
                "rationale": [
                    "Commons-sourced real photo for layered operator canvas tests.",
                ],
            },
        },
        compatible_with={"reel_formats": ["hook composition"]},
        compatibility_metadata=compatibility,
        intended_reel_formats=["hook composition"],
        priority=next(i for i, s in enumerate(STEAK_SEEDS) if s.slot == seed.slot),
        estimated_reuse_count=10,
        status=PlannedAssetSpecStatus.PLANNED.value,
    )
    db.add(spec)
    db.commit()
    db.refresh(spec)
    return spec


def source_register_request(
    *,
    seed: SteakSeed,
    data: bytes,
    spec_id: uuid.UUID,
    pack_name: str,
) -> SourceAssetRegisterRequest:
    wiki = commons_wiki_url(seed.commons_title)
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        visual = detect_png_visual_metadata(data)
        transparency = detect_png_transparency(data)
    else:
        visual = None
        transparency = detect_png_transparency(b"")

    validate_seed_bytes(seed, data)
    priority = next(i for i, s in enumerate(STEAK_SEEDS) if s.slot == seed.slot)

    source_meta = AssetSourceMetadata(
        source_type=AssetSourceType.APPROVED_EXTERNAL_SOURCE,
        source_provider="Wikimedia Commons",
        external_source_url=wiki,
        source_reference_id=seed.commons_title,
        licence_type="varies (see file page)",
        licence_notes=wiki,
        usage_allowed=True,
        commercial_use_allowed=True,
        attribution_required=True,
        attribution_text=f"See {wiki} for author and license.",
        imported_by="seed_steakpagetest_reel_pack",
        original_content_hash=hashlib.sha256(data).hexdigest(),
        source_quality_score=0.9,
        source_risk_notes="Imported from official Commons file page metadata; no generation used.",
    )

    content_type = "image/png" if data.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg"

    metadata = {
        "title": seed.working_title,
        "seed_slot": seed.slot,
        "asset_pack_niche": pack_name,
        "pack_role": seed.pack_role,
        "category": seed.category,
        "tags": list(seed.tags),
        "performance_score": seed.performance_score,
        "compatibility": compatibility_for_seed(seed).model_dump(mode="python"),
        "source": {
            "provider": "Wikimedia Commons",
            "file_title": seed.commons_title,
            "file_page": wiki,
            "download_url": seed.upload_url,
            "online_imported": True,
            "generation_used": False,
        },
        "visual": {} if visual is None else visual.model_dump(mode="python", exclude_none=True),
        "transparency": transparency.model_dump(mode="python", exclude_none=True),
    }

    return SourceAssetRegisterRequest(
        asset_class="component",
        asset_kind=seed.asset_kind,
        media_type=MediaType.IMAGE,
        asset_source=AssetSource.IMPORTED,
        pack_role=seed.pack_role,
        reuse_purpose=seed.purpose,
        priority=priority,
        planned_asset_spec_id=spec_id,
        filename=seed.local_filename,
        content_type=content_type,
        data_base64=base64.b64encode(data).decode("ascii"),
        width=None if visual is None else visual.width,
        height=None if visual is None else visual.height,
        metadata=metadata,
        source_metadata=source_meta,
    )


def library_item_for_slot(
    org_id: uuid.UUID, pack_name: str, seed: SteakSeed, asset_id: uuid.UUID
) -> dict[str, Any]:
    kind = "background" if seed.asset_kind is AssetKind.BACKGROUND_IMAGE else "object"
    return {
        "id": str(asset_id),
        "title": seed.working_title,
        "kind": kind,
        "mediaType": "image",
        "pack": pack_name,
        "tags": ["steak-reel-seed", seed.slot, *list(seed.tags)],
        "layerSuitability": f"Real-photo layer ({seed.slot})",
        "reuseCount": 0,
        "performanceScore": round(seed.performance_score * 100),
        "previewTone": "linear-gradient(135deg,#1f2937,#94a3b8)",
        "imageUrl": f"/api/orgs/{org_id}/assets/{asset_id}/file",
        "storageUri": "",
    }


def build_saved_generation(
    *,
    org_id: uuid.UUID,
    page_id: uuid.UUID,
    layout: dict[str, Any],
    slot_to_asset: dict[str, uuid.UUID],
) -> dict[str, Any]:
    pack_name = str(layout["packName"])
    gen_suffix = str(layout["savedGenerationIdSuffix"])
    name = str(layout["savedGenerationName"])
    bg_slot = str(layout["backgroundSlot"])

    bg_seed = next(s for s in STEAK_SEEDS if s.slot == bg_slot)
    bg_id = slot_to_asset[bg_slot]
    background = library_item_for_slot(org_id, pack_name, bg_seed, bg_id)

    items: list[dict[str, Any]] = []
    for row in layout["canvasItems"]:
        slot = str(row["slot"])
        seed = next(s for s in STEAK_SEEDS if s.slot == slot)
        aid = slot_to_asset[slot]
        items.append(
            {
                "id": f"{aid}-{slot}",
                "asset": library_item_for_slot(org_id, pack_name, seed, aid),
                "x": float(row["x"]),
                "y": float(row["y"]),
                "size": float(row["size"]),
            }
        )

    gen_id = f"local-hook:{page_id}:{gen_suffix}"
    return {
        "id": gen_id,
        "sourceRunId": None,
        "name": name,
        "selectedBackgroundId": str(bg_id),
        "background": background,
        "items": items,
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database-url", default=None)
    p.add_argument("--layout-path", type=Path, default=LAYOUT_PATH)
    p.add_argument(
        "--hook-json-out",
        type=Path,
        default=None,
        help="Write localStorage JSON array (single saved generation) for manual import.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    layout = load_layout(args.layout_path)
    pack_name = str(layout["packName"])

    settings = Settings()
    database_url = args.database_url or settings.database_url
    engine = create_engine(database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    with SessionLocal() as db:
        org = ensure_org(db)
        page = ensure_page(db, org.id)

        pack = db.scalars(
            select(AssetPack)
            .where(AssetPack.org_id == org.id, AssetPack.name == pack_name)
            .order_by(AssetPack.created_at.desc())
        ).first()
        if pack is None:
            pack = create_pack(
                db,
                org_id=org.id,
                name=pack_name,
                niche="steak reel hook composition",
                summary=(
                    "Eleven Wikimedia Commons stills (kitchen, cooktop, pan, steaks, herbs, "
                    "glassware, mint cut-out) for live hook canvas layering QA."
                ),
            )

        slot_map = get_existing_slot_map(db, pack.id)
        need_assets = len(slot_map) < len(STEAK_SEEDS)

        if need_assets:
            run_dir = (
                REPO_ROOT
                / "artifacts"
                / "seed_steakpagetest"
                / "downloads"
                / time.strftime("%Y%m%d-%H%M%S")
            )
            run_dir.mkdir(parents=True, exist_ok=True)

            for seed in STEAK_SEEDS:
                if seed.slot in slot_map:
                    continue
                prefixes: tuple[bytes, ...]
                if seed.upload_url.lower().endswith(".png"):
                    prefixes = (b"\x89PNG\r\n\x1a\n",)
                else:
                    prefixes = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")
                data = download_with_retry(seed.upload_url, expect_prefixes=prefixes)
                validate_seed_bytes(seed, data)
                (run_dir / seed.local_filename).write_bytes(data)

                spec = create_planned_spec(db, asset_pack_id=pack.id, seed=seed)
                body = source_register_request(
                    seed=seed, data=data, spec_id=spec.id, pack_name=pack_name
                )
                asset, _item, _reused = register_source_asset_for_pack(
                    db,
                    TEST_REQUEST,
                    org_id=org.id,
                    asset_pack_id=pack.id,
                    body=body,
                    settings=settings,
                )
                slot_map[seed.slot] = asset.id
                time.sleep(0.6)

        if len(slot_map) < len(STEAK_SEEDS):
            missing = sorted({s.slot for s in STEAK_SEEDS} - set(slot_map))
            raise RuntimeError(f"Asset pack incomplete; missing slots: {missing}")

        fresh = db.get(AssetPack, pack.id)
        if fresh is not None:
            fresh.status = AssetPackStatus.READY.value
            db.commit()

        generation = build_saved_generation(
            org_id=org.id, page_id=page.id, layout=layout, slot_to_asset=slot_map
        )

        summary = {
            "org_id": str(org.id),
            "org_slug": org.slug,
            "page_id": str(page.id),
            "page_handle": page.handle,
            "page_display_name": page.display_name,
            "asset_pack_id": str(pack.id),
            "asset_pack_name": pack.name,
            "asset_slots": {slot: str(aid) for slot, aid in sorted(slot_map.items())},
            "localStorage_key": f"{''.join(('content', '-lab'))}:hook-images:{org.id}:{page.id}",  # pragma: allowlist secret
            "saved_generation": generation,
        }
        print(json.dumps(summary, indent=2, sort_keys=True))

    if args.hook_json_out:
        # One-element array matching SavedHookImageGeneration[] in localStorage
        args.hook_json_out.parent.mkdir(parents=True, exist_ok=True)
        args.hook_json_out.write_text(
            json.dumps([generation], indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
