# Removes task worktrees and optionally deletes merged branches (local + remote).
# Use same -Count or -Tasks as spawn.
# Run from main repo after merge chat finishes.
param(
    [int]$Count,
    [string[]]$Tasks,
    [switch]$DeleteBranches = $true
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
$branches = @()
if ($Count -gt 0) {
    1..$Count | ForEach-Object {
        $n = $_
        $folders += "$repoName-task-$n"
        $branches += "feat/task-$n"
    }
} else {
    foreach ($t in $Tasks) {
        $slug = New-Slug $t
        $folders += "$repoName-$slug"
        $branches += "feat/$slug"
    }
}

foreach ($f in $folders) {
    $path = Join-Path $parentDir $f
    if (Test-Path $path) {
        git worktree remove $path
        if ($LASTEXITCODE -ne 0) { git worktree remove --force $path }
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Removed: $path" -ForegroundColor Green
        } else {
            Write-Host "Skipped (worktree invalid or already removed): $path" -ForegroundColor Yellow
        }
    } else {
        Write-Host "Skipped (not found): $path" -ForegroundColor Yellow
    }
}

git worktree prune
Write-Host "Pruned." -ForegroundColor Green

if ($DeleteBranches -and $branches.Count -gt 0) {
    $currentBranch = (git branch --show-current)
    if ($currentBranch -ne "main") {
        Write-Host "Skipping branch deletion (not on main). Switch to main first." -ForegroundColor Yellow
    } else {
        foreach ($b in $branches) {
            git show-ref --verify --quiet "refs/heads/$b"
            if ($LASTEXITCODE -eq 0) {
                git branch -d $b
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "Deleted local: $b" -ForegroundColor Green
                } else {
                    Write-Host "Skipped local $b (not fully merged or in use)" -ForegroundColor Yellow
                }
            }
            git show-ref --verify --quiet "refs/remotes/origin/$b"
            if ($LASTEXITCODE -eq 0) {
                git push origin --delete $b
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "Deleted remote: origin/$b" -ForegroundColor Green
                } else {
                    Write-Host "Skipped remote origin/$b (push failed)" -ForegroundColor Yellow
                }
            }
        }
    }
}
