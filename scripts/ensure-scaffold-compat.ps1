# Creates packages/<name>/py compat layout for Cursor scaffold verification.
# Each py/ dir contains symlinks to the parent's pyproject.toml, src, tests.
# Run from repo root.
$ErrorActionPreference = "Stop"
$packages = @("core","auth","storage","assets","creative","editing","qa","runs","outbox","ingestion","features","intelligence")
foreach ($p in $packages) {
    $parent = "packages/$p"
    $pyDir = "$parent/py"
    if (-not (Test-Path $parent)) { continue }
    if (Test-Path $pyDir) { Remove-Item $pyDir -Recurse -Force -ErrorAction SilentlyContinue }
    New-Item -ItemType Directory -Path $pyDir -Force | Out-Null
    Push-Location $pyDir
    try {
        # Symlink key files/dirs from parent
        foreach ($link in @("pyproject.toml","src","tests","poetry.lock")) {
            $target = "..\$link"
            if (Test-Path $target) {
                New-Item -ItemType SymbolicLink -Path $link -Target $target -Force -ErrorAction SilentlyContinue | Out-Null
            }
        }
    }
    finally { Pop-Location }
}
Write-Host "Scaffold compat layout created." -ForegroundColor Green
