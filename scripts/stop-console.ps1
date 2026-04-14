param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Push-Location $RepoRoot
try {
    & docker compose -f infra/docker-compose.yml --profile app --profile web down
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose down failed."
    }

    Write-Host "Content Lab stack stopped." -ForegroundColor Green
}
finally {
    Pop-Location
}
