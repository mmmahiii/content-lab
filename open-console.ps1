param(
    [string]$RepoRoot = $PSScriptRoot,
    [string]$ConsoleUrl = "http://127.0.0.1:3000",
    [int]$MaxWaitSeconds = 240,
    [switch]$NoBrowser,
    [switch]$SkipBuild,
    [switch]$Rebuild,
    [switch]$DockerWeb
)

$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    $scriptArgs = @{
        RepoRoot = $RepoRoot
        ConsoleUrl = $ConsoleUrl
        MaxWaitSeconds = $MaxWaitSeconds
    }

    if ($NoBrowser) {
        $scriptArgs.NoBrowser = $true
    }

    if ($SkipBuild) {
        $scriptArgs.SkipBuild = $true
    }

    if ($Rebuild) {
        $scriptArgs.Rebuild = $true
    }

    if ($DockerWeb) {
        $scriptArgs.DockerWeb = $true
    }

    & (Join-Path $PSScriptRoot "scripts/open-console.ps1") @scriptArgs
}
finally {
    Pop-Location
}
