"""Organization ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_lab_api.db import Base

if TYPE_CHECKING:
    from content_lab_api.models.api_key import ApiKey
    from content_lab_api.models.audit_log import AuditLog
    from content_lab_api.models.experiment import Experiment
    from content_lab_api.models.org_membership import OrgMembership
    from content_lab_api.models.policy_state import PolicyState
    from content_lab_api.models.provider_job import ProviderJob
    from content_lab_api.models.storage_integrity_check import StorageIntegrityCheck
    from content_lab_api.models.task import Task


class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False
    )
    name: Mapped[str] = mapped_column(String(256))
    slug: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )

    memberships: Mapped[list[OrgMembership]] = relationship(
        back_populates="org", init=False, default_factory=list
    )
    api_keys: Mapped[list[ApiKey]] = relationship(
        back_populates="org", init=False, default_factory=list
    )
    policy_states: Mapped[list[PolicyState]] = relationship(
        "PolicyState", back_populates="org", init=False, default_factory=list
    )
    experiments: Mapped[list[Experiment]] = relationship(
        "Experiment", back_populates="org", init=False, default_factory=list
    )
    tasks: Mapped[list[Task]] = relationship(
        "Task", back_populates="org", init=False, default_factory=list
    )
    provider_jobs: Mapped[list[ProviderJob]] = relationship(
        "ProviderJob", back_populates="org", init=False, default_factory=list
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        "AuditLog", back_populates="org", init=False, default_factory=list
    )
    storage_integrity_checks: Mapped[list[StorageIntegrityCheck]] = relationship(
        "StorageIntegrityCheck", back_populates="org", init=False, default_factory=list
    )
