# Runtime database inspection (canonical)

Use the repo-supported **read-only** helper when debugging runs, tasks, outbox
dispatch, provider jobs, assets, and package lineage. It uses the same
SQLAlchemy models as the API (`apps/api/src/content_lab_api/models/`), so
column names stay aligned with Alembic.

## Command

From the repo root (or any cwd), run via the API virtualenv so `DATABASE_URL`
comes from `.env` / `content_lab_shared.settings`:

```bash
cd apps/api && poetry run python ../../scripts/db_runtime_inspect.py --org-id <ORG_UUID>
```

Scope to a single run (org is inferred from the run row):

```bash
cd apps/api && poetry run python ../../scripts/db_runtime_inspect.py --run-id <RUN_UUID>
```

Optional limits (defaults are safe for interactive use):

- `--limit-runs` (default `5`, org-only mode)
- `--limit-tasks`, `--limit-outbox`, `--limit-provider-jobs`, `--limit-assets`, `--limit-run-assets`

## Expected output (JSON)

Top-level keys:

| Key | Meaning |
|-----|---------|
| `meta` | `org_id`, optional `run_id_filter`, `schema_tables_phase1` (table names this tool targets), and a short note about packages. |
| `runs` | Recent or selected runs: `id`, `org_id`, `workflow_key`, `flow_trigger`, `status`, keys, timestamps, and **`package_hints`** (`output_payload_keys`, `package_keys`). |
| `tasks` | Tasks for the selected run id set: `task_type`, `status`, `run_id`, `payload`, `result`, etc. |
| `outbox_events` | Outbox rows whose `aggregate_id` matches one of the selected run ids (`event_type`, `delivery_status`, `payload`, …). |
| `provider_jobs` | Latest provider jobs for the org (`provider`, `external_ref`, `task_id`, `status`, `metadata`, …). |
| `assets` | Recent assets for the org (subset of columns; no embedding vector). |
| `run_assets` | Links from selected runs to assets (`asset_role`). |
| `reels` | Reels referenced by selected runs (`reel_id` in `input_params` or `run_metadata.target`). |

**Packages:** there is no `packages` table. Packaged outputs are reflected in
`runs.output_payload` (see `package_hints`) and in storage; `run_assets`
connects a run to concrete `assets` rows when present.

## Operator safety

- The script performs **SELECT**-style ORM reads only (no commits, no DML).
- Run it against non-production only unless your policy allows read-only
  production access.

## Related smoke checks

- End-to-end MVP smoke still asserts Postgres using the same table names
  (`runs`, `tasks`, `reels`, `outbox_events`) in `scripts/e2e_mvp_smoke.py`.
- Asset resolve regression uses `provider_jobs`, `tasks`, and `assets` in
  `scripts/e2e_no_regen.py`.

For those paths, prefer this inspector when exploring state interactively
instead of ad-hoc SQL copied from older docs.
