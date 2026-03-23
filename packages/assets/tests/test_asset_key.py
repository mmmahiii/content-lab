from __future__ import annotations

import hashlib
import uuid
from typing import Any

import pytest

from content_lab_assets.asset_key import (
    Phase1ProviderLockError,
    build_asset_key,
    validate_phase1_provider_model,
)
from content_lab_assets.canonicalise import (
    canonicalise_runway_gen45_generation,
    serialise_canonical_payload,
)


def _base_generation_request(*, reference_asset_ids: list[uuid.UUID]) -> dict[str, Any]:
    return {
        "asset_class": " Clip ",
        "provider": " Runway ",
        "model": " GEN4.5 ",
        "prompt": " Hero   launch   shot ",
        "negative_prompt": " no   text overlays ",
        "seed": 7,
        "duration_seconds": 6.0,
        "fps": 24,
        "ratio": " 9 x 16 ",
        "motion": {
            "presets": [" cinematic ", "", "punchy"],
            "camera": {
                "tilt": " slow up ",
                "strength": 1.0,
            },
            "ignored": "   ",
        },
        "init_image_hash": " ABC123 ",
        "reference_asset_ids": reference_asset_ids,
    }


def test_canonical_generation_inputs_hash_identically_when_equivalent() -> None:
    reference_one = uuid.uuid4()
    reference_two = uuid.uuid4()
    first_request = _base_generation_request(reference_asset_ids=[reference_two, reference_one])
    second_request = {
        **_base_generation_request(reference_asset_ids=[reference_one, reference_two]),
        "asset_class": "clip",
        "provider": "runway",
        "model": "gen4.5",
        "prompt": "Hero launch shot",
        "negative_prompt": "no text overlays",
        "duration_seconds": 6,
        "ratio": "9:16",
        "motion": {
            "camera": {
                "strength": 1,
                "tilt": "slow up",
            },
            "presets": ["cinematic", "punchy"],
        },
        "init_image_hash": "abc123",
    }

    first_key = build_asset_key(**first_request)
    second_key = build_asset_key(**second_request)

    expected_payload = {
        "asset_class": "clip",
        "provider": "runway",
        "model": "gen4.5",
        "prompt": "Hero launch shot",
        "negative_prompt": "no text overlays",
        "seed": 7,
        "duration_seconds": 6,
        "fps": 24,
        "ratio": "9:16",
        "motion": {
            "camera": {
                "strength": 1,
                "tilt": "slow up",
            },
            "presets": ["cinematic", "punchy"],
        },
        "init_image_hash": "abc123",
        "reference_asset_ids": sorted([str(reference_one), str(reference_two)]),
    }

    assert first_key.canonical_params == expected_payload
    assert second_key.canonical_params == expected_payload
    assert (
        first_key.asset_key == second_key.asset_key == serialise_canonical_payload(expected_payload)
    )
    assert first_key.asset_key_hash == second_key.asset_key_hash
    assert (
        first_key.asset_key_hash == hashlib.sha256(first_key.asset_key.encode("utf-8")).hexdigest()
    )


def test_blank_optional_fields_are_omitted_from_the_canonical_payload() -> None:
    canonical = canonicalise_runway_gen45_generation(
        asset_class="clip",
        provider="runway",
        model="gen4.5",
        prompt="Hero launch shot",
        negative_prompt="   ",
        ratio=" 9 : 16 ",
        motion={"camera": {"strength": 0.5}, "empty": {}},
        init_image_hash="   ",
        reference_asset_ids=[],
    )

    assert canonical == {
        "asset_class": "clip",
        "provider": "runway",
        "model": "gen4.5",
        "prompt": "Hero launch shot",
        "ratio": "9:16",
        "motion": {"camera": {"strength": 0.5}},
    }


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("prompt", "Different shot"),
        ("duration_seconds", 8),
        ("motion", {"camera": {"strength": 0.8, "tilt": "slow up"}, "presets": ["cinematic"]}),
    ],
)
def test_non_equivalent_payload_differences_change_the_asset_key_hash(
    field_name: str,
    replacement: Any,
) -> None:
    request = _base_generation_request(reference_asset_ids=[uuid.uuid4()])
    mutated_request = dict(request)
    mutated_request[field_name] = replacement

    baseline_key = build_asset_key(**request)
    changed_key = build_asset_key(**mutated_request)

    assert changed_key.asset_key_hash != baseline_key.asset_key_hash
    assert changed_key.asset_key != baseline_key.asset_key


def test_validate_phase1_provider_model_rejects_non_runway_gen45_requests() -> None:
    with pytest.raises(Phase1ProviderLockError):
        validate_phase1_provider_model(provider="pika", model="gen4.5")
