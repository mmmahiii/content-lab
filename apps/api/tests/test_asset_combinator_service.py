from __future__ import annotations

import uuid

from sqlalchemy import insert
from sqlalchemy.orm import Session

from content_lab_api.models import Asset, AssetPack, AssetPackItem, Org
from content_lab_api.services import (
    build_asset_pack_compositions,
    estimate_asset_pack_output_potential,
)


def test_asset_pack_combinator_loads_pack_and_filters_candidates(db_session: Session) -> None:
    org_id = uuid.uuid4()
    pack_id = uuid.uuid4()
    bg_id = uuid.uuid4()
    object_id = uuid.uuid4()
    hook_id = uuid.uuid4()
    audio_id = uuid.uuid4()
    db_session.execute(
        insert(Org).values(id=org_id, name="Combo Org", slug=f"combo-{org_id.hex[:8]}")
    )
    db_session.execute(
        insert(AssetPack).values(
            id=pack_id,
            org_id=org_id,
            name="Pilates combos",
            niche="pilates",
        )
    )
    for asset_id, storage_uri in {
        bg_id: "s3://content-lab/assets/bg.mp4",
        object_id: "s3://content-lab/assets/object.png",
        hook_id: "s3://content-lab/assets/hook.txt",
        audio_id: "s3://content-lab/assets/audio.mp3",
    }.items():
        db_session.execute(
            insert(Asset).values(
                id=asset_id,
                org_id=org_id,
                asset_class="component",
                storage_uri=storage_uri,
            )
        )

    def add_item(
        *,
        asset_id: uuid.UUID,
        asset_kind: str,
        pack_role: str,
        compatibility: dict[str, object],
        performance_score: float = 0.5,
    ) -> None:
        db_session.execute(
            insert(AssetPackItem).values(
                id=uuid.uuid4(),
                asset_pack_id=pack_id,
                asset_id=asset_id,
                asset_kind=asset_kind,
                pack_role=pack_role,
                status="selected",
                compatibility_metadata=compatibility,
                metadata_json={"performance_score": performance_score},
            )
        )

    add_item(
        asset_id=bg_id,
        asset_kind="background_video",
        pack_role="background",
        performance_score=0.8,
        compatibility={
            "niche": ["pilates"],
            "visual_style": ["clean"],
            "format_type": ["hook-led tip"],
            "works_as_background_for": ["transparent_cutout_png"],
        },
    )
    add_item(
        asset_id=object_id,
        asset_kind="transparent_cutout_png",
        pack_role="object",
        performance_score=0.7,
        compatibility={
            "niche": ["pilates"],
            "visual_style": ["clean"],
            "format_type": ["hook-led tip"],
            "requires_transparency": True,
        },
    )
    add_item(
        asset_id=hook_id,
        asset_kind="hook_text",
        pack_role="hook",
        performance_score=0.9,
        compatibility={
            "niche": ["pilates"],
            "visual_style": ["clean"],
            "format_type": ["hook-led tip"],
        },
    )
    add_item(
        asset_id=audio_id,
        asset_kind="audio_track",
        pack_role="audio",
        performance_score=0.4,
        compatibility={
            "niche": ["pilates"],
            "visual_style": ["clean"],
            "format_type": ["hook-led tip"],
        },
    )
    db_session.flush()

    candidates = build_asset_pack_compositions(
        db_session,
        org_id=org_id,
        asset_pack_id=pack_id,
        target_reel_count=3,
        format_filters=["hook-led tip"],
        style_filters=["clean"],
        selection_mode="exploit",
    )
    estimate = estimate_asset_pack_output_potential(
        db_session,
        org_id=org_id,
        asset_pack_id=pack_id,
        target_reel_count=3,
    )

    assert candidates
    assert candidates[0].roles["background"].asset_id == str(bg_id)
    assert candidates[0].roles["hook"].asset_id == str(hook_id)
    assert estimate.valid_combination_count >= 1
