"""Emit one JSON line on stdout: DB alembic versions vs known script revisions.

Exit 0: DB versions are compatible with this codebase (empty or all known).
Exit 2: DB references at least one revision ID not present in migration scripts.
Exit 1: Configuration or connectivity error.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text


def _api_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    api_root = _api_root()
    cfg = Config(str(api_root / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    known = {r.revision for r in script.iterate_revisions(script.get_heads(), "base")}
    heads = list(script.get_heads())

    url = os.environ.get("DATABASE_URL")
    if not url:
        print(json.dumps({"error": "DATABASE_URL missing", "heads": heads}))
        return 1

    db_versions: list[str] = []
    try:
        eng = create_engine(url)
        with eng.connect() as conn:
            exists = conn.execute(
                text(
                    "SELECT EXISTS ("
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'alembic_version'"
                    ")"
                )
            ).scalar()
            if exists:
                rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
                db_versions = [str(r[0]) for r in rows]
    except OSError as exc:
        print(json.dumps({"error": f"db_connect_os: {exc}", "heads": heads}))
        return 1
    except Exception as exc:  # noqa: BLE001 — preflight must report any DB failure
        print(json.dumps({"error": f"db_connect: {exc}", "heads": heads}))
        return 1

    unknown = [v for v in db_versions if v not in known]
    stale = len(unknown) > 0
    payload = {
        "db_versions": db_versions,
        "unknown_script_versions": unknown,
        "heads": heads,
        "known_revision_count": len(known),
        "stale": stale,
    }
    print(json.dumps(payload))
    return 2 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
