# Removes task worktrees. Use same -Count or -Tasks as spawn.
# Run from main repo after merge chat finishes.
param(
    [int]$Count,
    [string[]]$Tasks
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function New-Slug {
    param([Parameter(Mandatory = $true)][string]$Name)
    $slug = $Name.Trim().ToLowerInvariant()
    $slug = [regex]::Replace($slug, "[^a-z0-9]+", "-")
    $slug = $slug.Trim('-')
    if ([string]::IsNullOrWhiteSpace($slug)) { throw "Could not derive slug from '$Name'." }
    return $slug
}

if (($Count -gt 0) -and $Tasks) { throw "Use either -Count or -Tasks, not both." }
if (($Count -le 0) -and (-not $Tasks -or $Tasks.Count -eq 0)) { throw "Provide -Count <N> or -Tasks <list>." }

$repoRoot = (git rev-parse --show-toplevel 2>$null)
if (-not $repoRoot) { throw "Run from inside a git repository." }
$repoRoot = $repoRoot.Trim()
$repoName = Split-Path -Leaf $repoRoot
$parentDir = Split-Path -Parent $repoRoot

$folders = @()
if ($Count -gt 0) {
    1..$Count | ForEach-Object { $folders += "$repoName-task-$_" }
} else {
    foreach ($t in $Tasks) { $folders += "$repoName-$(New-Slug $t)" }
}

foreach ($f in $folders) {
    $path = Join-Path $parentDir $f
    if (Test-Path $path) {
        git worktree remove $path
        Write-Host "Removed: $path" -ForegroundColor Green
    } else {
        Write-Host "Skipped (not found): $path" -ForegroundColor Yellow
    }
}

git worktree prune
Write-Host "Pruned." -ForegroundColor Green
