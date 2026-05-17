from __future__ import annotations

import json
import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, update
from sqlalchemy.orm import Session

from content_lab_api.deps import get_db
from content_lab_api.main import app
from content_lab_api.models import Asset, AssetPack, AssetPackItem, Org, Page
from content_lab_creative.single_prompt_reel_planner import PLANNING_PROMPT_VERSION


@pytest.fixture
def cinematic_client(db_session: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def _seed_pack(db_session: Session) -> dict[str, uuid.UUID]:
    org_id = uuid.uuid4()
    page_id = uuid.uuid4()
    pack_id = uuid.uuid4()
    bg_id = uuid.uuid4()
    subject_id = uuid.uuid4()
    audio_id = uuid.uuid4()
    db_session.execute(insert(Org).values(id=org_id, name="Cinema Org", slug=f"cinema-{org_id.hex[:8]}"))
    db_session.execute(
        insert(Page).values(
            id=page_id,
            org_id=org_id,
            platform="instagram",
            display_name="Kitchen Lab",
            handle="@kitchenlab",
            kind="owned",
            metadata_={"niche": "steak cooking"},
        )
    )
    db_session.execute(
        insert(AssetPack).values(
            id=pack_id,
            org_id=org_id,
            name="Steak sensory kit",
            niche="steak cooking",
            purpose="Reusable cinematic food reel components",
            target_audience="home cooks",
        )
    )
    for asset_id, storage_uri in {
        bg_id: "s3://content-lab/assets/kitchen-bg.mp4",
        subject_id: "s3://content-lab/assets/steak-closeup.png",
        audio_id: "s3://content-lab/assets/sizzle.wav",
    }.items():
        db_session.execute(
            insert(Asset).values(
                id=asset_id,
                org_id=org_id,
                asset_class="component",
                storage_uri=storage_uri,
                status="active",
            )
        )
    for priority, (asset_id, asset_kind, pack_role, title) in enumerate(
        [
        (bg_id, "background_video", "background", "Kitchen background"),
        (subject_id, "transparent_cutout_png", "hero subject", "Steak closeup"),
        (audio_id, "sound_effect", "audio", "Oil sizzle"),
        ]
    ):
        db_session.execute(
            insert(AssetPackItem).values(
                id=uuid.uuid4(),
                asset_pack_id=pack_id,
                asset_id=asset_id,
                asset_kind=asset_kind,
                pack_role=pack_role,
                priority=priority,
                status="selected",
                metadata_json={"title": title},
                compatibility_metadata={"niche": ["steak cooking"]},
            )
        )
    db_session.flush()
    return {
        "org_id": org_id,
        "page_id": page_id,
        "pack_id": pack_id,
        "bg_id": bg_id,
        "subject_id": subject_id,
        "audio_id": audio_id,
    }


def _prompt_body(ids: dict[str, uuid.UUID]) -> dict[str, object]:
    return {
        "page_id": str(ids["page_id"]),
        "selected_asset_ids": [
            str(ids["bg_id"]),
            str(ids["subject_id"]),
            str(ids["audio_id"]),
        ],
        "content_goal": "Make steak prep feel cinematic and appetising.",
        "brand_persona_constraints": {"tone": "warm expert"},
        "platform_constraints": {"platform": "instagram", "aspect_ratio": "9:16"},
        "duration_target_seconds": 6.5,
        "pinned_prompt_paths": ["sensory_hook"],
        "banned_prompt_paths": [],
    }


def _motion() -> dict[str, object]:
    return {
        "type": "linear",
        "start_value": {"x": 0.5, "scale": 1.0},
        "end_value": {"x": 0.5, "scale": 1.04},
        "easing": "ease_in_out",
        "jitter_allowed": False,
        "speed": 0.2,
        "sync_to_audio": None,
    }


def _shadow(enabled: bool, *, contact: bool = False) -> dict[str, object]:
    return {
        "enabled": enabled,
        "source_light_id": "key_window" if enabled else None,
        "offset_x": 0.03 if enabled else 0.0,
        "offset_y": 0.05 if enabled else 0.0,
        "blur": 0.22 if contact else 0.55,
        "opacity": 0.42 if enabled else 0.0,
        "softness": 0.55 if contact else 0.9,
        "derived_from_z_depth": True,
        "contact_shadow_required": contact,
    }


def _plan(ids: dict[str, uuid.UUID], input_hash: str, *, hallucinate: bool = False) -> dict[str, object]:
    bg_id = str(ids["bg_id"])
    subject_id = "unselected-asset" if hallucinate else str(ids["subject_id"])
    audio_id = str(ids["audio_id"])
    objects = [
        {
            "object_id": "kitchen_bg",
            "asset_id": bg_id,
            "asset_label": "Kitchen background",
            "role": "environment_base",
            "scene_id": "scene_1",
            "start_time": 0.0,
            "end_time": 6.5,
            "x": 0.5,
            "y": 0.5,
            "z": 0.05,
            "scale": 1.0,
            "width_normalised": 1.0,
            "height_normalised": 1.0,
            "rotation": 0.0,
            "opacity": 1.0,
            "anchor_point": "center",
            "motion_curve": _motion(),
            "shadow_spec": _shadow(False),
            "blur_spec": {"radius": 0.0, "background_blur": 0.0, "motion_blur": 0.0},
            "occlusion_group": "kitchen",
            "realism_reason": "The kitchen layer establishes one coherent filmed environment.",
        },
        {
            "object_id": "steak_hero",
            "asset_id": subject_id,
            "asset_label": "Steak closeup",
            "role": "hero_subject",
            "scene_id": "scene_1",
            "start_time": 0.0,
            "end_time": 6.5,
            "x": 0.5,
            "y": 0.56,
            "z": 0.72,
            "scale": 1.0,
            "width_normalised": 0.62,
            "height_normalised": 0.42,
            "rotation": 0.0,
            "opacity": 1.0,
            "anchor_point": "center",
            "motion_curve": _motion(),
            "shadow_spec": _shadow(True, contact=True),
            "blur_spec": {"radius": 0.0, "background_blur": 0.0, "motion_blur": 0.04},
            "occlusion_group": "tabletop",
            "realism_reason": "The steak is the dominant tactile subject and carries the payoff.",
        },
    ]
    return {
        "plan_id": "plan_api_smoke",
        "page_context_summary": "Kitchen Lab makes sensory steak cooking reels.",
        "content_goal": "Make steak prep feel cinematic and appetising.",
        "selected_prompt_paths": ["sensory_hook", "cinematic_closeup"],
        "narrative_arc": {
            "hook": "Open on the first sizzle.",
            "development": "Push into the steak texture.",
            "reveal_payoff": "Hold on the appetising closeup.",
            "closing_retention_loop": "End on a loopable glisten.",
        },
        "total_duration_seconds": 6.5,
        "fps": 24,
        "canvas": {"aspect_ratio": "9:16", "width": 1080, "height": 1920},
        "scenes": [
            {
                "scene_id": "scene_1",
                "start_time": 0.0,
                "end_time": 6.5,
                "purpose": "One coherent closeup kitchen moment.",
                "dominant_focal_role": "hero_subject",
                "emotional_intent": "Sensory appetite.",
                "visual_density": "low",
                "camera_move": {
                    "move_type": "slow_push_in",
                    "start_time": 0.0,
                    "end_time": 6.5,
                    "crop_x": 0.5,
                    "crop_y": 0.5,
                    "zoom": 1.06,
                    "rotation": 0.0,
                    "shake_intensity": 0.02,
                    "shake_frequency": 6.0,
                    "motion_curve": _motion(),
                },
                "objects": objects,
                "captions": [
                    {
                        "caption_id": "cap_hook",
                        "text": "That first sizzle matters",
                        "role": "hook",
                        "start_time": 0.4,
                        "end_time": 1.8,
                        "x": 0.5,
                        "y": 0.14,
                        "max_width": 0.72,
                        "font_size": 54,
                        "weight": "bold",
                        "alignment": "center",
                        "animation": "fade_up",
                        "safe_area": {
                            "top": 0.08,
                            "right": 0.06,
                            "bottom": 0.08,
                            "left": 0.06,
                        },
                        "safe_area_compliant": True,
                        "renderer_text_only": True,
                    }
                ],
                "audio_layers": [],
                "transition_in": None,
                "transition_out": "loop_to_open",
            }
        ],
        "global_camera_style": "Slow push-in closeup.",
        "global_lighting_style": "Warm window light with soft contact shadows.",
        "caption_strategy": "Sparse editable text in the top safe area.",
        "audio_strategy": "Use selected sizzle audio immediately.",
        "lighting_shadow_plan": {
            "lights": [
                {
                    "light_id": "key_window",
                    "type": "window",
                    "x": 0.2,
                    "y": 0.12,
                    "z": 0.9,
                    "intensity": 1.2,
                    "colour_temperature": 4300,
                    "softness": 0.75,
                }
            ],
            "per_object_shadow_specs": [
                {"object_id": item["object_id"], **item["shadow_spec"]} for item in objects
            ],
            "global_colour_temperature": 4300,
            "contrast_level": "medium",
        },
        "audio_plan": {
            "layers": [
                {
                    "audio_id": "sizzle",
                    "asset_id": audio_id,
                    "role": "sensory_sizzle",
                    "start_time": 0.0,
                    "end_time": 6.5,
                    "volume": 0.85,
                    "fade_in": 0.0,
                    "fade_out": 0.4,
                    "sync_points": [{"time": 0.2, "label": "first_sizzle", "target_object_id": "steak_hero"}],
                }
            ],
            "sync_points": [{"time": 0.2, "label": "first_sizzle", "target_object_id": "steak_hero"}],
            "sensory_moments": ["0.2s first sizzle"],
        },
        "realism_constraints": {
            "dominant_subject_required": True,
            "max_foreground_objects": 3,
            "require_contact_shadows": True,
            "forbid_floating_assets": True,
            "forbid_baked_text": True,
            "forbid_fake_ui": True,
            "require_depth_consistency": True,
            "require_caption_safe_area": True,
            "require_motion_continuity": True,
        },
        "render_notes": ["Use stored registry assets only."],
        "provenance": {
            "input_page_context_hash": input_hash,
            "selected_asset_ids": [bg_id, str(ids["subject_id"]), audio_id],
            "selected_prompt_paths": ["sensory_hook", "cinematic_closeup"],
            "planning_prompt_version": PLANNING_PROMPT_VERSION,
            "plan_hash": "",
            "rejected_assets": [],
            "realism_risk_score": 0.2,
        },
    }


def test_cinematic_prompt_endpoint_builds_manual_master_prompt(
    cinematic_client: TestClient,
    db_session: Session,
) -> None:
    ids = _seed_pack(db_session)

    response = cinematic_client.post(
        f"/orgs/{ids['org_id']}/asset-packs/{ids['pack_id']}/cinematic-plan-prompt",
        json=_prompt_body(ids),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommended_model"] == "gpt-5-mini"
    assert payload["selected_asset_ids"] == [str(ids["bg_id"]), str(ids["subject_id"]), str(ids["audio_id"])]
    assert "Return only valid JSON" in payload["master_prompt"]
    assert "Do not request screenshots" in payload["master_prompt"]
    assert "CRITICAL MANUAL-MODE RULE" in payload["master_prompt"]
    assert "Use the minimum number of selected assets" in payload["master_prompt"]
    assert "no more than 3 visible foreground objects" in payload["master_prompt"]
    assert "Every scene must begin with an environment_base object" in payload["master_prompt"]
    assert "Before returning, silently check" in payload["master_prompt"]
    assert payload["planner_input"]["selected_assets"][0]["possible_cinematic_roles"]


def test_cinematic_prompt_endpoint_rejects_non_png_object_assets(
    cinematic_client: TestClient,
    db_session: Session,
) -> None:
    ids = _seed_pack(db_session)
    db_session.execute(
        update(Asset)
        .where(Asset.id == ids["subject_id"])
        .values(storage_uri="s3://content-lab/assets/steak-closeup.jpg")
    )
    db_session.execute(
        update(AssetPackItem)
        .where(AssetPackItem.asset_id == ids["subject_id"])
        .values(asset_kind="object_image", pack_role="hero subject")
    )
    db_session.flush()

    response = cinematic_client.post(
        f"/orgs/{ids['org_id']}/asset-packs/{ids['pack_id']}/cinematic-plan-prompt",
        json=_prompt_body(ids),
    )

    assert response.status_code == 422
    assert "object assets must be PNG files" in response.json()["detail"]


def test_asset_pack_list_reports_actual_asset_count(
    cinematic_client: TestClient,
    db_session: Session,
) -> None:
    ids = _seed_pack(db_session)

    response = cinematic_client.get(f"/orgs/{ids['org_id']}/asset-packs")

    assert response.status_code == 200
    pack = next(item for item in response.json() if item["id"] == str(ids["pack_id"]))
    assert pack["requested_asset_count"] == 0
    assert pack["actual_asset_count"] == 3


def test_cinematic_validate_endpoint_returns_artifacts(
    cinematic_client: TestClient,
    db_session: Session,
) -> None:
    ids = _seed_pack(db_session)
    prompt_response = cinematic_client.post(
        f"/orgs/{ids['org_id']}/asset-packs/{ids['pack_id']}/cinematic-plan-prompt",
        json=_prompt_body(ids),
    )
    input_hash = prompt_response.json()["input_page_context_hash"]
    body = {**_prompt_body(ids), "raw_plan_json": json.dumps(_plan(ids, input_hash))}

    response = cinematic_client.post(
        f"/orgs/{ids['org_id']}/asset-packs/{ids['pack_id']}/cinematic-plan-validate",
        json=body,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["validation_report"]["passed"] is True
    assert payload["plan_hash"]
    assert payload["artifacts"]["reel_timeline.json"]["objects"][1]["asset_id"] == str(ids["subject_id"])
    assert "realism_qa.json" in payload["artifacts"]


def test_cinematic_validate_endpoint_rejects_hallucinated_asset(
    cinematic_client: TestClient,
    db_session: Session,
) -> None:
    ids = _seed_pack(db_session)
    prompt_response = cinematic_client.post(
        f"/orgs/{ids['org_id']}/asset-packs/{ids['pack_id']}/cinematic-plan-prompt",
        json=_prompt_body(ids),
    )
    input_hash = prompt_response.json()["input_page_context_hash"]
    body = {**_prompt_body(ids), "plan": _plan(ids, input_hash, hallucinate=True)}

    response = cinematic_client.post(
        f"/orgs/{ids['org_id']}/asset-packs/{ids['pack_id']}/cinematic-plan-validate",
        json=body,
    )

    assert response.status_code == 422
    assert "unselected assets" in response.json()["detail"]


def test_cinematic_prompt_endpoint_enforces_selected_assets_are_pack_members(
    cinematic_client: TestClient,
    db_session: Session,
) -> None:
    ids = _seed_pack(db_session)
    body = _prompt_body(ids)
    body["selected_asset_ids"] = [str(uuid.uuid4())]

    response = cinematic_client.post(
        f"/orgs/{ids['org_id']}/asset-packs/{ids['pack_id']}/cinematic-plan-prompt",
        json=body,
    )

    assert response.status_code == 422
    assert "not members of this pack" in response.json()["detail"]
