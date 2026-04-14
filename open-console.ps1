$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    & (Join-Path $PSScriptRoot "scripts/open-console.ps1")
}
finally {
    Pop-Location
}
