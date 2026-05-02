$ErrorActionPreference = "Stop"
$repoRoot = "C:\Users\islam\OneDrive\Documents\content-lab"
$workerDir = Join-Path $repoRoot "apps/worker"
$watchPaths = @(
    (Join-Path $repoRoot "apps/worker/src"),
    (Join-Path $repoRoot "packages")
)

function Get-LatestPythonWrite {
    $latest = Get-Date 0
    foreach ($path in $watchPaths) {
        if (Test-Path $path) {
            $candidate = Get-ChildItem -Path $path -Recurse -Include *.py -File -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTimeUtc -Descending |
                Select-Object -First 1
            if ($null -ne $candidate -and $candidate.LastWriteTimeUtc -gt $latest) {
                $latest = $candidate.LastWriteTimeUtc
            }
        }
    }
    return $latest
}

function Start-Worker {
    Set-Location $workerDir
    Write-Host "starting Dramatiq worker"
    return Start-Process `
        -FilePath "poetry" `
        -ArgumentList "run", "dramatiq", "content_lab_worker.worker" `
        -WorkingDirectory $workerDir `
        -NoNewWindow `
        -PassThru
}

function Stop-Worker {
    param($Process)
    if ($null -ne $Process -and -not $Process.HasExited) {
        taskkill /PID $Process.Id /T /F | Out-Null
    }
}

$lastWrite = Get-LatestPythonWrite
$worker = Start-Worker

try {
    while ($true) {
        Start-Sleep -Seconds 2
        if ($worker.HasExited) {
            throw "Dramatiq worker stopped with exit code $($worker.ExitCode)."
        }

        $currentWrite = Get-LatestPythonWrite
        if ($currentWrite -gt $lastWrite) {
            Write-Host "Python change detected; restarting Dramatiq worker"
            Stop-Worker $worker
            $worker = Start-Worker
            $lastWrite = $currentWrite
        }
    }
}
finally {
    Stop-Worker $worker
}
