"""Authentication, request-context, and RBAC demonstration routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from content_lab_api.deps import (
    AuditMutation,
    CreateAPIKeyRequest,
    CreatedAPIKeyResponse,
    IdentityResponse,
    MutationPayload,
    RoleGuardResult,
    get_audit_mutation,
    get_db,
    get_request_identity,
    require_role,
)
from content_lab_api.deps.auth import APIKeyLookup, get_api_key_store
from content_lab_auth import Identity

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=IdentityResponse)
def get_me(identity: Identity = Depends(get_request_identity)) -> IdentityResponse:
    return IdentityResponse(
        org_id=identity.org_id,
        role=identity.role,
        auth_scheme=identity.auth_scheme,
        subject=identity.subject,
        api_key_id=identity.api_key_id,
    )


@router.get("/guards/admin", response_model=RoleGuardResult)
def admin_guard(identity: Identity = Depends(require_role("admin"))) -> RoleGuardResult:
    return RoleGuardResult(message="admin access granted", org_id=identity.org_id, role=identity.role)


@router.get("/guards/operator", response_model=RoleGuardResult)
def operator_guard(identity: Identity = Depends(require_role("operator"))) -> RoleGuardResult:
    return RoleGuardResult(
        message="operator access granted", org_id=identity.org_id, role=identity.role
    )


@router.get("/guards/reviewer", response_model=RoleGuardResult)
def reviewer_guard(identity: Identity = Depends(require_role("reviewer"))) -> RoleGuardResult:
    return RoleGuardResult(
        message="reviewer access granted", org_id=identity.org_id, role=identity.role
    )


@router.get("/guards/readonly", response_model=RoleGuardResult)
def readonly_guard(identity: Identity = Depends(require_role("readonly"))) -> RoleGuardResult:
    return RoleGuardResult(
        message="readonly access granted", org_id=identity.org_id, role=identity.role
    )


@router.post("/api-keys", response_model=CreatedAPIKeyResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    body: CreateAPIKeyRequest,
    identity: Identity = Depends(require_role("admin")),
    store: APIKeyLookup = Depends(get_api_key_store),
    audit: AuditMutation = Depends(get_audit_mutation),
    db: Session = Depends(get_db),
) -> CreatedAPIKeyResponse:
    plaintext_key, record = store.create(
        org_id=identity.org_id,
        role=body.role,
        name=body.name,
        expires_at=body.expires_at,
    )
    audit.write(
        action="api_key.created",
        resource_type="api_key",
        resource_id=str(record.api_key_id or record.key_prefix),
        payload={
            "created_role": record.role,
            "key_prefix": record.key_prefix,
            "name": record.name,
            "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        },
    )
    db.commit()
    return CreatedAPIKeyResponse(
        api_key=plaintext_key,
        api_key_id=record.api_key_id or identity.org_id,
        key_prefix=record.key_prefix,
        org_id=record.org_id,
        role=record.role,
        name=record.name,
        expires_at=record.expires_at,
    )


@router.post("/mutations/echo", response_model=RoleGuardResult)
def echo_mutation(
    body: MutationPayload,
    identity: Identity = Depends(require_role("operator")),
    audit: AuditMutation = Depends(get_audit_mutation),
) -> RoleGuardResult:
    audit.write(
        action="demo.mutation",
        resource_type="demo_resource",
        resource_id=body.resource_id,
        payload={"note": body.note},
    )
    return RoleGuardResult(message="mutation accepted", org_id=identity.org_id, role=identity.role)
