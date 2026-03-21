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

    $r1 = Invoke-GitCaptured -WorkDir $repoRoot -ArgumentList @('worktree', 'remove', $path)
    if ($r1.ExitCode -ne 0) {
        $null = Invoke-GitCaptured -WorkDir $repoRoot -ArgumentList @('worktree', 'remove', '--force', $path)
    }

    if (-not (Test-Path -LiteralPath $path)) {
        Write-Host "Removed: $path" -ForegroundColor Green
        continue
    }

    # Folder still on disk but Git says it is not a worktree (stale/orphan after prune/manual edits).
    $stillReg = Test-PathIsRegisteredWorktree -RepoRoot $repoRoot -CandidatePath $path
    if ($stillReg) {
        Write-Host "Skipped (could not remove; still a registered worktree): $path" -ForegroundColor Yellow
        continue
    }

    $onWindows = ($null -ne (Get-Variable -Name IsWindows -ErrorAction SilentlyContinue) -and $IsWindows) -or ($env:OS -eq 'Windows_NT')
    $orphanRemovedMsgPrinted = $false
    try {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
    catch {
        $usedFallback = $false
        $clearedViaRename = $false
        if ($onWindows -and ($_.Exception -is [System.IO.IOException])) {
            $null = Start-Process -FilePath 'cmd.exe' -ArgumentList @('/c', "rmdir /s /q `"$path`"") `
                -Wait -PassThru -NoNewWindow
            $usedFallback = $true
            if (Test-Path -LiteralPath $path) {
                $empty = Join-Path $env:TEMP ("worktree-cleanup-empty-{0}" -f [Guid]::NewGuid().ToString('N'))
                try {
                    $null = New-Item -ItemType Directory -Path $empty -Force
                    $null = Start-Process -FilePath 'robocopy.exe' -ArgumentList @(
                        $empty, $path, '/MIR', '/NFL', '/NDL', '/NJH', '/NJS', '/NC', '/NS', '/R:2', '/W:1'
                    ) -Wait -PassThru -NoNewWindow
                    $null = Start-Process -FilePath 'cmd.exe' -ArgumentList @('/c', "rmdir /s /q `"$path`"") `
                        -Wait -PassThru -NoNewWindow
                } finally {
                    Remove-Item -LiteralPath $empty -Recurse -Force -ErrorAction SilentlyContinue
                }
            }
            if (Test-Path -LiteralPath $path) {
                $staging = Join-Path $env:TEMP ("worktree-cleanup-staging-{0}" -f [Guid]::NewGuid().ToString('N'))
                try {
                    Move-Item -LiteralPath $path -Destination $staging -Force
                    Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
                    if (Test-Path -LiteralPath $staging) {
                        $null = Start-Process -FilePath 'cmd.exe' -ArgumentList @('/c', "rmdir /s /q `"$staging`"") `
                            -Wait -NoNewWindow
                    }
                } catch {
                    # Same sharing lock as delete; try same-directory rename next.
                }
            }
        }
        # In-place rename often works when rmdir/move fail (directory handle held by IDE / Explorer / OneDrive).
        if (Test-Path -LiteralPath $path) {
            try {
                $orphanNewName = "$f.orphan.$([Guid]::NewGuid().ToString('N').Substring(0, 12))"
                Rename-Item -LiteralPath $path -NewName $orphanNewName
                $orphanFinal = Join-Path $parentDir $orphanNewName
                $clearedViaRename = $true
                Write-Host @"
Expected worktree folder name is now free.
Renamed locked path to:
  $orphanFinal

Delete that folder after closing any workspace, Explorer window, or terminal
using it (or pause OneDrive sync), then remove it manually.
"@ -ForegroundColor Yellow
            } catch {
                # Fall through to error below.
            }
        }
        if (Test-Path -LiteralPath $path) {
            Write-Host @"
Could not remove or rename worktree folder (in use by another process):
  $path

Close anything using that path (IDE workspace, File Explorer, shell cwd),
pause OneDrive if needed, then re-run this script or delete the folder manually.
"@ -ForegroundColor Red
            throw
        }
        if ($clearedViaRename) {
            $orphanRemovedMsgPrinted = $true
        } elseif ($usedFallback) {
            Write-Host "Removed orphaned folder (extended Windows cleanup): $path" -ForegroundColor Green
            $orphanRemovedMsgPrinted = $true
        }
    }
    if (-not $orphanRemovedMsgPrinted) {
        Write-Host "Removed orphaned folder: $path" -ForegroundColor Green
    }
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
