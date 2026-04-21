param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ConsoleStatePath = Join-Path $RepoRoot ".console-state.json"

function Get-ConsoleState {
    if (-not (Test-Path -LiteralPath $ConsoleStatePath)) {
        return $null
    }

    try {
        return Get-Content -LiteralPath $ConsoleStatePath -Raw | ConvertFrom-Json
    }
    catch {
        Write-Host "Ignoring unreadable console state file: $ConsoleStatePath" -ForegroundColor Yellow
        return $null
    }
}

function Clear-ConsoleState {
    if (Test-Path -LiteralPath $ConsoleStatePath) {
        Remove-Item -LiteralPath $ConsoleStatePath -Force
    }
}

function Stop-ProcessTree {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ProcessId
    )

    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue)
    foreach ($child in $children) {
        Stop-ProcessTree -ProcessId ([int]$child.ProcessId)
    }

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Stop-TrackedLocalWeb {
    $state = Get-ConsoleState
    if (-not $state -or $state.mode -ne "local-web-dev" -or -not $state.webPid) {
        Clear-ConsoleState
        return
    }

    $webPid = [int]$state.webPid
    if (Get-Process -Id $webPid -ErrorAction SilentlyContinue) {
        Write-Host "Stopping local web dev server (PID $webPid)..." -ForegroundColor Cyan
        Stop-ProcessTree -ProcessId $webPid
    }

    Clear-ConsoleState
}

Push-Location $RepoRoot
try {
    Stop-TrackedLocalWeb

    & docker compose -f infra/docker-compose.yml --profile app --profile web down
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose down failed."
    }

    Write-Host "Content Lab stack stopped." -ForegroundColor Green
}
finally {
    Pop-Location
}
