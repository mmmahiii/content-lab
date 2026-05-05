from __future__ import annotations

from content_lab_creative.trace import build_creative_trace, sanitize_trace_payload


def test_build_creative_trace_preserves_debug_contract_without_secrets() -> None:
    creative_output = {
        "brief": {"title": "Desk reset", "description": "Clear the visual noise"},
        "script": {
            "provider_name": "rules_provider",
            "generator_path": "rules_plus_provider",
            "generation_metadata": {
                "strategy": "rules_plus_provider_v1",
                "api_key": "sk-secret",
            },
        },
        "script_generation": {
            "provider_name": "rules_provider",
            "generator_path": "rules_plus_provider",
            "generation_metadata": {"client_secret": "hidden"},
        },
        "script_lint": {"outcome": "pass", "passed": True, "findings": []},
        "scene_plan": {"schema_version": "phase_1", "scenes": [{"scene_id": "hook"}]},
        "compiled_prompt": {
            "prompt": "hook scene: close-up of a desk reset",
            "trace": {"prompt_hash": "sha256:abc", "provider_token": "tok"},
        },
        "posting_plan": {"platform": "instagram"},
    }

    trace = build_creative_trace(
        reel_id="reel-1",
        run_id="run-1",
        creative_output=creative_output,
    )
    payload = trace.model_dump(mode="json")

    assert payload["schema_version"] == "phase_1"
    assert payload["artifact_type"] == "creative_trace"
    assert payload["generator_selection"] == {
        "provider_name": "rules_provider",
        "generator_path": "rules_plus_provider",
        "metadata": {"client_secret": "[redacted]"},
    }
    assert payload["brief"]["title"] == "Desk reset"
    assert payload["script_lint"]["outcome"] == "pass"
    assert payload["scene_plan"]["scenes"][0]["scene_id"] == "hook"
    assert payload["compiled_prompt"]["trace"]["provider_token"] == "[redacted]"


def test_creative_trace_includes_visual_style_lock() -> None:
    creative_output = {
        "brief": {"title": "Ops reset", "content_pillar": "operations"},
        "script": {"provider_name": "rules", "generator_path": "deterministic"},
        "scene_plan": {
            "visual_style_lock": {"subject": "busy founder"},
            "scenes": [{"scene_id": "scene_1", "subject": "busy founder"}],
        },
        "compiled_prompt": {
            "prompt": "busy founder at modern desk",
            "trace": {
                "visual_style_lock": {"subject": "busy founder"},
                "enriched_scene_fields": [{"scene_id": "scene_1", "subject": "busy founder"}],
            },
        },
    }

    trace = build_creative_trace(
        reel_id="reel-1",
        run_id="run-1",
        creative_output=creative_output,
    ).model_dump(mode="json")

    assert trace["scene_plan"]["visual_style_lock"]["subject"] == "busy founder"
    assert trace["prompt_trace"]["visual_style_lock"]["subject"] == "busy founder"
    assert trace["prompt_trace"]["enriched_scene_fields"][0]["subject"] == "busy founder"


def test_sanitize_trace_payload_recursively_redacts_secret_like_keys() -> None:
    sanitized = sanitize_trace_payload(
        {
            "authorization": "Bearer abc",
            "nested": {
                "password": "pw",
                "safe": [{"api-key": "secret"}, {"caption": "keep me"}],
            },
        }
    )

    assert sanitized == {
        "authorization": "[redacted]",
        "nested": {
            "password": "[redacted]",
            "safe": [{"api-key": "[redacted]"}, {"caption": "keep me"}],
        },
    }
