$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    & (Join-Path $PSScriptRoot "scripts/stop-console.ps1")
}
finally {
    Pop-Location
}
