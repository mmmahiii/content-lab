# Copies the task agent prompt to clipboard. Run from repo root.
$ErrorActionPreference = "Stop"
$root = (git rev-parse --show-toplevel 2>$null).Trim()
if (-not $root) { throw "Run from inside a git repository." }
$path = Join-Path $root "docs\worktree-prompts.md"
$content = Get-Content $path -Raw
if (-not $content) { throw "docs/worktree-prompts.md not found." }
$m = [regex]::Matches($content, '```markdown\r?\n(.*?)```', [System.Text.RegularExpressions.RegexOptions]::Singleline)
if ($m.Count -lt 2) { throw "Could not find task prompt in worktree-prompts.md." }
$prompt = $m[1].Groups[1].Value.Trim()  # second block (first is master kickoff)
Set-Clipboard -Value $prompt
Write-Host "Task prompt copied. Paste (Ctrl+V) in each task chat." -ForegroundColor Green
