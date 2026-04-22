#!/usr/bin/env bash
# Run golden bad-reel fixture regression tests (semantic QA + process-reel wiring).
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

echo "==> packages/qa: bad_reel semantic regression"
(
  cd "$repo_root/packages/qa"
  poetry run pytest tests/test_bad_reel_semantic_regression.py -q "$@"
)

echo "==> packages/creative: bad_reel shape"
(
  cd "$repo_root/packages/creative"
  poetry run pytest tests/test_bad_reel_fixtures_shape.py -q "$@"
)

echo "==> apps/orchestrator: process_reel bad_reel regression"
(
  cd "$repo_root/apps/orchestrator"
  poetry run pytest tests/test_process_reel_bad_reel_regression.py -q "$@"
)

echo "==> bad-reel regression done"
