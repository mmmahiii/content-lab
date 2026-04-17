param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ApiBaseUrl = "http://127.0.0.1:8000",
    [string]$OrgId = "",
    [string]$PageId = "",
    [ValidateSet("page", "global")]
    [string]$PolicyScope = "page",
    [string]$ActorId = "operator:manual-smoke",
    [string]$PagePlatform = "instagram",
    [string]$PageDisplayName = "Smoke Test Page",
    [string]$PageHandle = "@smoketest",
    [string]$FamilyName = "Smoke Family",
    [string]$VariantLabel = "A"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($PageId -and -not $OrgId) {
    throw "Provide -OrgId when reusing an existing -PageId."
}

function Assert-Command {
    param([string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

function Get-EnvSetting {
    param(
        [string]$Name,
        [string]$EnvFile
    )

    $processValue = [System.Environment]::GetEnvironmentVariable($Name)
    if (-not [string]::IsNullOrWhiteSpace($processValue)) {
        return $processValue.Trim()
    }

    if (-not (Test-Path $EnvFile)) {
        return $null
    }

    $line = Get-Content $EnvFile | Where-Object { $_ -match "^\s*$Name=(.*)$" } | Select-Object -First 1
    if ($null -eq $line) {
        return $null
    }

    $rawValue = ($line -split "=", 2)[1].Trim()
    if ($rawValue.Length -ge 2) {
        if (
            ($rawValue.StartsWith('"') -and $rawValue.EndsWith('"')) -or
            ($rawValue.StartsWith("'") -and $rawValue.EndsWith("'"))
        ) {
            $rawValue = $rawValue.Substring(1, $rawValue.Length - 2)
        }
    }
    return $rawValue
}

$envFile = Join-Path $RepoRoot ".env"
Assert-Command -Name "python"

$runwayKey = Get-EnvSetting -Name "RUNWAY_API_KEY" -EnvFile $envFile
if ([string]::IsNullOrWhiteSpace($runwayKey) -or $runwayKey -eq "changeme") {
    throw "RUNWAY_API_KEY is not configured in .env or the current environment."
}

$smokeScript = Join-Path $RepoRoot "scripts/e2e_mvp_smoke.py"
if (-not (Test-Path $smokeScript)) {
    throw "Expected smoke runner at $smokeScript."
}

$arguments = @(
    $smokeScript
    "--repo-root"; $RepoRoot
    "--api-base-url"; $ApiBaseUrl
    "--provider-mode"; "live"
    "--policy-scope"; $PolicyScope
    "--actor-id"; $ActorId
    "--page-platform"; $PagePlatform
    "--page-display-name"; $PageDisplayName
    "--page-handle"; $PageHandle
    "--family-name"; $FamilyName
    "--variant-label"; $VariantLabel
)

if (-not [string]::IsNullOrWhiteSpace($OrgId)) {
    $arguments += @("--org-id", $OrgId)
}
if (-not [string]::IsNullOrWhiteSpace($PageId)) {
    $arguments += @("--page-id", $PageId)
}

$previousMode = [System.Environment]::GetEnvironmentVariable("RUNWAY_API_MODE")
$env:RUNWAY_API_MODE = "live"
try {
    & python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Live provider smoke failed with exit code $LASTEXITCODE."
    }
} finally {
    if ($null -eq $previousMode) {
        Remove-Item Env:RUNWAY_API_MODE -ErrorAction SilentlyContinue
    } else {
        $env:RUNWAY_API_MODE = $previousMode
    }
}
