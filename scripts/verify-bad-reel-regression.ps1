# Run golden bad-reel fixture regression tests (semantic QA + process-reel wiring).
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

function Invoke-Step {
    param(
        [string] $RelativePath,
        [string] $TestFile
    )
    Write-Host "==> pytest $TestFile in $RelativePath"
    Push-Location (Join-Path $RepoRoot $RelativePath)
    try {
        & poetry run pytest $TestFile -q
    } finally {
        Pop-Location
    }
}

Invoke-Step "packages/qa" "tests/test_bad_reel_semantic_regression.py"
Invoke-Step "packages/creative" "tests/test_bad_reel_fixtures_shape.py"
Invoke-Step "apps/orchestrator" "tests/test_process_reel_bad_reel_regression.py"
Write-Host "==> bad-reel regression done"
