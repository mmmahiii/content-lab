Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

param(
    [int]$Count,
    [string[]]$Tasks,
    [string]$BaseBranch = "main"
)

function New-Slug {
    param([Parameter(Mandatory = $true)][string]$Name)

    $slug = $Name.Trim().ToLowerInvariant()
    $slug = [regex]::Replace($slug, "[^a-z0-9]+", "-")
    $slug = $slug.Trim('-')
    if ([string]::IsNullOrWhiteSpace($slug)) {
        throw "Could not derive a slug from task '$Name'."
    }
    return $slug
}

if (($Count -gt 0) -and $Tasks) {
    throw "Use either -Count or -Tasks, not both."
}
if (($Count -le 0) -and (-not $Tasks -or $Tasks.Count -eq 0)) {
    throw "Provide either -Count <N> or -Tasks <list>."
}

$repoRoot = (git rev-parse --show-toplevel 2>$null)
if (-not $repoRoot) {
    throw "Run this script from inside a git repository."
}
$repoRoot = $repoRoot.Trim()
$repoName = Split-Path -Leaf $repoRoot
$parentDir = Split-Path -Parent $repoRoot

$baseRef = "origin/$BaseBranch"
$hasRemoteBase = $true
try {
    git show-ref --verify --quiet "refs/remotes/$baseRef"
    if ($LASTEXITCODE -ne 0) {
        $hasRemoteBase = $false
    }
}
catch {
    $hasRemoteBase = $false
}
if (-not $hasRemoteBase) {
    $baseRef = $BaseBranch
}

$created = @()
$targets = @()

if ($Count -gt 0) {
    1..$Count | ForEach-Object {
        $n = $_
        $targets += [PSCustomObject]@{
            Branch = "feat/task-$n"
            Folder = "$repoName-task-$n"
            Label  = "task-$n"
        }
    }
}
else {
    foreach ($taskName in $Tasks) {
        $slug = New-Slug -Name $taskName
        $targets += [PSCustomObject]@{
            Branch = "feat/$slug"
            Folder = "$repoName-$slug"
            Label  = $taskName
        }
    }
}

foreach ($target in $targets) {
    $worktreePath = Join-Path $parentDir $target.Folder

    if (Test-Path $worktreePath) {
        Write-Host "Skipping existing path: $worktreePath" -ForegroundColor Yellow
        continue
    }

    git show-ref --verify --quiet "refs/heads/$($target.Branch)"
    $branchExists = ($LASTEXITCODE -eq 0)

    if ($branchExists) {
        git worktree add "$worktreePath" "$($target.Branch)"
    }
    else {
        git worktree add -b "$($target.Branch)" "$worktreePath" "$baseRef"
    }

    $created += [PSCustomObject]@{
        Task    = $target.Label
        Branch  = $target.Branch
        Worktree = $worktreePath
    }
}

if ($created.Count -eq 0) {
    Write-Host "No new worktrees created." -ForegroundColor Yellow
    exit 0
}

Write-Host "\nCreated worktrees:" -ForegroundColor Green
$created | Format-Table -AutoSize | Out-Host

$branchList = ($created | ForEach-Object { $_.Branch }) -join "`n"
Write-Host "`n--- Copy-paste for merge agent (after tasks finish) ---" -ForegroundColor Magenta
Write-Host @"
Merge these branches in order:
$branchList
"@
Write-Host "---" -ForegroundColor Magenta

Write-Host "`nNext:" -ForegroundColor Cyan
Write-Host "1) Open each Worktree folder in a separate Cursor window."
Write-Host "2) In each window: new chat -> paste task prompt (docs/worktree-prompts.md) -> paste backlog item."
Write-Host "3) After all tasks finish: main worktree -> new chat -> paste merge prompt -> paste branch list above."
