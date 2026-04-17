Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot

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

function Test-Truthy {
  param(
    [AllowNull()]
    [string]$Value
  )

  if ($null -eq $Value) {
    return $false
  }

  switch ($Value.ToLowerInvariant()) {
    "1" { return $true }
    "true" { return $true }
    "yes" { return $true }
    "on" { return $true }
    default { return $false }
  }
}

function Invoke-OrchestratorSmoke {
  $orchestratorPath = Join-Path $repoRoot "apps/orchestrator"
  Push-Location $orchestratorPath
  try {
    poetry run python -m content_lab_orchestrator.cli run --name verify
  }
  finally {
    Pop-Location
  }
}

function Test-HasPytestTargets {
  if (-not (Test-Path "tests")) {
    return $false
  }

  $testFiles = @(Get-ChildItem "tests" -Recurse -File -Include "test*.py", "*_test.py")
  return $testFiles.Count -gt 0
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
  "packages/ingestion",
  "packages/features",
  "packages/intelligence",
  "apps/api",
  "apps/worker",
  "apps/orchestrator"
)

foreach ($project in $projects) {
  $projectPath = Join-Path $repoRoot $project
  if (-not (Test-Path $projectPath)) {
    Write-Host "==> Skipping missing project $project"
    continue
  }

  Write-Host "==> Checking $project"
  Push-Location $projectPath
  try {
    Invoke-CheckedStep "poetry install --no-interaction" { poetry install --no-interaction }
    Invoke-CheckedStep "poetry run ruff check ." { poetry run ruff check . }
    Invoke-CheckedStep "poetry run ruff format --check ." { poetry run ruff format --check . }
    if (Test-Path "src") {
      Invoke-CheckedStep "poetry run mypy src" { poetry run mypy src }
    }
    else {
      Invoke-CheckedStep "poetry run mypy ." { poetry run mypy . }
    }

    if (Test-HasPytestTargets) {
      Invoke-CheckedStep "poetry run pytest -q" { poetry run pytest -q }
    }
    else {
      Write-Host "No collected pytest targets, skipping pytest"
    }
  }
  finally {
    Pop-Location
  }
}

if (Test-Truthy $env:CONTENT_LAB_RUN_API_HEALTH_SMOKE) {
  Invoke-CheckedStep "API health smoke" {
    & (Join-Path $PSScriptRoot "api-health-smoke.ps1") -RepoRoot $repoRoot
  }
}

if (Test-Truthy $env:CONTENT_LAB_RUN_ORCHESTRATOR_SMOKE) {
  Invoke-CheckedStep "Orchestrator smoke" { Invoke-OrchestratorSmoke }
}
