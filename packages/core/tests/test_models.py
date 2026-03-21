from __future__ import annotations

from datetime import timezone

from content_lab_core.models import DomainModel


class TestDomainModel:
    def test_defaults(self) -> None:
        m = DomainModel()
        assert len(m.id) == 32
        assert m.created_at.tzinfo == timezone.utc
        assert m.updated_at.tzinfo == timezone.utc

    def test_unique_ids(self) -> None:
        a = DomainModel()
        b = DomainModel()
        assert a.id != b.id

    def test_serialisation_roundtrip(self) -> None:
        m = DomainModel()
        data = m.model_dump()
        restored = DomainModel.model_validate(data)
        assert restored.id == m.id
