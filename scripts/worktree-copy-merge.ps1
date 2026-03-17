# Copies the merge agent prompt to clipboard. Run from repo root.
$ErrorActionPreference = "Stop"
$root = (git rev-parse --show-toplevel 2>$null).Trim()
if (-not $root) { throw "Run from inside a git repository." }
$path = Join-Path $root "docs\worktree-prompts.md"
$content = Get-Content $path -Raw
if (-not $content) { throw "docs/worktree-prompts.md not found." }
$m = [regex]::Matches($content, '```markdown\r?\n(.*?)```', [System.Text.RegularExpressions.RegexOptions]::Singleline)
if ($m.Count -lt 3) { throw "Could not find merge prompt in worktree-prompts.md." }
$prompt = $m[2].Groups[1].Value.Trim()  # third block
Set-Clipboard -Value $prompt
Write-Host "Merge prompt copied. Paste (Ctrl+V) in merge chat." -ForegroundColor Green
