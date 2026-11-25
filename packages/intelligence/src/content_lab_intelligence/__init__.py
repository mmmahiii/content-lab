"""AI/ML integration layer for content intelligence: a small structured-output LLM client."""

from content_lab_intelligence.client import (
    REFUSAL_FALLBACK_BETA,
    AnthropicLLMClient,
    LLMClient,
    StructuredLLMClient,
    build_llm_client,
    completion_from_response,
    require_llm_client,
)
from content_lab_intelligence.config import (
    DEFAULT_MODEL,
    PRICING_PER_MTOK,
    LLMSettings,
    ModelPricing,
    estimate_cost_usd,
)
from content_lab_intelligence.errors import (
    LLMError,
    LLMNotConfiguredError,
    LLMOutputError,
    LLMRefusalError,
    LLMRequestError,
    LLMUnavailableError,
)
from content_lab_intelligence.fake import FakeCall, FakeLLMClient
from content_lab_intelligence.schema import strict_json_schema
from content_lab_intelligence.types import (
    LLMUsage,
    RawCompletion,
    StructuredRequest,
    StructuredResult,
)

__all__ = [
    "DEFAULT_MODEL",
    "PRICING_PER_MTOK",
    "REFUSAL_FALLBACK_BETA",
    "AnthropicLLMClient",
    "FakeCall",
    "FakeLLMClient",
    "LLMClient",
    "LLMError",
    "LLMNotConfiguredError",
    "LLMOutputError",
    "LLMRefusalError",
    "LLMRequestError",
    "LLMSettings",
    "LLMUnavailableError",
    "LLMUsage",
    "ModelPricing",
    "RawCompletion",
    "StructuredLLMClient",
    "StructuredRequest",
    "StructuredResult",
    "build_llm_client",
    "completion_from_response",
    "estimate_cost_usd",
    "require_llm_client",
    "strict_json_schema",
]
