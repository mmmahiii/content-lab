#!/usr/bin/env bash
set -euo pipefail
# Run the process_reel content-quality E2E from the repo root.
# Usage: ./scripts/e2e_content_quality.sh [--mode pass|fail] [extra args]
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
cd "$repo_root/apps/orchestrator"
exec poetry run python "$repo_root/scripts/e2e_content_quality.py" "$@"
