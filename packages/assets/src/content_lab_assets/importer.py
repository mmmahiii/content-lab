"""Validated helpers for approved external asset import (no blind scraping)."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

# Cap single-object download size (bytes).
MAX_APPROVED_IMPORT_BYTES = 50 * 1024 * 1024

_HOST_LOCAL_PATTERNS = (
    re.compile(r"^localhost$", re.I),
    re.compile(r"^127\.\d+\.\d+\.\d+$"),
    re.compile(r"^::1$"),
    re.compile(r"^0+$"),
)


class ApprovedImportValidationError(ValueError):
    """Raised when operator import prerequisites are not met."""


def assert_safe_http_url_for_fetch(url: str) -> None:
    """Reject non-HTTP(S) schemes and obvious loopback/private literal hosts.

    Full SSRF hardening (DNS rebinding) belongs in network policy; this blocks
    the common SSRF footguns for operator-initiated URL imports.
    """

    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ApprovedImportValidationError("Only http and https URLs may be imported")
    host = parsed.hostname
    if not host:
        raise ApprovedImportValidationError("URL must include a hostname")
    for pat in _HOST_LOCAL_PATTERNS:
        if pat.match(host):
            raise ApprovedImportValidationError("Localhost and loopback URLs are not allowed")
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return
    if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
        raise ApprovedImportValidationError(
            "Private or non-routable address literals are not allowed"
        )


def usage_metadata_sufficient(
    *,
    usage_rights_confirmed: bool,
    licence_type: str | None,
    licence_notes: str | None,
    usage_allowed: bool | None,
    attribution_required: bool | None,
    attribution_text: str | None,
) -> tuple[bool, list[str]]:
    """Return (is_complete, warning_codes) for licence / usage documentation."""

    warnings: list[str] = []
    if not usage_rights_confirmed:
        warnings.append("operator_usage_not_confirmed")
    if usage_allowed is None and not licence_type and not (licence_notes or "").strip():
        warnings.append("missing_usage_and_licence_detail")
    if attribution_required is True and not (attribution_text or "").strip():
        warnings.append("missing_attribution_text")
    complete = (
        usage_rights_confirmed
        and usage_allowed is not None
        and (bool(licence_type) or bool((licence_notes or "").strip()))
    )
    return complete, warnings


__all__ = [
    "MAX_APPROVED_IMPORT_BYTES",
    "ApprovedImportValidationError",
    "assert_safe_http_url_for_fetch",
    "usage_metadata_sufficient",
]
