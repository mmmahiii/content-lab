from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.error import HTTPError, URLError

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
    detect_png_transparency,
    detect_png_visual_metadata,
)
from content_lab_shared.settings import Settings  # noqa: E402

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "ContentLabAssetSeeder/1.0 (local operator seed; Wikimedia Commons API)"


@dataclass(frozen=True)
class CommonsAssetSeed:
    title: str
    local_name: str
    asset_kind: AssetKind
    pack_role: str
    working_title: str
    purpose: str
    prompt_or_description: str
    category: str
    tags: tuple[str, ...]
    performance_score: float
    priority: int


ASSET_SEEDS: tuple[CommonsAssetSeed, ...] = (
    CommonsAssetSeed(
        title="File:Ratatouille ingredients.png",
        local_name="ratatouille_ingredients.png",
        asset_kind=AssetKind.BACKGROUND_IMAGE,
        pack_role="background ingredient scene",
        working_title="Ratatouille ingredient scene",
        purpose="Reusable produce-heavy scene setter for faceless cooking reels.",
        prompt_or_description="Imported transparent PNG of ratatouille ingredients for use as a layered cooking scene.",
        category="scene_setter",
        tags=("vegetables", "flatlay", "recipe_context"),
        performance_score=0.82,
        priority=0,
    ),
    CommonsAssetSeed(
        title="File:Fresh vegetables.png",
        local_name="fresh_vegetables.png",
        asset_kind=AssetKind.BACKGROUND_IMAGE,
        pack_role="background produce spread",
        working_title="Fresh vegetables spread",
        purpose="Reusable fresh-produce backdrop for ingredient reveal and checklist formats.",
        prompt_or_description="Imported transparent PNG of fresh vegetables for faceless recipe composition.",
        category="scene_setter",
        tags=("vegetables", "fresh", "produce"),
        performance_score=0.8,
        priority=1,
    ),
    CommonsAssetSeed(
        title="File:Chicken and vegetables.png",
        local_name="chicken_and_vegetables.png",
        asset_kind=AssetKind.BACKGROUND_IMAGE,
        pack_role="background meal prep scene",
        working_title="Chicken and vegetables scene",
        purpose="Reusable meal-prep visual for protein-plus-vegetable faceless cooking reels.",
        prompt_or_description="Imported transparent PNG of chicken and vegetables for meal-prep scene setting.",
        category="scene_setter",
        tags=("meal_prep", "protein", "vegetables"),
        performance_score=0.78,
        priority=2,
    ),
    CommonsAssetSeed(
        title="File:Tomato-cut.png",
        local_name="tomato_cut.png",
        asset_kind=AssetKind.TRANSPARENT_CUTOUT_PNG,
        pack_role="foreground ingredient tomato",
        working_title="Cut tomato foreground",
        purpose="Layerable tomato cut-out for recipe steps, mistakes, and ingredient reveals.",
        prompt_or_description="Imported transparent PNG tomato cut-out for overlapping on faceless cooking scenes.",
        category="layerable_cutout",
        tags=("tomato", "ingredient", "fresh"),
        performance_score=0.86,
        priority=3,
    ),
    CommonsAssetSeed(
        title="File:Basil.png",
        local_name="basil.png",
        asset_kind=AssetKind.TRANSPARENT_CUTOUT_PNG,
        pack_role="foreground garnish basil",
        working_title="Basil garnish foreground",
        purpose="Layerable herb garnish for fresh recipe and final-plate overlays.",
        prompt_or_description="Imported transparent PNG basil cut-out for herb garnish overlays.",
        category="layerable_cutout",
        tags=("basil", "herb", "garnish"),
        performance_score=0.84,
        priority=4,
    ),
    CommonsAssetSeed(
        title="File:Bell pepper.png",
        local_name="bell_pepper.png",
        asset_kind=AssetKind.TRANSPARENT_CUTOUT_PNG,
        pack_role="foreground ingredient bell pepper",
        working_title="Bell pepper foreground",
        purpose="Layerable bell pepper for chopping, prep, and colour contrast beats.",
        prompt_or_description="Imported transparent PNG bell pepper cut-out for cooking overlays.",
        category="layerable_cutout",
        tags=("bell_pepper", "vegetable", "colour"),
        performance_score=0.81,
        priority=5,
    ),
    CommonsAssetSeed(
        title="File:Broccoli.png",
        local_name="broccoli.png",
        asset_kind=AssetKind.TRANSPARENT_CUTOUT_PNG,
        pack_role="foreground ingredient broccoli",
        working_title="Broccoli foreground",
        purpose="Layerable green vegetable for healthy cooking and prep-list reels.",
        prompt_or_description="Imported transparent PNG broccoli cut-out for faceless healthy-cooking scenes.",
        category="layerable_cutout",
        tags=("broccoli", "vegetable", "healthy"),
        performance_score=0.79,
        priority=6,
    ),
    CommonsAssetSeed(
        title="File:Cut eggplant.png",
        local_name="cut_eggplant.png",
        asset_kind=AssetKind.TRANSPARENT_CUTOUT_PNG,
        pack_role="foreground ingredient eggplant",
        working_title="Cut eggplant foreground",
        purpose="Layerable eggplant for roasting, ratatouille, and before-after prep reels.",
        prompt_or_description="Imported transparent PNG cut eggplant for overlapping in faceless cooking compositions.",
        category="layerable_cutout",
        tags=("eggplant", "vegetable", "ratatouille"),
        performance_score=0.78,
        priority=7,
    ),
    CommonsAssetSeed(
        title="File:Ginger.png",
        local_name="ginger.png",
        asset_kind=AssetKind.TRANSPARENT_CUTOUT_PNG,
        pack_role="foreground ingredient ginger",
        working_title="Ginger foreground",
        purpose="Layerable aromatics visual for flavour-building recipe steps.",
        prompt_or_description="Imported transparent PNG ginger cut-out for recipe aromatics overlays.",
        category="layerable_cutout",
        tags=("ginger", "aromatic", "flavour"),
        performance_score=0.76,
        priority=8,
    ),
    CommonsAssetSeed(
        title="File:Habanero.png",
        local_name="habanero.png",
        asset_kind=AssetKind.TRANSPARENT_CUTOUT_PNG,
        pack_role="foreground ingredient chilli",
        working_title="Habanero foreground",
        purpose="Layerable chilli visual for heat, spice, and caution/mistake formats.",
        prompt_or_description="Imported transparent PNG habanero cut-out for spice-level cooking overlays.",
        category="layerable_cutout",
        tags=("habanero", "chilli", "spice"),
        performance_score=0.75,
        priority=9,
    ),
    CommonsAssetSeed(
        title="File:Jalape\u00f1o cut.png",
        local_name="jalapeno_cut.png",
        asset_kind=AssetKind.TRANSPARENT_CUTOUT_PNG,
        pack_role="foreground ingredient jalapeno",
        working_title="Cut jalapeno foreground",
        purpose="Layerable chilli slice for fast flavour and ingredient-swap reels.",
        prompt_or_description="Imported transparent PNG cut jalapeno for faceless cooking overlays.",
        category="layerable_cutout",
        tags=("jalapeno", "chilli", "ingredient_swap"),
        performance_score=0.74,
        priority=10,
    ),
    CommonsAssetSeed(
        title="File:Chicken egg.png",
        local_name="chicken_egg.png",
        asset_kind=AssetKind.TRANSPARENT_CUTOUT_PNG,
        pack_role="foreground ingredient egg",
        working_title="Chicken egg foreground",
        purpose="Layerable egg visual for baking, breakfast, and protein-prep formats.",
        prompt_or_description="Imported transparent PNG chicken egg for recipe step overlays.",
        category="layerable_cutout",
        tags=("egg", "protein", "baking"),
        performance_score=0.77,
        priority=11,
    ),
    CommonsAssetSeed(
        title="File:Fresh yeast.png",
        local_name="fresh_yeast.png",
        asset_kind=AssetKind.TRANSPARENT_CUTOUT_PNG,
        pack_role="foreground ingredient yeast",
        working_title="Fresh yeast foreground",
        purpose="Layerable baking ingredient for dough, bread, and fermentation explainers.",
        prompt_or_description="Imported transparent PNG fresh yeast for baking-process overlays.",
        category="layerable_cutout",
        tags=("yeast", "baking", "fermentation"),
        performance_score=0.7,
        priority=12,
    ),
    CommonsAssetSeed(
        title="File:Goat cheese.png",
        local_name="goat_cheese.png",
        asset_kind=AssetKind.TRANSPARENT_CUTOUT_PNG,
        pack_role="foreground ingredient cheese",
        working_title="Goat cheese foreground",
        purpose="Layerable dairy visual for salad, topping, and upgrade-tip reels.",
        prompt_or_description="Imported transparent PNG goat cheese for ingredient upgrade overlays.",
        category="layerable_cutout",
        tags=("cheese", "dairy", "topping"),
        performance_score=0.72,
        priority=13,
    ),
    CommonsAssetSeed(
        title="File:Bowl of chopped almonds no bg.png",
        local_name="bowl_chopped_almonds.png",
        asset_kind=AssetKind.PROP_IMAGE,
        pack_role="foreground prep bowl",
        working_title="Chopped almonds prep bowl",
        purpose="Layerable bowl prop for texture, topping, and mise-en-place shots.",
        prompt_or_description="Imported transparent PNG prep bowl of chopped almonds for faceless cooking overlays.",
        category="detail_prop",
        tags=("almonds", "bowl", "topping"),
        performance_score=0.73,
        priority=14,
    ),
    CommonsAssetSeed(
        title="File:Avocado.png",
        local_name="avocado.png",
        asset_kind=AssetKind.TRANSPARENT_CUTOUT_PNG,
        pack_role="foreground ingredient avocado",
        working_title="Avocado foreground",
        purpose="Layerable avocado cut-out for healthy bowls, toast, and ingredient-swap reels.",
        prompt_or_description="Imported transparent PNG avocado cut-out for faceless cooking overlays.",
        category="layerable_cutout",
        tags=("avocado", "ingredient", "healthy"),
        performance_score=0.8,
        priority=15,
    ),
    CommonsAssetSeed(
        title="File:Brussels sprout.png",
        local_name="brussels_sprout.png",
        asset_kind=AssetKind.TRANSPARENT_CUTOUT_PNG,
        pack_role="foreground ingredient brussels sprout",
        working_title="Brussels sprout foreground",
        purpose="Layerable vegetable cut-out for roasting, prep-list, and seasonal recipe reels.",
        prompt_or_description="Imported transparent PNG Brussels sprout cut-out for cooking overlays.",
        category="layerable_cutout",
        tags=("brussels_sprout", "vegetable", "roasting"),
        performance_score=0.74,
        priority=16,
    ),
    CommonsAssetSeed(
        title="File:Lettuce.png",
        local_name="lettuce.png",
        asset_kind=AssetKind.TRANSPARENT_CUTOUT_PNG,
        pack_role="foreground ingredient lettuce",
        working_title="Lettuce foreground",
        purpose="Layerable lettuce cut-out for salad, wrap, and freshness cue compositions.",
        prompt_or_description="Imported transparent PNG lettuce cut-out for faceless cooking overlays.",
        category="layerable_cutout",
        tags=("lettuce", "salad", "fresh"),
        performance_score=0.76,
        priority=17,
    ),
    CommonsAssetSeed(
        title="File:Leek on transparent background - 0947.png",
        local_name="leek.png",
        asset_kind=AssetKind.TRANSPARENT_CUTOUT_PNG,
        pack_role="foreground ingredient leek",
        working_title="Leek foreground",
        purpose="Layerable leek cut-out for soup, prep, and aromatic base recipe reels.",
        prompt_or_description="Imported transparent PNG leek cut-out for faceless cooking overlays.",
        category="layerable_cutout",
        tags=("leek", "aromatic", "soup"),
        performance_score=0.75,
        priority=18,
    ),
    CommonsAssetSeed(
        title="File:Bowl of melted butter no bg.png",
        local_name="bowl_melted_butter.png",
        asset_kind=AssetKind.PROP_IMAGE,
        pack_role="foreground prep bowl",
        working_title="Melted butter prep bowl",
        purpose="Layerable bowl prop for baking, sauce-building, and gloss finish recipe steps.",
        prompt_or_description="Imported transparent PNG prep bowl of melted butter for cooking overlays.",
        category="detail_prop",
        tags=("butter", "bowl", "baking"),
        performance_score=0.72,
        priority=19,
    ),
)


def main() -> None:
    args = parse_args()
    settings = Settings()
    database_url = args.database_url or settings.database_url
    artifact_dir = Path(args.artifact_dir or REPO_ROOT / "artifacts" / "asset_packs" / "faceless_cooking_real_png")
    run_dir = artifact_dir / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {len(ASSET_SEEDS)} Wikimedia Commons PNG assets into {run_dir}")
    image_infos = fetch_commons_image_infos([seed.title for seed in ASSET_SEEDS])
    downloads = download_assets(run_dir, image_infos)

    engine = create_engine(database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    with SessionLocal() as db:
        org = get_org(db, slug=args.org_slug, org_id=args.org_id)
        demo_page = ensure_demo_page(db, org_id=org.id) if args.create_demo_page else None
        pack = create_pack(db, org_id=org.id, pack_name=args.pack_name)
        summary_assets: list[dict[str, Any]] = []
        request = SimpleNamespace(state=SimpleNamespace(actor="seed_faceless_cooking_asset_pack"))
        for seed in ASSET_SEEDS:
            info = image_infos[seed.title]
            path = downloads[seed.title]
            data = path.read_bytes()
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
                    "filename": path.name,
                    "content_hash": asset.content_hash,
                    "storage_uri": asset.storage_uri,
                    "source_page": info["descriptionurl"],
                    "download_url": info["url"],
                    "license": info["license_short_name"],
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
            "demo_page_id": None if demo_page is None else str(demo_page.id),
            "demo_page_name": None if demo_page is None else demo_page.display_name,
            "asset_pack_id": str(pack.id),
            "asset_pack_name": pack.name,
            "niche": pack.niche,
            "requested_asset_count": pack.requested_asset_count,
            "artifact_dir": str(run_dir),
            "asset_count": len(summary_assets),
            "by_kind": by_kind(summary_assets),
            "assets": summary_assets,
        }
        (run_dir / "summary.json").write_text(
            json.dumps(result, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(json.dumps(result, indent=2, sort_keys=True))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed a faceless-cooking asset pack with real online PNG assets."
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--org-id", default=None)
    parser.add_argument("--org-slug", default="default")
    parser.add_argument(
        "--pack-name",
        default="faceless cooking png test pack online",
    )
    parser.add_argument("--artifact-dir", default=None)
    parser.add_argument(
        "--create-demo-page",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Create or update the Faceless Cooking Demo page for the local web UI.",
    )
    return parser.parse_args()


def get_org(db: Session, *, slug: str, org_id: str | None) -> Org:
    if org_id:
        parsed_org_id = uuid.UUID(org_id)
        org = db.get(Org, parsed_org_id)
        if org is None:
            org = Org(
                name="Local Operator Org",
                slug=f"local-operator-{str(parsed_org_id)[:8]}",
            )
            org.id = parsed_org_id
            db.add(org)
            db.commit()
            db.refresh(org)
        return org

    org = db.scalars(select(Org).where(Org.slug == slug)).one_or_none()
    if org is None and slug != "default":
        org = db.scalars(select(Org).where(Org.slug == "default")).one_or_none()
    if org is None:
        raise RuntimeError("No target org found; create an org before seeding assets")
    return org


def ensure_demo_page(db: Session, *, org_id: uuid.UUID) -> Page:
    page = (
        db.query(Page)
        .filter(Page.org_id == org_id, Page.handle == "@faceless_cooking_demo")
        .one_or_none()
    )
    metadata: dict[str, object] = {
        "persona": {
            "label": "Faceless cooking",
            "audience": "Home cooks who want clear, saveable recipe prep tips.",
            "brand_tone": ["useful", "clear", "calm"],
            "content_pillars": ["recipe prep", "ingredient prep", "kitchen shortcuts"],
            "differentiators": ["faceless", "ingredient-first", "no generation assets"],
            "primary_call_to_action": "Save this recipe prep tip.",
            "extensions": {},
        },
        "constraints": {
            "banned_topics": [],
            "blocked_phrases": [],
            "required_disclosures": [],
            "prohibited_claims": [],
            "preferred_languages": ["en"],
            "allow_direct_cta": True,
            "max_script_words": 80,
            "max_hashtags": 4,
        },
    }
    if page is None:
        page = Page(
            org_id=org_id,
            platform="instagram",
            display_name="Faceless Cooking Demo",
            external_page_id=None,
            handle="@faceless_cooking_demo",
            kind=PageKind.OWNED.value,
            metadata_=metadata,
        )
        db.add(page)
    else:
        page.platform = "instagram"
        page.display_name = "Faceless Cooking Demo"
        page.kind = PageKind.OWNED.value
        page.metadata_ = metadata
    db.commit()
    db.refresh(page)
    return page


def create_pack(db: Session, *, org_id: uuid.UUID, pack_name: str) -> AssetPack:
    asset_mix = {
        AssetKind.BACKGROUND_IMAGE.value: 3,
        AssetKind.TRANSPARENT_CUTOUT_PNG.value: 15,
        AssetKind.PROP_IMAGE.value: 2,
    }
    pack = AssetPack(
        org_id=org_id,
        name=pack_name,
        niche="faceless cooking",
        purpose=(
            "Real online PNG ingredient and food-prep assets for faceless cooking "
            "compositions. This seed performs no asset generation."
        ),
        target_audience="Operators building ready-to-post faceless cooking reels.",
        requested_asset_count=len(ASSET_SEEDS),
        asset_mix_requested_json=asset_mix,
        asset_mix_final_json=asset_mix,
        status=AssetPackStatus.APPROVED.value,
        strategy_summary=(
            "Imported Wikimedia Commons PNG assets selected for layered cooking "
            "compositions: produce scene setters, ingredient cut-outs, and one prep prop."
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
    seed: CommonsAssetSeed,
) -> PlannedAssetSpec:
    compatibility = compatibility_for_seed(seed).model_dump(mode="python")
    spec = PlannedAssetSpec(
        asset_pack_id=asset_pack_id,
        asset_kind=seed.asset_kind.value,
        media_type=MediaType.IMAGE.value,
        working_title=seed.working_title,
        purpose=seed.purpose,
        prompt_or_description=seed.prompt_or_description,
        required_traits={
            "category": seed.category,
            "faceless": True,
            "no_people": True,
            "online_source_only": True,
            "generation_allowed": False,
            "layerable": True,
            "caption_safe": seed.asset_kind is AssetKind.BACKGROUND_IMAGE,
            "tags": list(seed.tags),
            "output_potential": {
                "score": round(seed.performance_score * 100, 2),
                "rationale": [
                    "Real PNG source asset selected for reusable overlapping compositions.",
                    "Avoids generation while increasing the visual asset bank for this niche.",
                ],
            },
        },
        compatible_with={
            "reel_formats": [
                "ingredient reveal",
                "step-by-step demo",
                "saveable checklist",
                "mistake-fix explainer",
            ],
            "works_with": [
                "caption overlays",
                "ingredient labels",
                "top-down prep scenes",
                "faceless hands-free edits",
            ],
        },
        compatibility_metadata=compatibility,
        intended_reel_formats=[
            "ingredient reveal",
            "step-by-step demo",
            "saveable checklist",
            "mistake-fix explainer",
        ],
        priority=seed.priority,
        estimated_reuse_count=6,
        status=PlannedAssetSpecStatus.PLANNED.value,
    )
    db.add(spec)
    db.commit()
    db.refresh(spec)
    return spec


def source_register_request(
    *,
    seed: CommonsAssetSeed,
    info: dict[str, Any],
    data: bytes,
    spec_id: uuid.UUID,
) -> SourceAssetRegisterRequest:
    visual = detect_png_visual_metadata(data)
    transparency = detect_png_transparency(data)
    validate_seed_png(seed=seed, data=data, transparency=transparency)
    source_meta = AssetSourceMetadata(
        source_type=AssetSourceType.APPROVED_EXTERNAL_SOURCE,
        source_provider="Wikimedia Commons",
        external_source_url=info["descriptionurl"],
        source_reference_id=seed.title,
        licence_type=info["license_short_name"],
        licence_notes=info["license_url"],
        usage_allowed=True,
        commercial_use_allowed=True,
        attribution_required=info["attribution_required"],
        attribution_text=info["attribution_text"],
        imported_by="seed_faceless_cooking_asset_pack",
        original_content_hash=hashlib.sha256(data).hexdigest(),
        source_quality_score=0.92,
        source_risk_notes="Imported from Wikimedia Commons file metadata; no generation used.",
    )
    metadata = {
        "title": seed.working_title,
        "asset_pack_niche": "faceless cooking",
        "pack_role": seed.pack_role,
        "category": seed.category,
        "tags": list(seed.tags),
        "performance_score": seed.performance_score,
        "intended_reel_formats": [
            "ingredient reveal",
            "step-by-step demo",
            "saveable checklist",
            "mistake-fix explainer",
        ],
        "compatibility": compatibility_for_seed(seed).model_dump(mode="python"),
        "source": {
            "provider": "Wikimedia Commons",
            "file_title": seed.title,
            "file_page": info["descriptionurl"],
            "download_url": info["url"],
            "license": info["license_short_name"],
            "license_url": info["license_url"],
            "artist": info["artist"],
            "credit": info["credit"],
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
        priority=seed.priority,
        planned_asset_spec_id=spec_id,
        filename=seed.local_name,
        content_type="image/png",
        data_base64=base64.b64encode(data).decode("ascii"),
        width=None if visual is None else visual.width,
        height=None if visual is None else visual.height,
        metadata=metadata,
        source_metadata=source_meta,
    )


def compatibility_for_seed(seed: CommonsAssetSeed) -> AssetCompatibilityMetadata:
    base: dict[str, Any] = {
        "niche": ["faceless cooking"],
        "topic": ["recipe prep", "ingredient prep", "home cooking"],
        "theme": ["clean prep", "ingredient reveal", *seed.tags],
        "emotion": ["useful", "fresh", "calm"],
        "visual_style": ["real food png", "faceless", "platform native"],
        "pace": ["medium", "snappy"],
        "format_type": [
            "ingredient reveal",
            "step-by-step demo",
            "saveable checklist",
            "mistake-fix explainer",
        ],
    }
    if seed.asset_kind is AssetKind.BACKGROUND_IMAGE:
        base["works_as_background_for"] = [
            AssetKind.TRANSPARENT_CUTOUT_PNG.value,
            AssetKind.PROP_IMAGE.value,
            "foreground",
            "object",
            "ingredient",
            "prep_bowl",
        ]
        base["requires_safe_area"] = True
    else:
        base["works_with_object_types"] = [
            seed.category,
            "ingredient",
            "foreground",
            seed.pack_role.replace(" ", "_"),
        ]
        base["requires_transparency"] = seed.asset_kind is AssetKind.TRANSPARENT_CUTOUT_PNG
    return AssetCompatibilityMetadata.model_validate(base)


def fetch_commons_image_infos(titles: list[str]) -> dict[str, dict[str, Any]]:
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

    pages = payload["query"]["pages"].values()
    infos: dict[str, dict[str, Any]] = {}
    for page in pages:
        title = page["title"]
        if "missing" in page:
            raise RuntimeError(f"Commons file not found: {title}")
        imageinfo = page["imageinfo"][0]
        if imageinfo.get("mime") != "image/png":
            raise RuntimeError(f"{title} is not image/png: {imageinfo.get('mime')}")
        ext = imageinfo.get("extmetadata", {})
        infos[title] = {
            "url": imageinfo["url"],
            "descriptionurl": imageinfo["descriptionurl"],
            "size": imageinfo.get("size"),
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


def download_assets(run_dir: Path, infos: dict[str, dict[str, Any]]) -> dict[str, Path]:
    downloads: dict[str, Path] = {}
    for seed in ASSET_SEEDS:
        info = infos[seed.title]
        path = run_dir / seed.local_name
        data = path.read_bytes() if path.exists() else download_with_retry(info["url"])
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError(f"{seed.title} did not download as a PNG")
        path.write_bytes(data)
        downloads[seed.title] = path
    return downloads


def validate_seed_png(
    *,
    seed: CommonsAssetSeed,
    data: bytes,
    transparency: Any,
) -> None:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError(f"{seed.title} is not a PNG")
    if seed.asset_kind is AssetKind.BACKGROUND_IMAGE:
        return
    if not bool(transparency.has_transparency):
        raise RuntimeError(
            f"{seed.title} is not layerable: non-background pack assets must have PNG transparency"
        )


def download_with_retry(url: str) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, 7):
        try:
            with urllib.request.urlopen(request(url), timeout=180) as response:
                content_type = response.headers.get("content-type", "").split(";", 1)[0]
                if content_type != "image/png":
                    raise RuntimeError(f"Download is not image/png: {content_type}")
                return response.read()
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504}:
                raise
            retry_after = exc.headers.get("retry-after")
            delay = int(retry_after) if retry_after and retry_after.isdigit() else 5 * attempt
            time.sleep(delay)
        except URLError as exc:
            last_error = exc
            time.sleep(5 * attempt)
    raise RuntimeError(f"Unable to download after retries: {url}") from last_error


def request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def ext_value(extmetadata: dict[str, Any], key: str) -> str | None:
    value = extmetadata.get(key, {}).get("value")
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def strip_html(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"<[^>]+>", "", value)
    text = html.unescape(text)
    text = " ".join(text.split())
    return text or None


def is_attribution_required(license_short_name: str | None) -> bool:
    if not license_short_name:
        return True
    normalized = license_short_name.lower()
    return not any(token in normalized for token in ("public domain", "cc0", "pd"))


def attribution_text(title: str, info: dict[str, Any]) -> str:
    artist = info.get("artist") or "Wikimedia Commons contributor"
    license_short_name = info.get("license_short_name") or "license metadata unavailable"
    return f"{title} by {artist}, {license_short_name}, via Wikimedia Commons: {info['descriptionurl']}"


def by_kind(assets: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for asset in assets:
        kind = str(asset["asset_kind"])
        counts[kind] = counts.get(kind, 0) + 1
    return dict(sorted(counts.items()))


if __name__ == "__main__":
    main()
