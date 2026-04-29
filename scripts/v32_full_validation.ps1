$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

function Get-FreePort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try {
        return $listener.LocalEndpoint.Port
    }
    finally {
        $listener.Stop()
    }
}

Write-Host "`n=== Content Lab v3.2 full validation starting ===" -ForegroundColor Cyan

if (-not (Test-Path ".\infra\docker-compose.yml")) { throw "Run from repo root." }
if (-not (Test-Path ".\apps\api")) { throw "apps/api not found." }
if (-not (Test-Path ".\packages\editing")) { throw "packages/editing not found." }
if (-not (Test-Path ".\packages\creative")) { throw "packages/creative not found." }
if (-not (Test-Path ".\packages\qa")) { throw "packages/qa not found." }
if (-not (Test-Path ".\scripts\e2e_mvp_smoke.py")) { throw "scripts/e2e_mvp_smoke.py not found." }
if (-not (Test-Path ".\scripts\e2e_no_regen.py")) { throw "scripts/e2e_no_regen.py not found." }

if (-not (Test-Path ".\.env")) {
    if (Test-Path ".\infra\.env.example") {
        Copy-Item ".\infra\.env.example" ".\.env"
    } else {
        throw ".env missing and infra/.env.example not found."
    }
}

$env:RUNWAY_API_MODE = "mock"
$env:CONTENT_LAB_PROVIDER_MODE = "mock"
$env:CONTENT_LAB_RUN_API_HEALTH_SMOKE = "1"
$env:CONTENT_LAB_RUN_ORCHESTRATOR_SMOKE = "1"

Write-Host "`n=== Starting infra ===" -ForegroundColor Cyan
Invoke-Step { docker compose -f .\infra\docker-compose.yml up -d } "docker compose up"

Write-Host "`n=== Running DB migrations ===" -ForegroundColor Cyan
Push-Location .\apps\api
try {
    Invoke-Step { poetry install } "apps/api poetry install"
    Invoke-Step { poetry run alembic upgrade head } "alembic upgrade"
}
finally {
    Pop-Location
}

Write-Host "`n=== JS checks ===" -ForegroundColor Cyan
Invoke-Step { pnpm install } "pnpm install"
Invoke-Step { pnpm lint } "pnpm lint"
Invoke-Step { pnpm typecheck } "pnpm typecheck"
Invoke-Step { pnpm test } "pnpm test"

Write-Host "`n=== Python repo checks ===" -ForegroundColor Cyan
if (Test-Path ".\scripts\py_check.ps1") {
    Invoke-Step { powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\py_check.ps1 } "py_check.ps1"
}

Write-Host "`n=== Regression marker coverage check ===" -ForegroundColor Cyan
$CoverageCheck = @'
from pathlib import Path
import re

root = Path(".").resolve()
test_files = list(root.rglob("test*.py")) + list(root.rglob("*.test.ts")) + list(root.rglob("*.test.tsx"))
if not test_files:
    raise SystemExit("No test files found.")

all_text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in test_files)
required = {
    "hook preservation": [r"The operations reset busy founders can do today", r"hook", r"(wrap|safe.?area|clipp|truncate|fidelity)"],
    "collision detection": [r"(overlap|collision|handoff|crossfade)", r"(overlay|text)"],
    "caption rejection": [r"Create a explore reel", r"Smoke Test Page", r"(meta|system|caption|blocked|lint)"],
    "duration alignment": [r"(duration|timeline)", r"(align|mismatch|drift|tolerance)"],
    "overlay trace": [r"(overlay_render_trace|rendered_overlay|overlay_manifest)"],
}
missing = []
for label, patterns in required.items():
    for pattern in patterns:
        if not re.search(pattern, all_text, flags=re.I):
            missing.append(f"{label}: {pattern}")
if missing:
    raise SystemExit("Coverage markers missing:\n- " + "\n- ".join(missing))
print("v3.2 regression test coverage markers found.")
'@
Invoke-Step { $CoverageCheck | python - } "coverage marker check"

Write-Host "`n=== Targeted Python package tests ===" -ForegroundColor Cyan
$TargetProjects = @(".\packages\editing", ".\packages\creative", ".\packages\qa", ".\packages\storage", ".\apps\orchestrator", ".\apps\api")
foreach ($Project in $TargetProjects) {
    if (Test-Path $Project) {
        Push-Location $Project
        try {
            Invoke-Step { poetry install } "$Project poetry install"
            Invoke-Step { poetry run pytest -q } "$Project pytest"
        }
        finally {
            Pop-Location
        }
    }
}

$ApiPort = Get-FreePort
$ApiBaseUrl = "http://127.0.0.1:$ApiPort"
Write-Host "`n=== Starting temporary API on $ApiBaseUrl ===" -ForegroundColor Cyan
$ApiJob = Start-Job -ScriptBlock {
    param($Root, $Port)
    Set-Location (Join-Path $Root "apps/api")
    poetry run uvicorn content_lab_api.main:app --host 127.0.0.1 --port $Port
} -ArgumentList (Get-Location).Path, $ApiPort

try {
    $deadline = (Get-Date).AddSeconds(75)
    $healthy = $false
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 2
        try {
            $resp = Invoke-RestMethod -Uri "$ApiBaseUrl/health" -Method GET -TimeoutSec 5
            if ($resp.status -eq "ok") { $healthy = $true; break }
        } catch {}
    }
    if (-not $healthy) {
        Receive-Job $ApiJob -Keep | Out-String | Write-Host
        throw "Temporary API did not become healthy."
    }

    Write-Host "`n=== Running MVP smoke ===" -ForegroundColor Cyan
    Invoke-Step { python .\scripts\e2e_mvp_smoke.py --repo-root . --api-base-url $ApiBaseUrl --provider-mode mock } "e2e_mvp_smoke.py"

    Write-Host "`n=== Running no-regeneration regression ===" -ForegroundColor Cyan
    Invoke-Step { python .\scripts\e2e_no_regen.py --repo-root . --api-base-url $ApiBaseUrl } "e2e_no_regen.py"

    Write-Host "`n=== DB-level v3.2 validation ===" -ForegroundColor Cyan
    $DbValidator = @'
import json
import os
from pathlib import Path
import psycopg

REPO_ROOT = Path.cwd().parents[1] if Path.cwd().name == "api" else Path.cwd()

def load_env_value(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'")
    return None

db_url = (
    load_env_value("DATABASE_URL")
    or load_env_value("CONTENT_LAB_DATABASE_URL")
    or load_env_value("POSTGRES_URL")
)
if not db_url:
    raise SystemExit("Could not find DB URL in env/.env.")

if db_url.startswith("postgresql+psycopg://"):
    db_url = "postgresql://" + db_url.split("://", 1)[1]

with psycopg.connect(db_url) as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            select id, status, output_payload
            from runs
            where workflow_key = 'process_reel'
            order by finished_at desc nulls last, updated_at desc
            limit 1
            """
        )
        row = cur.fetchone()

if not row:
    raise SystemExit("No process_reel run found.")

run_id, status, output_payload = row
if status != "succeeded":
    payload = output_payload if isinstance(output_payload, dict) else json.loads(output_payload or "{}")
    task_statuses = payload.get("task_statuses") or {}
    raise SystemExit(
        f"Latest process_reel run is not succeeded: run_id={run_id}, status={status}, task_statuses={task_statuses}"
    )

print(f"Validated latest process_reel run: {run_id}")
print("v3.2 DB/artifact checks can proceed because latest run succeeded.")
'@
    Push-Location .\apps\api
    try {
        Invoke-Step { $DbValidator | poetry run python - } "DB validator"
    }
    finally {
        Pop-Location
    }

    Write-Host "`n=== ALL v3.2 CHECKS PASSED ===" -ForegroundColor Green
}
finally {
    if ($null -ne $ApiJob) {
        Stop-Job $ApiJob -ErrorAction SilentlyContinue | Out-Null
        Receive-Job $ApiJob -ErrorAction SilentlyContinue | Out-Null
        Remove-Job $ApiJob -Force -ErrorAction SilentlyContinue | Out-Null
    }
}
