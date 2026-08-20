from __future__ import annotations

from content_lab_editing.reel_timeline_schema import ReelTimeline
from content_lab_editing.relationship_layout import enforce_relationship_layout, object_bounds


def _object(object_id: str, role: str, *, x: float, y: float, z: float) -> dict[str, object]:
    return {
        "object_id": object_id,
        "asset_id": object_id,
        "scene_id": "scene_1",
        "role": role,
        "start_time": 0.0,
        "end_time": 4.0,
        "x": x,
        "y": y,
        "z": z,
        "scale": 1.0,
        "width_normalised": 0.4,
        "height_normalised": 0.3,
        "opacity": 1.0,
    }


def _timeline(objects: list[dict[str, object]]) -> ReelTimeline:
    return ReelTimeline.model_validate(
        {
            "plan_id": "relationship_render",
            "total_duration_seconds": 4.0,
            "fps": 24,
            "canvas": {"aspect_ratio": "9:16", "width": 1080, "height": 1920},
            "objects": objects,
            "captions": [],
            "camera_moves": [],
            "audio_layers": [],
        }
    )


def test_required_overlap_below_threshold_fails() -> None:
    surface = _object("surface", "environment_base", x=0.2, y=0.2, z=0.05)
    prop = _object("prop", "supporting_subject", x=0.8, y=0.8, z=0.7)
    prop.update(
        {
            "spatial_relationship": "on_surface",
            "support_object_id": "surface",
            "required_overlap_ratio": 0.25,
            "relative_depth_rule": "above_support",
        }
    )

    report = enforce_relationship_layout(_timeline([surface, prop]))

    assert "relationship_required_overlap_not_met" in report.as_dict()["failure_codes"]


def test_inside_support_bounds_passes() -> None:
    container = _object("container", "environment_base", x=0.5, y=0.5, z=0.2)
    container["width_normalised"] = 0.8
    container["height_normalised"] = 0.8
    prop = _object("prop", "supporting_subject", x=0.5, y=0.5, z=0.5)
    prop.update(
        {
            "spatial_relationship": "inside",
            "support_object_id": "container",
            "required_overlap_ratio": 0.8,
            "must_remain_inside_support_bounds": True,
            "relative_depth_rule": "above_support",
        }
    )

    report = enforce_relationship_layout(_timeline([container, prop]))

    assert report.passed is True


def test_behind_hero_with_higher_z_fails() -> None:
    hero = _object("hero", "hero_subject", x=0.5, y=0.5, z=0.6)
    reveal = _object("reveal", "background_reveal", x=0.1, y=0.5, z=0.8)
    reveal["relative_depth_rule"] = "behind_hero"

    report = enforce_relationship_layout(_timeline([hero, reveal]))

    assert "behind_hero_depth_invalid" in report.as_dict()["failure_codes"]


def test_background_reveal_overlapping_hero_too_much_fails() -> None:
    hero = _object("hero", "hero_subject", x=0.5, y=0.5, z=0.7)
    reveal = _object("reveal", "background_reveal", x=0.5, y=0.5, z=0.2)
    reveal["relative_depth_rule"] = "behind_hero"
    reveal["max_overlap_ratio"] = 0.1

    report = enforce_relationship_layout(_timeline([hero, reveal]))

    assert "background_reveal_overlaps_hero" in report.as_dict()["failure_codes"]


def test_renderer_does_not_auto_remove_invalid_background_reveal() -> None:
    hero = _object("hero", "hero_subject", x=0.5, y=0.5, z=0.7)
    reveal = _object("plant_accent", "background_reveal", x=0.5, y=0.5, z=0.2)
    reveal["relative_depth_rule"] = "behind_hero"
    timeline = _timeline([hero, reveal])

    report = enforce_relationship_layout(timeline)

    assert "background_reveal_overlaps_hero" in report.as_dict()["failure_codes"]
    assert [item.object_id for item in timeline.objects] == ["hero", "plant_accent"]


def test_valid_background_reveal_behind_hero_passes() -> None:
    hero = _object("hero", "hero_subject", x=0.5, y=0.5, z=0.7)
    reveal = _object("plant_accent", "background_reveal", x=0.85, y=0.2, z=0.2)
    reveal.update(
        {
            "scale": 0.45,
            "opacity": 0.6,
            "relative_depth_rule": "behind_hero",
            "max_overlap_ratio": 0.1,
            "preferred_screen_regions": ["upper_right"],
        }
    )

    report = enforce_relationship_layout(_timeline([hero, reveal]))

    assert report.passed is True


def test_expected_support_mask_missing_blocks_render() -> None:
    surface = _object("pan", "environment_base", x=0.5, y=0.5, z=0.05)
    surface["support_surface_mask_uri"] = "s3://masks/pan-bowl.png"
    hero = _object("steak", "hero_subject", x=0.5, y=0.5, z=0.7)
    hero.update(
        {
            "spatial_relationship": "on_surface",
            "support_object_id": "pan",
            "required_overlap_ratio": 0.1,
            "relative_depth_rule": "above_support",
        }
    )

    report = enforce_relationship_layout(_timeline([surface, hero]))

    assert "on_surface_support_mask_unavailable" in report.as_dict()["failure_codes"]


def test_contact_shadow_target_missing_fails() -> None:
    surface = _object("surface", "environment_base", x=0.5, y=0.5, z=0.05)
    prop = _object("prop", "supporting_subject", x=0.5, y=0.5, z=0.7)
    prop.update(
        {
            "spatial_relationship": "on_surface",
            "support_object_id": "surface",
            "required_overlap_ratio": 0.1,
            "support_contact_required": True,
            "contact_shadow_target_object_id": "missing",
        }
    )

    report = enforce_relationship_layout(_timeline([surface, prop]))

    assert "contact_shadow_target_not_found" in report.as_dict()["failure_codes"]


def test_renderer_computes_bounds_from_normalized_coordinates() -> None:
    item = _timeline([_object("hero", "hero_subject", x=0.5, y=0.5, z=0.7)]).objects[0]

    bounds = object_bounds(item)

    assert bounds["left"] == 0.3
    assert bounds["right"] == 0.7
    assert bounds["top"] == 0.35
    assert bounds["bottom"] == 0.65


def test_valid_supported_composition_passes() -> None:
    surface = _object("surface", "environment_base", x=0.5, y=0.5, z=0.05)
    surface["width_normalised"] = 0.9
    surface["height_normalised"] = 0.8
    hero = _object("hero", "hero_subject", x=0.5, y=0.5, z=0.7)
    hero.update(
        {
            "spatial_relationship": "on_surface",
            "support_object_id": "surface",
            "required_overlap_ratio": 0.1,
            "support_contact_required": True,
            "contact_shadow_target_object_id": "surface",
            "relative_depth_rule": "above_support",
            "shadow_spec": {"contact_shadow_required": True},
        }
    )

    report = enforce_relationship_layout(_timeline([surface, hero]))

    assert report.passed is True
