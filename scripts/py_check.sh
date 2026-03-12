#!/usr/bin/env bash
set -euo pipefail

projects=(
  "packages/shared/py"
  "apps/api"
  "apps/worker"
  "apps/orchestrator"
)

for p in "${projects[@]}"; do
  echo "==> Checking $p"
  pushd "$p" >/dev/null
  poetry install --no-interaction
  poetry run ruff check .
  poetry run ruff format --check .
  poetry run mypy .
  poetry run pytest -q
  popd >/dev/null
done
