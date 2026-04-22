"""Load deterministic bad-reel JSON fixtures and expected semantic outcomes."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

FIXTURES_VERSION = "bad_reel_fixture_v1"

_FIXTURES_ROOT = Path(__file__).resolve().parent
_CASES_DIR = _FIXTURES_ROOT / "cases"
_OUTCOMES_PATH = _FIXTURES_ROOT / "expected_outcomes.json"


@lru_cache(maxsize=8)
def load_expected_outcomes() -> dict[str, Any]:
    """Return the full expected-outcomes manifest (semantic / quality expectations)."""

    return cast(dict[str, Any], json.loads(_OUTCOMES_PATH.read_text(encoding="utf-8")))


def expected_outcome(case_id: str) -> dict[str, Any]:
    """Expected metadata for a case, including alignment verdict and required fail codes."""

    manifest = load_expected_outcomes()
    if case_id not in manifest:
        raise KeyError(f"Unknown bad-reel case_id: {case_id!r}")
    return cast(dict[str, Any], manifest[case_id])


def list_case_ids() -> tuple[str, ...]:
    """Case ids that have both a JSON bundle and an expected-outcomes entry."""

    from json import JSONDecodeError

    outcome_ids = set(load_expected_outcomes().keys())
    case_ids: list[str] = []
    for path in sorted(_CASES_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except JSONDecodeError:
            continue
        cid = payload.get("case_id")
        if isinstance(cid, str) and cid in outcome_ids:
            case_ids.append(cid)
    return tuple(case_ids)


def load_bad_reel_case(case_id: str) -> dict[str, Any]:
    """Load a full bad-reel bundle: brief, script, scene_plan, compiled_prompt, editing, asset_resolution."""

    path = _CASES_DIR / f"{case_id}.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    if payload.get("case_id") != case_id:
        raise ValueError(f"case_id mismatch in {path}: expected {case_id!r}")
    if payload.get("schema_version") != FIXTURES_VERSION:
        raise ValueError(
            f"Unexpected schema_version in {path}: {payload.get('schema_version')!r} "
            f"(loader expects {FIXTURES_VERSION!r})"
        )
    return payload
