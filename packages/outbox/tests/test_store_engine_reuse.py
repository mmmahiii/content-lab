"""Stores built per poll must reuse one engine; a new pool per call leaked connections."""

from __future__ import annotations

from content_lab_outbox.store import SQLOutboxStore
from content_lab_shared.settings import Settings


def test_stores_share_one_engine_per_database_url() -> None:
    settings = Settings(database_url="sqlite:///leakcheck.db")
    first = SQLOutboxStore(settings=settings)
    second = SQLOutboxStore(settings=settings)
    assert first._session_factory.kw["bind"] is second._session_factory.kw["bind"]


def test_different_urls_get_different_engines() -> None:
    a = SQLOutboxStore(settings=Settings(database_url="sqlite:///a.db"))
    b = SQLOutboxStore(settings=Settings(database_url="sqlite:///b.db"))
    assert a._session_factory.kw["bind"] is not b._session_factory.kw["bind"]
