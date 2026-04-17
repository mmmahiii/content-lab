#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

projects=(
  "packages/shared/py"
  "packages/core"
  "packages/auth"
  "packages/storage"
  "packages/assets"
  "packages/creative"
  "packages/editing"
  "packages/outbox"
  "packages/qa"
  "packages/runs"
  "packages/ingestion"
  "packages/features"
  "packages/intelligence"
  "apps/api"
  "apps/worker"
  "apps/orchestrator"
)

is_truthy() {
  local value="${1:-0}"
  case "${value,,}" in
    1|true|yes|on)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

has_pytest_targets() {
  find tests -type f \( -name 'test*.py' -o -name '*_test.py' \) -print -quit | grep -q .
}

run_api_health_smoke() {
  local runner=""

  if command -v powershell >/dev/null 2>&1; then
    runner="powershell"
  elif command -v pwsh >/dev/null 2>&1; then
    runner="pwsh"
  else
    echo "Skipping API health smoke: PowerShell is not available."
    return 0
  fi

  echo "==> Running API health smoke"
  "$runner" -NoProfile -File "$script_dir/api-health-smoke.ps1" -RepoRoot "$repo_root"
}

run_orchestrator_smoke() {
  echo "==> Running orchestrator smoke"
  (
    cd "$repo_root/apps/orchestrator"
    poetry run python -m content_lab_orchestrator.cli run --name verify
  )
}

cd "$repo_root"

for p in "${projects[@]}"; do
  if [[ ! -d "$p" ]]; then
    echo "==> Skipping missing project $p"
    continue
  fi

  echo "==> Checking $p"
  pushd "$p" >/dev/null
  poetry install --no-interaction
  poetry run ruff check .
  poetry run ruff format --check .
  if [[ -d src ]]; then
    poetry run mypy src
  else
    poetry run mypy .
  fi
  if [[ -d tests ]] && has_pytest_targets; then
    poetry run pytest -q
  else
    echo "No collected pytest targets, skipping pytest"
  fi
  popd >/dev/null
done

if is_truthy "${CONTENT_LAB_RUN_API_HEALTH_SMOKE:-0}"; then
  run_api_health_smoke
fi

if is_truthy "${CONTENT_LAB_RUN_ORCHESTRATOR_SMOKE:-0}"; then
  run_orchestrator_smoke
fi
