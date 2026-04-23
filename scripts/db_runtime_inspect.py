#!/usr/bin/env python3
"""Canonical read-only Postgres inspection for operator debugging.

Uses the API SQLAlchemy models (same column names as migrations). No writes.

Examples:
  cd apps/api && poetry run python ../../scripts/db_runtime_inspect.py --org-id <UUID>
  cd apps/api && poetry run python ../../scripts/db_runtime_inspect.py --run-id <UUID>

See docs/RUNTIME_DB_INSPECT.md for output shape and troubleshooting.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path


def _bootstrap_path() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    api_src = repo_root / "apps" / "api" / "src"
    if api_src.is_dir():
        sys.path.insert(0, str(api_src))


def main() -> int:
    _bootstrap_path()

    parser = argparse.ArgumentParser(
        description="Read-only snapshot of runs, tasks, outbox, provider jobs, assets, run_assets.",
    )
    parser.add_argument("--org-id", default="", help="Org UUID to scope the snapshot.")
    parser.add_argument("--run-id", default="", help="Run UUID (infers org when org-id omitted).")
    parser.add_argument(
        "--limit-runs", type=int, default=5, help="Max runs when filtering by org only."
    )
    parser.add_argument("--limit-tasks", type=int, default=100)
    parser.add_argument("--limit-outbox", type=int, default=100)
    parser.add_argument("--limit-provider-jobs", type=int, default=50)
    parser.add_argument("--limit-assets", type=int, default=50)
    parser.add_argument("--limit-run-assets", type=int, default=100)
    args = parser.parse_args()

    org_id: uuid.UUID | None = None
    if args.org_id.strip():
        org_id = uuid.UUID(args.org_id.strip())
    run_id: uuid.UUID | None = None
    if args.run_id.strip():
        run_id = uuid.UUID(args.run_id.strip())

    if org_id is None and run_id is None:
        print("Error: provide --org-id and/or --run-id.", file=sys.stderr)
        return 2

    from content_lab_api.db import SessionLocal
    from content_lab_api.diagnostics.runtime_db_snapshot import build_runtime_db_snapshot

    db = SessionLocal()
    try:
        snapshot = build_runtime_db_snapshot(
            db,
            org_id=org_id,
            run_id=run_id,
            limit_runs=args.limit_runs,
            limit_tasks=args.limit_tasks,
            limit_outbox=args.limit_outbox,
            limit_provider_jobs=args.limit_provider_jobs,
            limit_assets=args.limit_assets,
            limit_run_assets=args.limit_run_assets,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
