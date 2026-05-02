param(
    [switch]$NoInfra,
    [switch]$Worker,
    [int]$ApiPort = 8000,
    [int]$WebPort = 3000
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$processes = @()
$logPositions = @{}
$logDir = Join-Path $repoRoot ".dev-stack"
$script:DevStackShuttingDown = $false
$script:DevStackCancelHandler = $null

function Start-DevProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$Command
    )

    New-Item -ItemType Directory -Force -Path $logDir | Out-Null

    $outLog = Join-Path $logDir "$Name.out.log"
    $errLog = Join-Path $logDir "$Name.err.log"
    "" | Set-Content -Path $outLog
    "" | Set-Content -Path $errLog

    $childScript = "`$ProgressPreference = 'SilentlyContinue'; Set-Location '$WorkingDirectory'; $Command"
    $encodedCommand = [Convert]::ToBase64String(
        [Text.Encoding]::Unicode.GetBytes($childScript)
    )

    $process = Start-Process `
        -FilePath "powershell" `
        -ArgumentList "-NoProfile -ExecutionPolicy Bypass -EncodedCommand $encodedCommand" `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -WindowStyle Hidden `
        -PassThru

    $entry = [PSCustomObject]@{
        Name = $Name
        Process = $process
        OutLog = $outLog
        ErrLog = $errLog
    }

    $logPositions[$outLog] = 0
    $logPositions[$errLog] = 0
    Write-Host "[$Name] started (pid $($process.Id))"
    return $entry
}

function Start-WorkerWatchProcess {
    $watchScript = @'
$ErrorActionPreference = "Stop"
$repoRoot = "__REPO_ROOT__"
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
'@

    $watchScript = $watchScript.Replace("__REPO_ROOT__", $repoRoot.Replace("'", "''"))
    $watchScriptPath = Join-Path $logDir "worker-watch.ps1"
    Set-Content -Path $watchScriptPath -Value $watchScript

    return Start-DevProcess `
        -Name "worker" `
        -WorkingDirectory $repoRoot `
        -Command "powershell -NoProfile -ExecutionPolicy Bypass -File '$watchScriptPath'"
}

function Write-NewLogLines {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Path
    )

    if (-not (Test-Path $Path)) {
        return
    }

    $stream = [System.IO.File]::Open($Path, "Open", "Read", "ReadWrite")
    try {
        $stream.Seek($logPositions[$Path], [System.IO.SeekOrigin]::Begin) | Out-Null
        $reader = New-Object System.IO.StreamReader($stream)
        while (-not $reader.EndOfStream) {
            $line = $reader.ReadLine()
            if ($line -ne "" -and $line -ne "#< CLIXML") {
                Write-Host ("[{0}] {1}" -f $Name, $line)
            }
        }
        $logPositions[$Path] = $stream.Position
    }
    finally {
        $stream.Dispose()
    }
}

function Stop-DevProcesses {
    if ($processes.Count -eq 0) {
        return
    }

    Write-Host ""
    Write-Host "Stopping live dev stack..."
    foreach ($entry in $processes) {
        $process = Get-Process -Id $entry.Process.Id -ErrorAction SilentlyContinue
        if ($null -ne $process -and -not $process.HasExited) {
            & taskkill /PID $process.Id /T /F 2>$null | Out-Null
        }
    }
}

try {
    Set-Location $repoRoot

    if (-not $NoInfra) {
        Write-Host "[infra] starting Docker Compose infrastructure"
        docker compose -f infra/docker-compose.yml up -d
    }

    $processes += Start-DevProcess `
        -Name "api" `
        -WorkingDirectory (Join-Path $repoRoot "apps/api") `
        -Command "poetry run uvicorn content_lab_api.main:app --reload --host 0.0.0.0 --port $ApiPort"

    if ($Worker) {
        $processes += Start-WorkerWatchProcess
    }

    $processes += Start-DevProcess `
        -Name "web" `
        -WorkingDirectory $repoRoot `
        -Command "pnpm --filter web dev -- --port $WebPort"

    Write-Host ""
    Write-Host "Live dev stack is running."
    Write-Host "Web: http://localhost:$WebPort"
    Write-Host "API: http://localhost:$ApiPort"
    if ($Worker) {
        Write-Host "Worker: enabled"
    }
    else {
        Write-Host "Worker: disabled for a quieter UI/API dev loop"
    }
    Write-Host "Press Ctrl+C to stop API/web. Infra containers stay running."
    Write-Host ""

    try {
        $script:DevStackCancelHandler = [ConsoleCancelEventHandler] {
            param($sender, $e)
            $e.Cancel = $true
            $script:DevStackShuttingDown = $true
        }
        [Console]::add_CancelKeyPress($script:DevStackCancelHandler)
    }
    catch {
        # Non-interactive host (no Console cancel key handling).
    }

    :watchLoop while ($true) {
        foreach ($entry in $processes) {
            Write-NewLogLines -Name $entry.Name -Path $entry.OutLog
            Write-NewLogLines -Name $entry.Name -Path $entry.ErrLog

            $process = Get-Process -Id $entry.Process.Id -ErrorAction SilentlyContinue
            if ($null -eq $process -or $process.HasExited) {
                if ($script:DevStackShuttingDown) {
                    break watchLoop
                }
                throw "$($entry.Name) stopped. See $($entry.OutLog) and $($entry.ErrLog)."
            }
        }

        if ($script:DevStackShuttingDown) {
            break
        }
        Start-Sleep -Milliseconds 500
    }
}
finally {
    if ($null -ne $script:DevStackCancelHandler) {
        try {
            [Console]::remove_CancelKeyPress($script:DevStackCancelHandler)
        }
        catch {
        }
        $script:DevStackCancelHandler = $null
    }
    Stop-DevProcesses
}
