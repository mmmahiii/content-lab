# Start the API in a background job, poll /health, then stop the job.
# Use this instead of Start-Job { poetry ... } alone — jobs do not inherit cwd;
# the repo root must be passed in and apps/api must be set inside the job.
#
# From repo root:
#   pwsh -File scripts/api-health-smoke.ps1
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ListenHost = "127.0.0.1",
    [int]$Port = 8000,
    [int]$MaxWaitSeconds = 60
)

$ErrorActionPreference = "Continue"

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
