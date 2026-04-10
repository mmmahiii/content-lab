Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-CheckedStep {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Description,

    [Parameter(Mandatory = $true)]
    [scriptblock]$Script
  )

  & $Script

  if (-not $?) {
    throw "$Description failed."
  }

  if ($LASTEXITCODE -ne 0) {
    throw "$Description failed with exit code $LASTEXITCODE."
  }
}

$projects = @(
  "packages/shared/py",
  "packages/core",
  "packages/auth",
  "packages/storage",
  "packages/assets",
  "packages/creative",
  "packages/editing",
  "packages/outbox",
  "packages/qa",
  "packages/runs",
  "apps/api",
  "apps/worker",
  "apps/orchestrator"
)

foreach ($project in $projects) {
  Write-Host "==> Checking $project"
  Push-Location $project
  try {
    Invoke-CheckedStep "poetry install --no-interaction" { poetry install --no-interaction }
    Invoke-CheckedStep "poetry run ruff check ." { poetry run ruff check . }
    Invoke-CheckedStep "poetry run ruff format --check ." { poetry run ruff format --check . }
    Invoke-CheckedStep "poetry run mypy ." { poetry run mypy . }
    Invoke-CheckedStep "poetry run pytest -q" { poetry run pytest -q }
  }
  finally {
    Pop-Location
  }
}
