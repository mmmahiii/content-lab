# Copies the task agent prompt to clipboard. Run from repo root.
$ErrorActionPreference = "Stop"
$root = (git rev-parse --show-toplevel 2>$null).Trim()
if (-not $root) { throw "Run from inside a git repository." }
$path = Join-Path $root "docs\worktree-prompts.md"
$content = Get-Content $path -Raw
if (-not $content) { throw "docs/worktree-prompts.md not found." }
# Anchor on heading so extra ```markdown blocks (e.g. coordinator) do not shift indices.
$taskPattern = '(?s)##\s+1\)\s+Task Agent Initial Prompt.*?\r?\n```markdown\r?\n(.*?)```'
$m = [regex]::Match($content, $taskPattern, [System.Text.RegularExpressions.RegexOptions]::Singleline)
if (-not $m.Success) { throw "Could not find task prompt block under '## 1) Task Agent' in worktree-prompts.md." }
$prompt = $m.Groups[1].Value.Trim()
Set-Clipboard -Value $prompt
Write-Host "Task prompt copied. Paste (Ctrl+V) in each task chat." -ForegroundColor Green
