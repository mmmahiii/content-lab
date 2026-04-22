"""Read the shared `packages/qa` bad-reel JSON fixtures (no dependency on the QA test package)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

# packages/creative/tests/fixtures/bad_reels/loader.py -> .../packages
_PACKAGES_ROOT = Path(__file__).resolve().parents[4]
QA_BAD_REEL_ROOT = _PACKAGES_ROOT / "qa" / "tests" / "fixtures" / "bad_reels"

if not QA_BAD_REEL_ROOT.is_dir():
    raise FileNotFoundError(
        f"Could not find shared QA bad_reel fixtures at {QA_BAD_REEL_ROOT} "
        "(expected packages/qa/tests/fixtures/bad_reels under the monorepo packages/ directory)."
    )

_FIXTURES_VERSION = "bad_reel_fixture_v1"


def load_bad_reel_case(case_id: str) -> dict[str, Any]:
    """Load a case JSON from the canonical QA fixture pack."""

    path = QA_BAD_REEL_ROOT / "cases" / f"{case_id}.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    if payload.get("case_id") != case_id:
        raise ValueError(f"case_id mismatch in {path}: expected {case_id!r}")
    if payload.get("schema_version") != _FIXTURES_VERSION:
        raise ValueError(
            f"Unexpected schema_version in {path}: {payload.get('schema_version')!r} "
            f"(expected {_FIXTURES_VERSION!r})"
        )
    return payload


def load_expected_outcomes() -> dict[str, Any]:
    """Copy of the QA expected-outcomes manifest (kept in sync by tests, not duplicated JSON)."""

    path = QA_BAD_REEL_ROOT / "expected_outcomes.json"
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
