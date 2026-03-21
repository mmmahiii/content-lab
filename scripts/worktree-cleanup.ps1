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

#region agent log
$script:AgentDebugLogPath = Join-Path (Split-Path -Parent $PSScriptRoot) "debug-48ea62.log"
function Write-AgentDebugLog {
    param(
        [Parameter(Mandatory = $true)][string]$HypothesisId,
        [Parameter(Mandatory = $true)][string]$Location,
        [Parameter(Mandatory = $true)][string]$Message,
        [hashtable]$Data = @{}
    )
    $payload = [ordered]@{
        sessionId    = "48ea62"
        runId        = $env:WORKTREE_CLEANUP_DEBUG_RUN_ID
        hypothesisId = $HypothesisId
        location     = $Location
        message      = $Message
        data         = $Data
        timestamp    = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    }
    $line = ($payload | ConvertTo-Json -Compress -Depth 8)
    Add-Content -LiteralPath $script:AgentDebugLogPath -Value $line -Encoding utf8 -ErrorAction SilentlyContinue
}
#endregion

function New-Slug {
    param([Parameter(Mandatory = $true)][string]$Name)
    $slug = $Name.Trim().ToLowerInvariant()
    $slug = [regex]::Replace($slug, "[^a-z0-9]+", "-")
    $slug = $slug.Trim('-')
    if ([string]::IsNullOrWhiteSpace($slug)) { throw "Could not derive slug from '$Name'." }
    return $slug
}

# Run git with stderr redirected to a file so PowerShell 7+ (ErrorAction Stop) never treats
# expected failures (e.g. "not a working tree") as terminating errors.
function Invoke-GitCaptured {
    param(
        [Parameter(Mandatory = $true)][string]$WorkDir,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList
    )
    $outPath = Join-Path $env:TEMP ("worktree-cleanup-{0}-out.txt" -f [Guid]::NewGuid().ToString('N'))
    $errPath = Join-Path $env:TEMP ("worktree-cleanup-{0}-err.txt" -f [Guid]::NewGuid().ToString('N'))
    try {
        $p = Start-Process -FilePath 'git' -WorkingDirectory $WorkDir -ArgumentList $ArgumentList `
            -Wait -PassThru -NoNewWindow -RedirectStandardOutput $outPath -RedirectStandardError $errPath
        $stdout = if (Test-Path -LiteralPath $outPath) {
            Get-Content -LiteralPath $outPath -Raw -ErrorAction SilentlyContinue
        } else { '' }
        return [PSCustomObject]@{
            ExitCode = $p.ExitCode
            StdOut   = $stdout
        }
    } finally {
        Remove-Item -LiteralPath $outPath, $errPath -ErrorAction SilentlyContinue
    }
}

if (($Count -gt 0) -and $Tasks) { throw "Use either -Count or -Tasks, not both." }
if (($Count -le 0) -and (-not $Tasks -or $Tasks.Count -eq 0)) { throw "Provide -Count <N> or -Tasks <list>." }

$cwd = (Get-Location).Path
$rTop = Invoke-GitCaptured -WorkDir $cwd -ArgumentList @('rev-parse', '--show-toplevel')
if ($rTop.ExitCode -ne 0) { throw "Run from inside a git repository." }
$repoRoot = $rTop.StdOut.Trim()
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

function Get-NormalizedFullPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    try {
        return [System.IO.Path]::GetFullPath($Path)
    } catch {
        return $null
    }
}

function Test-PathIsRegisteredWorktree {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$CandidatePath
    )
    $resolved = (Resolve-Path -LiteralPath $CandidatePath -ErrorAction SilentlyContinue).Path
    if (-not $resolved) { return $false }
    $resolvedNorm = Get-NormalizedFullPath $resolved
    if (-not $resolvedNorm) { return $false }
    $rList = Invoke-GitCaptured -WorkDir $RepoRoot -ArgumentList @('worktree', 'list')
    if ($rList.ExitCode -ne 0) { return $false }
    $lines = $rList.StdOut -split "`r?`n"
    foreach ($line in $lines) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        $wtPath = ($line -split '\s{2,}', 2)[0].Trim()
        if ([string]::IsNullOrWhiteSpace($wtPath)) { continue }
        $r = (Resolve-Path -LiteralPath $wtPath -ErrorAction SilentlyContinue).Path
        if (-not $r) { continue }
        $rNorm = Get-NormalizedFullPath $r
        if ($rNorm -and [string]::Equals($rNorm, $resolvedNorm, [StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    return $false
}

foreach ($f in $folders) {
    $path = Join-Path $parentDir $f
    if (-not (Test-Path -LiteralPath $path)) {
        Write-Host "Skipped (not found): $path" -ForegroundColor Yellow
        continue
    }

    #region agent log
    $cwdNorm = Get-NormalizedFullPath $cwd
    $pathNorm = Get-NormalizedFullPath $path
    $trimPath = if ($pathNorm) { $pathNorm.TrimEnd('\') } else { "" }
    $cwdInsideWt = $false
    if ($cwdNorm -and $trimPath) {
        $cwdInsideWt = ($cwdNorm.Equals($trimPath, [StringComparison]::OrdinalIgnoreCase)) -or
            $cwdNorm.StartsWith(($trimPath + '\'), [StringComparison]::OrdinalIgnoreCase)
    }
    Write-AgentDebugLog -HypothesisId "H1" -Location "worktree-cleanup.ps1:loop" -Message "before worktree remove" -Data @{
        path           = $path
        cwd            = $cwd
        cwdInsideWorktree = $cwdInsideWt
    }
    #endregion

    $r1 = Invoke-GitCaptured -WorkDir $repoRoot -ArgumentList @('worktree', 'remove', $path)
    if ($r1.ExitCode -ne 0) {
        $rForce = Invoke-GitCaptured -WorkDir $repoRoot -ArgumentList @('worktree', 'remove', '--force', $path)
        #region agent log
        Write-AgentDebugLog -HypothesisId "H2" -Location "worktree-cleanup.ps1:git-remove" -Message "worktree remove exit codes" -Data @{
            path          = $path
            removeExit    = $r1.ExitCode
            forceExit     = $rForce.ExitCode
        }
        #endregion
    }
    else {
        #region agent log
        Write-AgentDebugLog -HypothesisId "H2" -Location "worktree-cleanup.ps1:git-remove" -Message "worktree remove first try ok" -Data @{
            path       = $path
            removeExit = $r1.ExitCode
        }
        #endregion
    }

    if (-not (Test-Path -LiteralPath $path)) {
        Write-Host "Removed: $path" -ForegroundColor Green
        continue
    }

    # Folder still on disk but Git says it is not a worktree (stale/orphan after prune/manual edits).
    $stillReg = Test-PathIsRegisteredWorktree -RepoRoot $repoRoot -CandidatePath $path
    #region agent log
    Write-AgentDebugLog -HypothesisId "H3" -Location "worktree-cleanup.ps1:orphan-check" -Message "path still exists after git remove" -Data @{
        path                = $path
        stillRegistered     = $stillReg
    }
    #endregion
    if ($stillReg) {
        Write-Host "Skipped (could not remove; still a registered worktree): $path" -ForegroundColor Yellow
        continue
    }

    #region agent log
    $wtList = Invoke-GitCaptured -WorkDir $repoRoot -ArgumentList @('worktree', 'list')
    $wtRaw = if ($null -eq $wtList.StdOut) { "" } else { $wtList.StdOut.Trim() }
    $wtSnippet = if ($wtRaw.Length -le 500) { $wtRaw } else { $wtRaw.Substring(0, 500) }
    $dotGit = Join-Path $path ".git"
    $dotGitExists = Test-Path -LiteralPath $dotGit
    $topCount = 0
    try {
        $topCount = @(Get-ChildItem -LiteralPath $path -Force -ErrorAction Stop).Count
    } catch {
        $topCount = -1
    }
    Write-AgentDebugLog -HypothesisId "H5" -Location "worktree-cleanup.ps1:pre-remove-item" -Message "context before Remove-Item orphan path" -Data @{
        path             = $path
        cwdInsideWorktree = $cwdInsideWt
        oneDriveInPath   = ($path -like '*OneDrive*')
        dotGitExists     = $dotGitExists
        topLevelCount    = $topCount
        worktreeListExit = $wtList.ExitCode
        worktreeListSnip = $wtSnippet
    }
    #endregion

    #region agent log
    try {
        Remove-Item -LiteralPath $path -Recurse -Force
        Write-AgentDebugLog -HypothesisId "H4" -Location "worktree-cleanup.ps1:remove-item" -Message "Remove-Item succeeded" -Data @{ path = $path }
    }
    catch {
        Write-AgentDebugLog -HypothesisId "H4" -Location "worktree-cleanup.ps1:remove-item" -Message "Remove-Item failed" -Data @{
            path      = $path
            exception = $_.Exception.GetType().FullName
            message   = $_.Exception.Message
        }
        throw
    }
    #endregion
    Write-Host "Removed orphaned folder: $path" -ForegroundColor Green
}

$null = Invoke-GitCaptured -WorkDir $repoRoot -ArgumentList @('worktree', 'prune')
Write-Host "Pruned." -ForegroundColor Green

if ($DeleteBranches -and $branches.Count -gt 0) {
    $rBranch = Invoke-GitCaptured -WorkDir $repoRoot -ArgumentList @('branch', '--show-current')
    $currentBranch = $rBranch.StdOut.Trim()
    if ($currentBranch -ne "main") {
        Write-Host "Skipping branch deletion (not on main). Switch to main first." -ForegroundColor Yellow
    } else {
        foreach ($b in $branches) {
            $rRef = Invoke-GitCaptured -WorkDir $repoRoot -ArgumentList @('show-ref', '--verify', '--quiet', "refs/heads/$b")
            if ($rRef.ExitCode -eq 0) {
                $rDel = Invoke-GitCaptured -WorkDir $repoRoot -ArgumentList @('branch', '-d', $b)
                if ($rDel.ExitCode -eq 0) {
                    Write-Host "Deleted local: $b" -ForegroundColor Green
                } else {
                    Write-Host "Skipped local $b (not fully merged or in use)" -ForegroundColor Yellow
                }
            }
            $rRem = Invoke-GitCaptured -WorkDir $repoRoot -ArgumentList @('show-ref', '--verify', '--quiet', "refs/remotes/origin/$b")
            if ($rRem.ExitCode -eq 0) {
                $rPush = Invoke-GitCaptured -WorkDir $repoRoot -ArgumentList @('push', 'origin', '--delete', $b)
                if ($rPush.ExitCode -eq 0) {
                    Write-Host "Deleted remote: origin/$b" -ForegroundColor Green
                } else {
                    Write-Host "Skipped remote origin/$b (push failed)" -ForegroundColor Yellow
                }
            }
        }
    }
}
