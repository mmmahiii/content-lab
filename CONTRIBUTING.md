# Contributing

## Golden rules
1. **No secrets in the repo**. Use `.env` locally. Keep `infra/.env.example` updated.
2. Every feature needs **tests**.
3. Every endpoint needs **validation** (Pydantic models + explicit enums).
4. Keep changes **small** and **reviewable**.
5. Prefer **deterministic** codepaths (idempotency keys, stable hashing, stable ordering).

## Branching
- `main` is always releasable.
- Use short-lived branches: `feat/...`, `fix/...`, `chore/...`.

## How to run locally
See `README.md` and `docs/RUN_LOCAL.md`.

## How to format/lint/typecheck/test
### Python (each app)
```bash
cd apps/api
poetry run ruff check .
poetry run black .
poetry run mypy .
poetry run pytest
```

Or run the repo-wide checks:
- Bash: `./scripts/py_check.sh`
- PowerShell: `./scripts/py_check.ps1`

### Web (from repo root)
```bash
pnpm lint
pnpm typecheck
pnpm test
pnpm format
```

## Pull requests
PRs must include:
- Description + screenshots (if UI)
- Tests added/updated
- Notes on migrations (if any)
- Updated docs if behaviour changes

CI must be green (lint + typecheck + tests).
