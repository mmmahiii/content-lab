"""Asset record model and registry protocol for cataloguing media assets."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import Field

from content_lab_core.models import DomainModel
from content_lab_core.types import AssetKind


class AssetRecord(DomainModel):
    """Metadata record for a catalogued asset."""

    name: str
    kind: AssetKind
    content_hash: str
    storage_uri: str
    size_bytes: int = 0
    tags: list[str] = Field(default_factory=list)


@runtime_checkable
class AssetRegistry(Protocol):
    """Interface for asset catalogue operations."""

    def register(self, record: AssetRecord) -> AssetRecord: ...

    def lookup_by_hash(self, content_hash: str) -> AssetRecord | None: ...
