Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Get-Location).Path

Write-Host "Verifying Content Lab scaffold from: $repoRoot" -ForegroundColor Cyan

# 1) Check required tools exist
$required = @("git","docker","python","poetry","node","pnpm","ffmpeg")
foreach ($cmd in $required) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $cmd"
    }
}

# 2) Ensure .env exists
if (-not (Test-Path ".env")) {
    if (Test-Path "infra\.env.example") {
        Copy-Item "infra\.env.example" ".env"
        Write-Host "Created .env from infra\.env.example" -ForegroundColor Yellow
    } elseif (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "Created .env from .env.example" -ForegroundColor Yellow
    } else {
        throw "No .env or .env.example/infra\.env.example found at repo root."
    }
}

# 3) Start infra
docker compose -f infra/docker-compose.yml up -d postgres redis minio minio-init | Out-Host

# 4) Wait for infra readiness
$services = @("postgres","redis","minio")
foreach ($svc in $services) {
    $ready = $false
    for ($i = 1; $i -le 30; $i++) {
        $rawCid = docker compose -f infra/docker-compose.yml ps -q $svc 2>$null
        $cid = if ($rawCid) { $rawCid.Trim() } else { $null }
        if ($cid) {
            $status = (docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $cid).Trim()
            if ($status -in @("healthy","running")) {
                $ready = $true
                Write-Host "$svc ready: $status" -ForegroundColor Green
                break
            } else {
                Write-Host "$svc status: $status (waiting)" -ForegroundColor Yellow
            }
        } else {
            Write-Host "$svc container not found yet (attempt $i)" -ForegroundColor Yellow
        }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) {
        throw "$svc failed to become ready"
    }
}

# 5) Install Node workspace deps
pnpm install | Out-Host

# 6) Install and verify all Python projects
$pyProjects = @(
    "packages/shared/py",
    "apps/api",
    "apps/worker",
    "apps/orchestrator"
)

foreach ($p in $pyProjects) {
    Write-Host "`n==> Checking $p" -ForegroundColor Cyan
    Push-Location $p
    try {
        poetry install --no-interaction | Out-Host
        poetry run ruff check . | Out-Host
        poetry run ruff format --check . | Out-Host
        if (Test-Path "src") {
            poetry run mypy src | Out-Host
        } else {
            poetry run mypy . | Out-Host
        }
        if (Test-Path "tests") {
            poetry run pytest -q | Out-Host
        } else {
            Write-Host "No tests directory, skipping pytest" -ForegroundColor DarkYellow
        }
    }
    finally {
        Pop-Location
    }
}

# 7) Verify TS/Next workspace
Write-Host "`n==> Checking Node workspace" -ForegroundColor Cyan
pnpm lint | Out-Host
pnpm typecheck | Out-Host
pnpm test | Out-Host

# 8) Verify Docker app images build cleanly
Write-Host "`n==> Building Docker app images" -ForegroundColor Cyan
docker compose -f infra/docker-compose.yml --profile app --profile web build | Out-Host

# 9) API smoke test
Write-Host "`n==> API smoke test" -ForegroundColor Cyan
$apiJob = Start-Job -ScriptBlock {
    param($root)
    Set-Location (Join-Path $root "apps/api")
    poetry run uvicorn content_lab_api.main:app --host 127.0.0.1 --port 8000
} -ArgumentList $repoRoot

try {
    $apiReady = $false
    for ($i = 1; $i -le 30; $i++) {
        Start-Sleep -Seconds 2
        try {
            $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method GET
            if ($resp.status -eq "ok" -and $resp.service -eq "api") {
                $apiReady = $true
                Write-Host "API health check passed" -ForegroundColor Green
                break
            }
        } catch {
            # ignore transient failures during startup
        }
    }
    if (-not $apiReady) {
        throw "API health check failed"
    }
}
finally {
    Stop-Job $apiJob -ErrorAction SilentlyContinue | Out-Null
    Receive-Job $apiJob -ErrorAction SilentlyContinue | Out-Null
    Remove-Job $apiJob -Force -ErrorAction SilentlyContinue | Out-Null
}

# 10) Orchestrator smoke test
Write-Host "`n==> Orchestrator smoke test" -ForegroundColor Cyan
Push-Location "apps/orchestrator"
$flowOutput = poetry run python -m content_lab_orchestrator.cli run --name verify
Pop-Location
if ($flowOutput -notmatch "hello verify") {
    throw "Orchestrator flow smoke test failed. Output was: $flowOutput"
}
Write-Host "Orchestrator smoke test passed" -ForegroundColor Green

Write-Host "`nREADY: scaffold passed infra, installs, lint, format, typecheck, tests, Docker build, API health, and orchestrator smoke test." -ForegroundColor Green

