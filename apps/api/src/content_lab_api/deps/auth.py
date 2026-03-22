"""Authentication, org-scoped request context, RBAC, and audit dependencies."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, cast

import structlog
from fastapi import Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from content_lab_api.deps.database import get_db
from content_lab_api.models import ApiKey, AuditLog
from content_lab_auth import (
    APIKeyRecord,
    Identity,
    Role,
    extract_key_prefix,
    issue_api_key,
    verify_api_key,
)
from content_lab_shared.settings import Settings

logger = structlog.get_logger()

API_KEY_HEADER = "X-API-Key"
_AUTH_SCHEME = "Bearer"
_VALID_ROLES: set[Role] = {"owner", "admin", "operator", "reviewer", "readonly"}


class AuthError(Exception):
    """Raised when request credentials cannot be resolved into an identity."""

    def __init__(self, detail: str, *, status_code: int = status.HTTP_401_UNAUTHORIZED) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class APIKeyLookup(Protocol):
    """Interface for loading hashed API-key records without leaking secrets."""

    def get_by_prefix(self, prefix: str) -> APIKeyRecord | None:
        ...

    def create(
        self,
        *,
        org_id: uuid.UUID,
        role: Role,
        name: str | None,
        expires_at: datetime | None,
    ) -> tuple[str, APIKeyRecord]:
        ...


class AuditSink(Protocol):
    """Interface for recording security-sensitive audit events."""

    def write(
        self,
        *,
        org_id: uuid.UUID,
        action: str,
        resource_type: str,
        actor_type: str | None,
        actor_id: str | None,
        resource_id: str | None,
        payload: dict[str, Any],
    ) -> None:
        ...


class RequestCredentialResolver(Protocol):
    """Future-proof credential resolver abstraction (API key today; JWT/OIDC later)."""

    def authenticate(self, request: Request) -> Identity:
        ...


class CreateAPIKeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    role: Role = "readonly"
    expires_at: datetime | None = None


class CreatedAPIKeyResponse(BaseModel):
    api_key: str
    api_key_id: uuid.UUID
    key_prefix: str
    org_id: uuid.UUID
    role: Role
    name: str | None = None
    expires_at: datetime | None = None


class IdentityResponse(BaseModel):
    org_id: uuid.UUID
    role: Role
    auth_scheme: str
    subject: str
    api_key_id: uuid.UUID | None = None


class RoleGuardResult(BaseModel):
    message: str
    org_id: uuid.UUID
    role: Role


class MutationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str
    note: str | None = None


class SQLAlchemyAPIKeyStore:
    def __init__(self, db: Session, *, salt: str) -> None:
        self._db = db
        self._salt = salt

    def get_by_prefix(self, prefix: str) -> APIKeyRecord | None:
        row = self._db.query(ApiKey).filter(ApiKey.key_prefix == prefix).one_or_none()
        if row is None:
            return None
        metadata = _parse_name_metadata(row.name)
        return APIKeyRecord(
            api_key_id=row.id,
            org_id=row.org_id,
            role=cast(Role, metadata["role"]),
            key_hash=row.key_hash,
            key_prefix=row.key_prefix,
            name=cast(str | None, metadata["name"]),
            expires_at=cast(datetime | None, metadata["expires_at"]),
            revoked_at=row.revoked_at,
        )

    def create(
        self,
        *,
        org_id: uuid.UUID,
        role: Role,
        name: str | None,
        expires_at: datetime | None,
    ) -> tuple[str, APIKeyRecord]:
        issued = issue_api_key(
            org_id=org_id,
            role=role,
            salt=self._salt,
            name=name,
            expires_at=expires_at,
        )
        row = ApiKey(
            org_id=org_id,
            name=_compose_name(name=name, role=role, expires_at=expires_at),
            key_prefix=issued.record.key_prefix,
            key_hash=issued.record.key_hash,
            revoked_at=issued.record.revoked_at,
        )
        self._db.add(row)
        self._db.flush()
        record = issued.record.model_copy(update={"api_key_id": row.id})
        return issued.plaintext_key, record


class SQLAlchemyAuditSink:
    def __init__(self, db: Session) -> None:
        self._db = db

    def write(
        self,
        *,
        org_id: uuid.UUID,
        action: str,
        resource_type: str,
        actor_type: str | None,
        actor_id: str | None,
        resource_id: str | None,
        payload: dict[str, Any],
    ) -> None:
        self._db.add(
            AuditLog(
                org_id=org_id,
                action=action,
                resource_type=resource_type,
                actor_type=actor_type,
                actor_id=actor_id,
                resource_id=resource_id,
                payload=payload,
            )
        )
        self._db.flush()


class APIKeyAuthResolver:
    def __init__(self, store: APIKeyLookup, *, api_key_header: str | None, salt: str) -> None:
        self._store = store
        self._api_key_header = api_key_header
        self._salt = salt

    def authenticate(self, request: Request) -> Identity:
        plaintext_key = _resolve_plaintext_api_key(request, api_key_header=self._api_key_header)
        if plaintext_key is None:
            raise AuthError("Missing API key")

        try:
            prefix = extract_key_prefix(plaintext_key)
        except ValueError as exc:
            raise AuthError("Invalid API key format") from exc

        record = self._store.get_by_prefix(prefix)
        if record is None:
            raise AuthError("Invalid API key")
        if record.revoked:
            raise AuthError("API key has been revoked")
        if record.is_expired():
            raise AuthError("API key has expired")
        if not verify_api_key(plaintext_key, salt=self._salt, expected_hash=record.key_hash):
            raise AuthError("Invalid API key")

        identity = Identity(
            org_id=record.org_id,
            role=record.role,
            subject=f"api_key:{record.api_key_id or record.key_prefix}",
            api_key_id=record.api_key_id,
        )
        request.state.identity = identity
        request.state.actor = identity.subject
        structlog.contextvars.bind_contextvars(actor=identity.subject, org_id=str(identity.org_id))
        return identity


@dataclass(frozen=True)
class AuditMutation:
    write: Callable[..., None]



def _compose_name(*, name: str | None, role: Role, expires_at: datetime | None) -> str:
    label = (name or "generated").strip() or "generated"
    parts = [f"role={role}"]
    if expires_at is not None:
        normalized = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)  # noqa: UP017
        parts.append(f"exp={normalized.isoformat()}")
    metadata = "|".join(parts)
    return f"{label} [{metadata}]"



def _parse_name_metadata(raw_name: str | None) -> dict[str, Any]:
    metadata: dict[str, Any] = {"name": raw_name, "role": "readonly", "expires_at": None}
    if raw_name is None:
        return metadata
    marker = raw_name.rfind("[")
    if marker == -1 or not raw_name.endswith("]"):
        return metadata
    metadata["name"] = raw_name[:marker].rstrip() or None
    for item in raw_name[marker + 1 : -1].split("|"):
        key, _, value = item.partition("=")
        if key == "role" and value in _VALID_ROLES:
            metadata["role"] = value
        elif key == "exp" and value:
            metadata["expires_at"] = datetime.fromisoformat(value)
    return metadata



def _resolve_plaintext_api_key(request: Request, *, api_key_header: str | None) -> str | None:
    if api_key_header:
        return api_key_header.strip() or None
    authorization = request.headers.get("Authorization")
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == _AUTH_SCHEME.lower() and token.strip():
            return token.strip()
    return None



def get_settings() -> Settings:
    return Settings()



def get_api_key_store(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> APIKeyLookup:
    return SQLAlchemyAPIKeyStore(db, salt=settings.api_key_salt.get_secret_value())



def get_audit_sink(db: Session = Depends(get_db)) -> AuditSink:
    return SQLAlchemyAuditSink(db)



def get_request_auth_resolver(
    store: APIKeyLookup = Depends(get_api_key_store),
    settings: Settings = Depends(get_settings),
    api_key_header: str | None = Header(default=None, alias=API_KEY_HEADER),
) -> RequestCredentialResolver:
    return APIKeyAuthResolver(
        store,
        api_key_header=api_key_header,
        salt=settings.api_key_salt.get_secret_value(),
    )



def get_request_identity(
    request: Request,
    resolver: RequestCredentialResolver = Depends(get_request_auth_resolver),
) -> Identity:
    existing = getattr(request.state, "identity", None)
    if isinstance(existing, Identity):
        return existing
    try:
        return resolver.authenticate(request)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc



def require_role(required_role: Role) -> Callable[[Identity], Identity]:
    def dependency(identity: Identity = Depends(get_request_identity)) -> Identity:
        if not identity.has_role(required_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {required_role} role",
            )
        return identity

    return dependency



def get_audit_mutation(
    identity: Identity = Depends(get_request_identity),
    sink: AuditSink = Depends(get_audit_sink),
) -> AuditMutation:
    def write(
        *,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        sink.write(
            org_id=identity.org_id,
            action=action,
            resource_type=resource_type,
            actor_type=identity.auth_scheme,
            actor_id=identity.subject,
            resource_id=resource_id,
            payload=payload or {},
        )
        logger.info(
            "audit_mutation_recorded",
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            org_id=str(identity.org_id),
            actor=identity.subject,
        )

    return AuditMutation(write=write)
