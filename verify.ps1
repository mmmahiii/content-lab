# Canonical scaffold verification entry point.
# Run from repo root: .\verify.ps1
$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try { & (Join-Path $PSScriptRoot "scripts/verify-scaffold.ps1") }
finally { Pop-Location }
