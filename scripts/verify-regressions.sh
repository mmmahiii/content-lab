#!/usr/bin/env bash
set -euo pipefail

# Run the fast regression suite for previously fixed bugs.
#
# This is intentionally narrower than full py_check: it collects the focused
# "this must not come back" lanes that protect known historical fixes.

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

run_step() {
  local relative_path="$1"
  shift
  echo "==> ${relative_path} :: $*"
  (
    cd "${repo_root}/${relative_path}"
    poetry run pytest -q "$@"
  )
}

echo "==> Running fast historical regression gates"

run_step "packages/editing" \
  tests/test_long_hook_render_regression.py \
  tests/test_overlays.py

run_step "packages/qa" \
  tests/test_bad_reel_semantic_regression.py \
  tests/test_caption_meta_language_regression.py \
  tests/test_overlay_fidelity.py \
  tests/semantic_reel_regression

run_step "packages/creative" \
  tests/test_bad_reel_fixtures_shape.py \
  tests/test_copy_lint.py \
  tests/test_lint.py

run_step "apps/orchestrator" \
  tests/test_process_reel_bad_reel_regression.py \
  tests/test_source_plan_overlay_regression.py

echo "==> Historical regression gates passed"
