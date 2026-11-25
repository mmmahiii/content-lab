from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Literal

import anthropic
import pytest
from pydantic import BaseModel, Field, ValidationInfo, field_validator

from content_lab_intelligence import (
    REFUSAL_FALLBACK_BETA,
    AnthropicLLMClient,
    FakeLLMClient,
    LLMNotConfiguredError,
    LLMOutputError,
    LLMRefusalError,
    LLMSettings,
    LLMUnavailableError,
    LLMUsage,
    RawCompletion,
    StructuredRequest,
    build_llm_client,
    estimate_cost_usd,
    strict_json_schema,
)


class Tagline(BaseModel):
    text: str = Field(min_length=3, max_length=40)
    tone: Literal["calm", "loud"]

    @field_validator("text")
    @classmethod
    def _no_blocked(cls, value: str, info: ValidationInfo) -> str:
        blocked = (info.context or {}).get("blocked", ())
        for phrase in blocked:
            if phrase in value.lower():
                raise ValueError(f"contains blocked phrase {phrase!r}")
        return value


def _request(**overrides: Any) -> StructuredRequest[Tagline]:
    params: dict[str, Any] = {
        "purpose": "tagline",
        "system": "You write taglines.",
        "prompt": "Write one tagline.",
        "output_model": Tagline,
    }
    params.update(overrides)
    return StructuredRequest(**params)


def test_fake_client_returns_validated_output() -> None:
    client = FakeLLMClient([{"text": "Slow mornings win", "tone": "calm"}])
    result = client.generate_structured(_request())
    assert result.output == Tagline(text="Slow mornings win", tone="calm")
    assert result.attempts == 1
    assert result.usage.input_tokens == 100


def test_malformed_json_is_repaired_with_validation_errors() -> None:
    client = FakeLLMClient(["{not json", {"text": "Fixed it", "tone": "loud"}])
    result = client.generate_structured(_request())
    assert result.attempts == 2
    assert result.output.text == "Fixed it"
    repair = client.calls[1].messages
    assert [m["role"] for m in repair] == ["user", "assistant", "user"]
    assert repair[1]["content"] == "{not json"
    assert "failed validation" in repair[2]["content"]
    # Usage is summed across attempts.
    assert result.usage.input_tokens == 200


def test_persistent_bad_output_raises_output_error() -> None:
    client = FakeLLMClient([{"text": "x", "tone": "calm"}, {"text": "ok text", "tone": "meh"}])
    with pytest.raises(LLMOutputError) as caught:
        client.generate_structured(_request())
    assert len(caught.value.validation_errors) == 2
    assert "text" in caught.value.validation_errors[0]
    assert "tone" in caught.value.validation_errors[1]
    assert caught.value.usage is not None


def test_validation_context_reaches_validators() -> None:
    client = FakeLLMClient(
        [{"text": "Buy now cheap", "tone": "loud"}, {"text": "Worth a look", "tone": "loud"}]
    )
    result = client.generate_structured(_request(validation_context={"blocked": ["buy now"]}))
    assert result.output.text == "Worth a look"
    assert "blocked phrase" in client.calls[1].messages[2]["content"]


def test_refusal_raises_without_retry() -> None:
    refusal = RawCompletion(
        text="",
        stop_reason="refusal",
        usage=LLMUsage(model="fake-model"),
        refusal_category="general_harms",
        refusal_explanation="declined",
    )
    client = FakeLLMClient([refusal])
    with pytest.raises(LLMRefusalError) as caught:
        client.generate_structured(_request())
    assert caught.value.category == "general_harms"
    assert client.call_count == 1


def test_max_tokens_stop_triggers_a_repair_attempt() -> None:
    cut_off = RawCompletion(text='{"text": "Half', stop_reason="max_tokens", usage=LLMUsage("m"))
    client = FakeLLMClient([cut_off, {"text": "Whole line", "tone": "calm"}])
    result = client.generate_structured(_request())
    assert result.attempts == 2
    assert "max_tokens" in client.calls[1].messages[2]["content"]


def test_exceptions_from_the_provider_propagate() -> None:
    client = FakeLLMClient([LLMUnavailableError("down")])
    with pytest.raises(LLMUnavailableError):
        client.generate_structured(_request())


class _StubMessages:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.params: dict[str, Any] = {}

    def create(self, **params: Any) -> Any:
        self.params = params
        if self.error is not None:
            raise self.error
        return self.response


def _stub_sdk(messages: _StubMessages) -> Any:
    return SimpleNamespace(beta=SimpleNamespace(messages=messages))


def _response(text: str, **usage: Any) -> Any:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason="end_turn",
        stop_details=None,
        model="claude-sonnet-5-5",
        usage=SimpleNamespace(
            input_tokens=usage.get("input_tokens", 1_000),
            output_tokens=usage.get("output_tokens", 500),
            cache_read_input_tokens=usage.get("cache_read_input_tokens", 0),
            cache_creation_input_tokens=0,
            iterations=usage.get("iterations"),
        ),
    )


def test_anthropic_client_sends_structured_output_request() -> None:
    messages = _StubMessages(_response('{"text": "Real call", "tone": "calm"}'))
    client = AnthropicLLMClient(LLMSettings(effort="low"), sdk_client=_stub_sdk(messages))
    result = client.generate_structured(_request())

    params = messages.params
    assert params["model"] == "claude-sonnet-5-5"
    assert params["system"] == "You write taglines."
    assert params["messages"] == [{"role": "user", "content": "Write one tagline."}]
    assert params["cache_control"] == {"type": "ephemeral"}
    assert params["betas"] == [REFUSAL_FALLBACK_BETA]
    assert params["fallbacks"] == "default"
    assert "temperature" not in params
    output_config = params["output_config"]
    assert output_config["effort"] == "low"
    schema = output_config["format"]["schema"]
    assert output_config["format"]["type"] == "json_schema"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["text", "tone"]

    assert result.output.text == "Real call"
    # 1000 * $2 + 500 * $10 per million tokens.
    assert result.usage.cost_usd == pytest.approx(0.007)


def test_anthropic_client_can_disable_refusal_fallbacks() -> None:
    messages = _StubMessages(_response('{"text": "No fallback", "tone": "calm"}'))
    client = AnthropicLLMClient(
        LLMSettings(refusal_fallbacks=False), sdk_client=_stub_sdk(messages)
    )
    client.generate_structured(_request())
    assert "betas" not in messages.params
    assert "fallbacks" not in messages.params


def test_anthropic_client_reports_fallback_served_responses() -> None:
    iterations = [SimpleNamespace(type="message"), SimpleNamespace(type="fallback_message")]
    messages = _StubMessages(
        _response('{"text": "Rescued", "tone": "calm"}', iterations=iterations)
    )
    client = AnthropicLLMClient(LLMSettings(), sdk_client=_stub_sdk(messages))
    assert client.generate_structured(_request()).usage.served_by_fallback is True


def test_anthropic_connection_errors_become_unavailable() -> None:
    error = anthropic.APIConnectionError(request=None)  # type: ignore[arg-type]
    client = AnthropicLLMClient(LLMSettings(), sdk_client=_stub_sdk(_StubMessages(error=error)))
    with pytest.raises(LLMUnavailableError):
        client.generate_structured(_request())


def test_anthropic_client_errors_become_not_configured() -> None:
    error = anthropic.AnthropicError("Could not resolve authentication method")
    client = AnthropicLLMClient(LLMSettings(), sdk_client=_stub_sdk(_StubMessages(error=error)))
    with pytest.raises(LLMNotConfiguredError):
        client.generate_structured(_request())


class _Inner(BaseModel):
    label: str = Field(max_length=10)
    kind: Literal["a"] = "a"


class _Outer(BaseModel):
    items: list[_Inner] = Field(min_length=1, max_length=3)
    note: str | None = None


def test_strict_json_schema_moves_constraints_into_descriptions() -> None:
    schema = strict_json_schema(_Outer)
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["items", "note"]
    assert "maxItems" not in schema["properties"]["items"]
    assert "at most 3 items" in schema["properties"]["items"]["description"]
    inner = schema["$defs"]["_Inner"]
    assert inner["additionalProperties"] is False
    assert inner["properties"]["kind"]["enum"] == ["a"]
    assert "at most 10 characters" in inner["properties"]["label"]["description"]
    assert "title" not in inner


def test_settings_from_env_and_enablement() -> None:
    settings = LLMSettings.from_env({})
    assert settings.model == "claude-sonnet-5-5"
    assert settings.effort == "medium"
    assert settings.is_enabled({}) is False
    assert settings.is_enabled({"ANTHROPIC_API_KEY": "sk-test"}) is True
    custom = LLMSettings.from_env({"CONTENT_LAB_LLM_MODEL": "claude-opus-5-5"})
    assert custom.model == "claude-opus-5-5"
    off = LLMSettings.from_env({"CONTENT_LAB_LLM_PROVIDER": "none", "ANTHROPIC_API_KEY": "k"})
    assert off.is_enabled({"ANTHROPIC_API_KEY": "k"}) is False
    with pytest.raises(ValueError):
        LLMSettings.from_env({"CONTENT_LAB_LLM_EFFORT": "extreme"})


def test_build_llm_client_needs_credentials() -> None:
    assert build_llm_client(env={}) is None
    client = build_llm_client(env={"ANTHROPIC_API_KEY": "sk-test"})
    assert isinstance(client, AnthropicLLMClient)


def test_cost_estimate_unknown_model_is_none() -> None:
    assert estimate_cost_usd("mystery", input_tokens=1, output_tokens=1) is None
    assert estimate_cost_usd(
        "claude-sonnet-5-5", input_tokens=0, output_tokens=0, cache_read_input_tokens=1_000_000
    ) == pytest.approx(0.10)
