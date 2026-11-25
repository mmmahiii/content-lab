from __future__ import annotations

import pytest

from content_lab_creative.niche import (
    GENERAL_NICHE_KEY,
    NicheProfile,
    is_single_instance_token,
    keyword_ranked_prompt_paths,
    niche_from_mapping,
    register_niche_profile,
    registered_niche_profiles,
    resolve_niche_profile,
    single_instance_objects_for,
)
from content_lab_creative.prompt_paths import PROMPT_PATHS


def test_resolve_by_key_alias_and_keywords() -> None:
    assert resolve_niche_profile("fitness").key == "fitness"
    assert resolve_niche_profile("Faceless Cooking").key == "cooking"
    assert resolve_niche_profile(None, text="a steak recipe").key == "cooking"
    assert resolve_niche_profile("baking breads").key == "cooking"
    assert resolve_niche_profile(None, text="knitting patterns").key == GENERAL_NICHE_KEY


def test_every_profile_uses_real_prompt_paths() -> None:
    for profile in registered_niche_profiles():
        assert set(profile.prompt_paths) <= set(PROMPT_PATHS), profile.key


def test_single_instance_rules_are_niche_scoped() -> None:
    cooking = resolve_niche_profile("cooking")
    luxury = resolve_niche_profile("luxury")
    general = resolve_niche_profile(None, text="")
    assert single_instance_objects_for(cooking) == ("pan",)
    assert single_instance_objects_for(luxury) == ()
    # Unknown content keeps every registered guard.
    assert "pan" in single_instance_objects_for(general)


@pytest.mark.parametrize(
    ("token", "expected"),
    [("pan", True), ("pan2", True), ("pan1test", True), ("pans", False), ("panorama", False)],
)
def test_single_instance_token_matching(token: str, expected: bool) -> None:
    assert is_single_instance_token(token, "pan") is expected


def test_keyword_ranking_keeps_original_order_for_original_niches() -> None:
    assert keyword_ranked_prompt_paths("kitchen founder")[:6] == [
        "sensory_hook",
        "satisfying_process",
        "cinematic_closeup",
        "problem_solution",
        "educational_overlay",
        "social_proof",
    ]


def test_niche_from_nested_mapping() -> None:
    assert niche_from_mapping({"page": {"metadata": {"niche": "travel"}}}) == "travel"
    assert niche_from_mapping({"niche_key": "beauty"}) == "beauty"
    assert niche_from_mapping({"page_name": "x"}) is None


def test_register_custom_niche() -> None:
    profile = NicheProfile(
        key="pottery_test",
        label="Pottery",
        keywords=("pottery", "ceramic"),
        prompt_paths=("satisfying_process",),
        single_instance_objects=("wheel",),
    )
    register_niche_profile(profile)
    try:
        assert resolve_niche_profile(None, text="ceramic mugs").key == "pottery_test"
        with pytest.raises(ValueError):
            register_niche_profile(profile)
        with pytest.raises(ValueError):
            register_niche_profile(NicheProfile(key="general", label="x"))
    finally:
        from content_lab_creative import niche as niche_module

        niche_module._REGISTRY.pop("pottery_test", None)
