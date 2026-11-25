"""LLM client dependency. Returns ``None`` when no provider/credentials are configured."""

from __future__ import annotations

from functools import lru_cache

from content_lab_intelligence import LLMClient, build_llm_client


@lru_cache(maxsize=1)
def _cached_client() -> LLMClient | None:
    return build_llm_client()


def get_llm_client() -> LLMClient | None:
    """FastAPI dependency; override it in tests with ``FakeLLMClient``."""

    return _cached_client()


__all__ = ["get_llm_client"]
