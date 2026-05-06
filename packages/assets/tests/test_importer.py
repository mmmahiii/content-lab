from __future__ import annotations

import pytest

from content_lab_assets.importer import (
    ApprovedImportValidationError,
    assert_safe_http_url_for_fetch,
    usage_metadata_sufficient,
)


def test_assert_safe_blocks_localhost() -> None:
    with pytest.raises(ApprovedImportValidationError):
        assert_safe_http_url_for_fetch("http://127.0.0.1:8080/a.png")


def test_assert_safe_blocks_private_literal() -> None:
    with pytest.raises(ApprovedImportValidationError):
        assert_safe_http_url_for_fetch("https://10.0.0.1/asset.png")


def test_usage_metadata_complete() -> None:
    ok, warnings = usage_metadata_sufficient(
        usage_rights_confirmed=True,
        licence_type="cc-by",
        licence_notes=None,
        usage_allowed=True,
        attribution_required=False,
        attribution_text=None,
    )
    assert ok is True
    assert warnings == []


def test_usage_metadata_incomplete_flags() -> None:
    ok, warnings = usage_metadata_sufficient(
        usage_rights_confirmed=True,
        licence_type=None,
        licence_notes=None,
        usage_allowed=None,
        attribution_required=None,
        attribution_text=None,
    )
    assert ok is False
    assert "missing_usage_and_licence_detail" in warnings
