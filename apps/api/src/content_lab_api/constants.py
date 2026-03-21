"""Application-wide constants (bootstrap IDs, etc.)."""

from __future__ import annotations

import uuid

# Stable default org for single-tenant / dev bootstrap; matches migration 0003 seed.
DEFAULT_ORG_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")

X_REQUEST_ID_HEADER = "X-Request-Id"
