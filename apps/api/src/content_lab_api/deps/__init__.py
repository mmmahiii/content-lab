"""Dependency injection providers."""

from content_lab_api.deps.database import get_db
from content_lab_api.deps.llm import get_llm_client

__all__ = ["get_db", "get_llm_client"]
