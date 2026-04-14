param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ConsoleUrl = "http://127.0.0.1:3000",
    [int]$MaxWaitSeconds = 240,
    [switch]$NoBrowser,
    [switch]$SkipBuild,
    [switch]$Rebuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Compose {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$ComposeArgs
    )

    & docker compose --ansi never -f infra/docker-compose.yml @ComposeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed: $($ComposeArgs -join ' ')"
    }
}

function Ensure-Command {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

function Ensure-EnvFile {
    if (Test-Path ".env") {
        return
    }

    if (Test-Path "infra/.env.example") {
        Copy-Item "infra/.env.example" ".env"
        Write-Host "Created .env from infra/.env.example" -ForegroundColor Yellow
        return
    }

    throw "Missing .env and infra/.env.example was not found."
}

function Ensure-DockerDaemon {
    try {
        docker info *> $null
        return
    }
    catch {
        Write-Host "Docker daemon not reachable. Attempting automatic startup..." -ForegroundColor Yellow
    }

    $bash = Get-Command bash -ErrorAction SilentlyContinue
    $dockerd = Get-Command dockerd -ErrorAction SilentlyContinue
    if ($bash -and $dockerd) {
        & bash -lc "sudo nohup dockerd > /tmp/dockerd.log 2>&1 &"
        Start-Sleep -Seconds 3

        try {
            docker info *> $null
            Write-Host "Docker daemon started automatically." -ForegroundColor Green
            return
        }
        catch {
            # Fall through to the explicit failure message below.
        }
    }

    throw "Docker daemon is not running. Start Docker Desktop or start dockerd, then re-run open-console.ps1."
}

function Get-ComposeContainerId {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Service
    )

    $raw = docker compose --ansi never -f infra/docker-compose.yml ps -q $Service 2>$null
    if (-not $raw) {
        return $null
    }

    $id = $raw.Trim()
    if ($id.Length -eq 0) {
        return $null
    }

    return $id
}

function Wait-ForComposeService {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Service,
        [Parameter(Mandatory = $true)]
        [string[]]$AcceptedStatus,
        [int]$TimeoutSeconds = 120,
        [switch]$RequireZeroExitCode
    )

    $deadline = [datetime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([datetime]::UtcNow -lt $deadline) {
        $containerId = Get-ComposeContainerId -Service $Service
        if ($containerId) {
            $status = (docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $containerId).Trim()
            if ($AcceptedStatus -contains $status) {
                if ($RequireZeroExitCode) {
                    $exitCode = (docker inspect --format '{{.State.ExitCode}}' $containerId).Trim()
                    if ($exitCode -ne "0") {
                        throw "$Service finished with exit code $exitCode."
                    }
                }

                Write-Host "$Service ready: $status" -ForegroundColor Green
                return
            }

            Write-Host "$Service status: $status (waiting)" -ForegroundColor DarkYellow
        }
        else {
            Write-Host "$Service container not found yet (waiting)" -ForegroundColor DarkYellow
        }

        Start-Sleep -Seconds 2
    }

    throw "$Service did not reach an accepted status: $($AcceptedStatus -join ', ')"
}

function Wait-ForHttpReady {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [int]$TimeoutSeconds = 120
    )

    $deadline = [datetime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([datetime]::UtcNow -lt $deadline) {
        try {
            Invoke-RestMethod -Uri $Url -Method Get -ErrorAction Stop | Out-Null
            Write-Host "HTTP ready: $Url" -ForegroundColor Green
            return
        }
        catch {
            # Service still starting.
        }

        Start-Sleep -Seconds 2
    }

    throw "Timed out waiting for $Url"
}

Push-Location $RepoRoot
try {
    Ensure-Command -Name "docker"
    Ensure-EnvFile
    Ensure-DockerDaemon

    if ($SkipBuild) {
        Write-Host "The -SkipBuild switch is no longer needed; the launcher now reuses existing images by default." -ForegroundColor Yellow
    }

    Write-Host "Starting infrastructure..." -ForegroundColor Cyan
    Invoke-Compose -ComposeArgs @("up", "-d", "postgres", "redis", "minio")

    Wait-ForComposeService -Service "postgres" -AcceptedStatus @("healthy", "running") -TimeoutSeconds $MaxWaitSeconds
    Wait-ForComposeService -Service "redis" -AcceptedStatus @("healthy", "running") -TimeoutSeconds $MaxWaitSeconds
    Wait-ForComposeService -Service "minio" -AcceptedStatus @("healthy", "running") -TimeoutSeconds $MaxWaitSeconds

    Write-Host "Ensuring MinIO bucket..." -ForegroundColor Cyan
    Invoke-Compose -ComposeArgs @("up", "minio-init")

    if ($Rebuild) {
        Write-Host "Rebuilding API, worker, orchestrator, and web images..." -ForegroundColor Cyan
        Invoke-Compose -ComposeArgs @("--profile", "app", "--profile", "web", "build", "api", "worker", "orchestrator", "web")
    }
    else {
        Write-Host "Reusing existing app images. Use -Rebuild when you want a fresh image build." -ForegroundColor Cyan
    }

    Write-Host "Applying database migrations..." -ForegroundColor Cyan
    Invoke-Compose -ComposeArgs @("--profile", "app", "run", "--rm", "api", "poetry", "run", "alembic", "upgrade", "head")

    Write-Host "Starting API, worker, orchestrator, and web..." -ForegroundColor Cyan
    $upArgs = @("--profile", "app", "--profile", "web", "up", "-d")
    $upArgs += @("api", "worker", "orchestrator", "web")
    Invoke-Compose -ComposeArgs $upArgs

    Wait-ForComposeService -Service "api" -AcceptedStatus @("healthy", "running") -TimeoutSeconds $MaxWaitSeconds
    Wait-ForComposeService -Service "web" -AcceptedStatus @("healthy", "running") -TimeoutSeconds $MaxWaitSeconds
    Wait-ForHttpReady -Url "http://127.0.0.1:8000/health" -TimeoutSeconds $MaxWaitSeconds
    Wait-ForHttpReady -Url $ConsoleUrl -TimeoutSeconds $MaxWaitSeconds

    if (-not $NoBrowser) {
        Start-Process $ConsoleUrl
    }

    Write-Host ""
    Write-Host "Console ready at $ConsoleUrl" -ForegroundColor Green
    Write-Host "To stop the stack later, run:" -ForegroundColor Cyan
    Write-Host "  powershell -NoProfile -File scripts/stop-console.ps1" -ForegroundColor White
}
finally {
    Pop-Location
}
