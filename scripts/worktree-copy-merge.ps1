# Copies the merge agent prompt to clipboard. Run from repo root.
$ErrorActionPreference = "Stop"
$root = (git rev-parse --show-toplevel 2>$null).Trim()
if (-not $root) { throw "Run from inside a git repository." }
$path = Join-Path $root "docs\worktree-prompts.md"
$content = Get-Content $path -Raw
if (-not $content) { throw "docs/worktree-prompts.md not found." }
$mergePattern = '(?s)##\s+2\)\s+Merge Agent Genesis Prompt.*?\r?\n```markdown\r?\n(.*?)```'
$m = [regex]::Match($content, $mergePattern, [System.Text.RegularExpressions.RegexOptions]::Singleline)
if (-not $m.Success) { throw "Could not find merge prompt block under '## 2) Merge Agent' in worktree-prompts.md." }
$prompt = $m.Groups[1].Value.Trim()
Set-Clipboard -Value $prompt
Write-Host "Merge prompt copied. Paste (Ctrl+V) in merge chat." -ForegroundColor Green
