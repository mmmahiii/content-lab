# Start the API in a background job, poll /health, then stop the job.
# Use this instead of Start-Job { poetry ... } alone — jobs do not inherit cwd;
# the repo root must be passed in and apps/api must be set inside the job.
#
# From repo root (use Windows PowerShell if `pwsh` is not installed):
#   powershell -NoProfile -File scripts/api-health-smoke.ps1
#   pwsh -NoProfile -File scripts/api-health-smoke.ps1
#
# Port: use 0 (default) to bind an ephemeral free port so this never collides with
# another app on 8000 (IDE, old uvicorn, etc.). Pass -Port 8000 only if you need a fixed port.
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ListenHost = "127.0.0.1",
    [int]$Port = 0,
    [int]$MaxWaitSeconds = 60
)

$ErrorActionPreference = "Continue"

function Get-EphemeralListenPort {
    param([string]$BindHost)
    $addr = if ($BindHost -eq "0.0.0.0") {
        [System.Net.IPAddress]::Any
    } else {
        [System.Net.IPAddress]::Parse($BindHost)
    }
    $listener = [System.Net.Sockets.TcpListener]::new($addr, 0)
    $listener.Start()
    try {
        return $listener.LocalEndpoint.Port
    } finally {
        $listener.Stop()
    }
}

if ($Port -le 0) {
    $Port = Get-EphemeralListenPort -BindHost $ListenHost
    Write-Host "Using ephemeral port $Port (avoid conflicts with anything on 8000)." -ForegroundColor DarkGray
} else {
    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count -gt 0) {
        $pids = ($listeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
        Write-Host "Port ${Port} is already in use (OwningProcess: $pids). Use -Port 0 for auto." -ForegroundColor Red
        exit 1
    }
}

$apiJob = Start-Job -ScriptBlock {
    param($Root, $HostAddr, $ListenPort)
    Set-Location (Join-Path $Root "apps/api")
    poetry run uvicorn content_lab_api.main:app --host $HostAddr --port $ListenPort
} -ArgumentList $RepoRoot, $ListenHost, $Port

$ok = $false
try {
    $deadline = [datetime]::UtcNow.AddSeconds($MaxWaitSeconds)
    while ([datetime]::UtcNow -lt $deadline) {
        Start-Sleep -Seconds 2
        try {
            $resp = Invoke-RestMethod -Uri "http://${ListenHost}:${Port}/health" -Method GET -ErrorAction Stop
            if ($resp.status -eq "ok" -and $resp.service -eq "api") {
                Write-Host "API health check passed." -ForegroundColor Green
                $ok = $true
                break
            }
        } catch {
            # still starting
        }
    }
    if (-not $ok) {
        Write-Host "API health check failed (no ok response within ${MaxWaitSeconds}s)." -ForegroundColor Red
        $err = Receive-Job $apiJob -ErrorAction SilentlyContinue
        if ($err) { $err | Out-String | Write-Host }
        throw "API health check failed"
    }
} finally {
    Stop-Job $apiJob -ErrorAction SilentlyContinue | Out-Null
    Receive-Job $apiJob -ErrorAction SilentlyContinue | Out-Null
    Remove-Job $apiJob -Force -ErrorAction SilentlyContinue | Out-Null
}
