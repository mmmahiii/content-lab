"""Dependency helpers exposed for API routes."""

from content_lab_api.deps.auth import (
    API_KEY_HEADER,
    AuditMutation,
    CreateAPIKeyRequest,
    CreatedAPIKeyResponse,
    IdentityResponse,
    MutationPayload,
    RoleGuardResult,
    get_audit_mutation,
    get_request_identity,
    require_role,
)
from content_lab_api.deps.database import get_db

__all__ = [
    "API_KEY_HEADER",
    "AuditMutation",
    "CreateAPIKeyRequest",
    "CreatedAPIKeyResponse",
    "IdentityResponse",
    "MutationPayload",
    "RoleGuardResult",
    "get_audit_mutation",
    "get_db",
    "get_request_identity",
    "require_role",
]
