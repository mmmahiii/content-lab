#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if command -v python3 >/dev/null 2>&1; then
  python_bin="python3"
elif command -v python >/dev/null 2>&1; then
  python_bin="python"
else
  echo "Missing required command on PATH: python3 or python" >&2
  exit 1
fi

for cmd in docker poetry; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command on PATH: $cmd" >&2
    exit 1
  fi
done

if [[ ! -f .env ]]; then
  cp infra/.env.example .env
fi

run_infra() {
  if command -v make >/dev/null 2>&1; then
    make infra-up
  else
    docker compose -f infra/docker-compose.yml up -d
  fi
}

run_migrate() {
  if command -v make >/dev/null 2>&1; then
    make migrate
  else
    (
      cd apps/api
      poetry run alembic upgrade head
    )
  fi
}

api_port="$("$python_bin" -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
api_base_url="http://127.0.0.1:${api_port}"
log_dir="$(mktemp -d 2>/dev/null || "$python_bin" - <<'PY'
from __future__ import annotations
import tempfile
print(tempfile.mkdtemp())
PY
)"
api_log="$log_dir/api.log"
api_pid=""

cleanup() {
  if [[ -n "${api_pid}" ]]; then
    kill "${api_pid}" >/dev/null 2>&1 || true
    wait "${api_pid}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "==> Starting infra"
run_infra

echo "==> Running migrations"
run_migrate

echo "==> Starting API on ${api_base_url}"
(
  cd apps/api
  poetry run uvicorn content_lab_api.main:app --host 127.0.0.1 --port "${api_port}"
) >"${api_log}" 2>&1 &
api_pid="$!"

echo "==> Running no-regeneration regression"
set +e
"$python_bin" scripts/e2e_no_regen.py --repo-root "$repo_root" --api-base-url "$api_base_url" "$@"
status=$?
set -e

if [[ $status -ne 0 ]]; then
  echo
  echo "No-regeneration regression failed. API log tail (${api_log}):" >&2
  tail -n 80 "${api_log}" >&2 || true
  exit "$status"
fi
