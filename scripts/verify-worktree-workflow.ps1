# Smoke-check worktree multi-agent tooling (no worktrees created). Run from repo root.
# Usage: pwsh -File scripts/verify-worktree-workflow.ps1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (git rev-parse --show-toplevel 2>$null)
if (-not $root) { throw "Run from inside a git repository." }
$root = $root.Trim()
Set-Location $root

$required = @(
    "docs/worktree-prompts.md",
    "docs/WORKTREE_WORKFLOW.md",
    "scripts/worktree-spawn.ps1",
    "scripts/worktree-spawn.sh",
    "scripts/worktree-cleanup.ps1",
    "scripts/worktree-cleanup.sh",
    "scripts/worktree-copy-task.ps1",
    "scripts/worktree-copy-merge.ps1"
)
foreach ($rel in $required) {
    $p = Join-Path $root $rel
    if (-not (Test-Path -LiteralPath $p)) { throw "Missing required file: $rel" }
}

$promptsPath = Join-Path $root "docs/worktree-prompts.md"
$content = Get-Content $promptsPath -Raw

$taskPattern = '(?s)##\s+1\)\s+Task Agent Initial Prompt.*?\r?\n```markdown\r?\n(.*?)```'
$mergePattern = '(?s)##\s+2\)\s+Merge Agent Genesis Prompt.*?\r?\n```markdown\r?\n(.*?)```'
$opt = [System.Text.RegularExpressions.RegexOptions]::Singleline

$taskMatch = [regex]::Match($content, $taskPattern, $opt)
$mergeMatch = [regex]::Match($content, $mergePattern, $opt)
if (-not $taskMatch.Success) { throw "Task prompt block not found (heading ## 1) Task Agent ... ```markdown)." }
if (-not $mergeMatch.Success) { throw "Merge prompt block not found (heading ## 2) Merge Agent ... ```markdown)." }

$taskBody = $taskMatch.Groups[1].Value.Trim()
$mergeBody = $mergeMatch.Groups[1].Value.Trim()
if ($taskBody -notmatch "You are a task agent") { throw "Task prompt body looks wrong (expected 'You are a task agent')." }
if ($mergeBody -notmatch "You are the merge agent") { throw "Merge prompt body looks wrong (expected 'You are the merge agent')." }

Write-Host "OK: worktree workflow files and prompt extraction checks passed." -ForegroundColor Green
