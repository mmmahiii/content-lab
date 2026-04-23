"""Light tests for runtime DB snapshot helpers (no database required)."""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

from content_lab_api.diagnostics.runtime_db_snapshot import (
    SCHEMA_TABLES_PHASE1,
    _package_hints,
    _reel_ids_from_runs,
)


def test_phase1_table_names_include_operational_core() -> None:
    assert "runs" in SCHEMA_TABLES_PHASE1
    assert "tasks" in SCHEMA_TABLES_PHASE1
    assert "outbox_events" in SCHEMA_TABLES_PHASE1
    assert "provider_jobs" in SCHEMA_TABLES_PHASE1
    assert "assets" in SCHEMA_TABLES_PHASE1
    assert "run_assets" in SCHEMA_TABLES_PHASE1


def test_reel_ids_from_runs_collects_input_and_metadata_targets() -> None:
    first = uuid.uuid4()
    second = uuid.uuid4()
    run = SimpleNamespace(
        input_params={"reel_id": str(first)},
        run_metadata={"target": {"reel_id": str(second)}},
    )
    assert _reel_ids_from_runs([run]) == [first, second]

    dup = SimpleNamespace(
        input_params={"reel_id": str(first)},
        run_metadata={"target": {"reel_id": str(first)}},
    )
    assert _reel_ids_from_runs([dup]) == [first]


def test_package_hints_reflects_output_payload_shape() -> None:
    empty = _package_hints(None)
    assert empty["output_payload_keys"] == []
    assert empty["package_keys"] is None

    nested = _package_hints({"package": {"root": "s3://x"}, "status": "ok"})
    assert "package" in nested["output_payload_keys"]
    assert nested["package_keys"] == ["root"]


def test_db_runtime_inspect_script_help_smoke() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    script = repo_root / "scripts" / "db_runtime_inspect.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "org-id" in proc.stdout.lower()
