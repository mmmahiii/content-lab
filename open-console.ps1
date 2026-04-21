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
    $args = @(
        "-RepoRoot", $RepoRoot,
        "-ConsoleUrl", $ConsoleUrl,
        "-MaxWaitSeconds", $MaxWaitSeconds
    )

    if ($NoBrowser) {
        $args += "-NoBrowser"
    }

    if ($SkipBuild) {
        $args += "-SkipBuild"
    }

    if ($Rebuild) {
        $args += "-Rebuild"
    }

    if ($DockerWeb) {
        $args += "-DockerWeb"
    }

    & (Join-Path $PSScriptRoot "scripts/open-console.ps1") @args
}
finally {
    Pop-Location
}
