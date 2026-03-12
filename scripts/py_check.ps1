Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projects = @(
  "packages/shared/py",
  "apps/api",
  "apps/worker",
  "apps/orchestrator"
)

foreach ($project in $projects) {
  Write-Host "==> Checking $project"
  Push-Location $project
  try {
    poetry install --no-interaction
    poetry run ruff check .
    poetry run ruff format --check .
    poetry run mypy .
    poetry run pytest -q
  }
  finally {
    Pop-Location
  }
}
