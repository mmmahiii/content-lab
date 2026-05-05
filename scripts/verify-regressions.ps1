# Run the fast regression suite for previously fixed bugs.
#
# This is intentionally narrower than full py_check: it collects the focused
# "this must not come back" lanes that protect known historical fixes.
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

function Invoke-RegressionStep {
    param(
        [string] $RelativePath,
        [string[]] $PytestArgs
    )

    $label = "$RelativePath :: $($PytestArgs -join ' ')"
    Write-Host "==> $label"
    Push-Location (Join-Path $RepoRoot $RelativePath)
    try {
        & poetry run pytest -q @PytestArgs
        if (-not $?) {
            throw "Regression step failed: $label"
        }
        if ($LASTEXITCODE -ne 0) {
            throw "Regression step failed: $label (exit code $LASTEXITCODE)"
        }
    } finally {
        Pop-Location
    }
}

Write-Host "==> Running fast historical regression gates"

Invoke-RegressionStep "packages/editing" @(
    "tests/test_long_hook_render_regression.py",
    "tests/test_overlays.py"
)

Invoke-RegressionStep "packages/qa" @(
    "tests/test_bad_reel_semantic_regression.py",
    "tests/test_caption_meta_language_regression.py",
    "tests/test_overlay_fidelity.py",
    "tests/semantic_reel_regression"
)

Invoke-RegressionStep "packages/creative" @(
    "tests/test_bad_reel_fixtures_shape.py",
    "tests/test_copy_lint.py",
    "tests/test_lint.py"
)

Invoke-RegressionStep "apps/orchestrator" @(
    "tests/test_process_reel_bad_reel_regression.py",
    "tests/test_source_plan_overlay_regression.py"
)

Write-Host "==> Historical regression gates passed"
