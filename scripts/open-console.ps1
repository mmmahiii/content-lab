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
$BuildFingerprintPath = Join-Path $RepoRoot ".console-build-fingerprint"

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

function Test-DockerDaemonReachable {
    # With $ErrorActionPreference = "Stop", PowerShell 7+ can treat native stderr (e.g. "cannot connect
    # to the docker API") as a terminating error. That prevented Ensure-DockerDaemon from starting
    # Docker Desktop and waiting. Probe the engine without letting stderr abort the script.
    $savedEap = $ErrorActionPreference
    $hadNativePref = Test-Path variable:PSNativeCommandUseErrorActionPreference
    $prevNative = $false
    if ($hadNativePref) {
        $prevNative = $PSNativeCommandUseErrorActionPreference
        $PSNativeCommandUseErrorActionPreference = $false
    }

    try {
        $ErrorActionPreference = "SilentlyContinue"
        docker info *> $null
        return $LASTEXITCODE -eq 0
    }
    finally {
        $ErrorActionPreference = $savedEap
        if ($hadNativePref) {
            $PSNativeCommandUseErrorActionPreference = $prevNative
        }
    }
}

function Wait-DockerDaemonReachable {
    param(
        [int]$TimeoutSeconds = 180,
        [int]$PollSeconds = 2
    )

    $deadline = [datetime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([datetime]::UtcNow -lt $deadline) {
        if (Test-DockerDaemonReachable) {
            return $true
        }

        Start-Sleep -Seconds $PollSeconds
    }

    return (Test-DockerDaemonReachable)
}

function Test-IsWindowsOs {
    if ($PSVersionTable.PSVersion.Major -ge 6) {
        return $IsWindows
    }

    return $env:OS -eq "Windows_NT"
}

function Get-DockerDesktopExeWindows {
    if (-not (Test-IsWindowsOs)) {
        return $null
    }

    $candidates = @(
        (Join-Path ${env:ProgramFiles} "Docker\Docker\Docker Desktop.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Docker\Docker\Docker Desktop.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Docker\Docker\Docker Desktop.exe")
    )

    foreach ($exe in $candidates) {
        if (Test-Path -LiteralPath $exe) {
            return $exe
        }
    }

    return $null
}

function Try-StartDockerDesktopWindows {
    $exe = Get-DockerDesktopExeWindows
    if (-not $exe) {
        return [PSCustomObject]@{ ExecutableFound = $false; LaunchedUi = $false }
    }

    $running = Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue
    $launched = $false
    if (-not $running) {
        Start-Process -FilePath $exe -ErrorAction SilentlyContinue | Out-Null
        $launched = $true
    }

    return [PSCustomObject]@{ ExecutableFound = $true; LaunchedUi = $launched }
}

function Ensure-DockerDaemon {
    # Fast path when the engine is already up: one `docker info`, no Desktop launch, no waits.
    if (Test-DockerDaemonReachable) {
        return
    }

    Write-Host "Docker engine not reachable yet. Trying to start it (nothing is installed)..." -ForegroundColor Yellow

    $bash = Get-Command bash -ErrorAction SilentlyContinue
    $dockerd = Get-Command dockerd -ErrorAction SilentlyContinue
    if ($bash -and $dockerd) {
        & bash -lc "sudo nohup dockerd > /tmp/dockerd.log 2>&1 &"
        Start-Sleep -Seconds 3

        if (Test-DockerDaemonReachable) {
            Write-Host "Docker daemon started automatically." -ForegroundColor Green
            return
        }
    }

    $dd = Try-StartDockerDesktopWindows
    if ($dd.ExecutableFound) {
        if ($dd.LaunchedUi) {
            Write-Host "Started Docker Desktop. Waiting for the engine (this only runs while Docker is starting)..." -ForegroundColor Yellow
        }
        else {
            Write-Host "Docker Desktop is already running; waiting for the engine..." -ForegroundColor Yellow
        }

        if (Wait-DockerDaemonReachable -TimeoutSeconds 180) {
            Write-Host "Docker daemon is ready." -ForegroundColor Green
            return
        }
    }

    throw "Docker daemon is not running. Start Docker Desktop or start dockerd, then re-run open-console.ps1."
}

function Test-DockerImageExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ImageName
    )

    docker image inspect $ImageName *> $null
    return $LASTEXITCODE -eq 0
}

function Get-BuildFingerprint {
    $paths = @(
        "package.json",
        "pnpm-lock.yaml",
        "pnpm-workspace.yaml",
        "tsconfig.base.json",
        "infra/docker-compose.yml",
        "infra/Dockerfile.api",
        "infra/Dockerfile.worker",
        "infra/Dockerfile.orchestrator",
        "infra/Dockerfile.web",
        "apps/web",
        "apps/api",
        "apps/worker",
        "apps/orchestrator",
        "packages"
    )

    $files = foreach ($path in $paths) {
        if (-not (Test-Path $path)) {
            continue
        }

        $item = Get-Item $path
        if ($item.PSIsContainer) {
            Get-ChildItem -Path $path -Recurse -File | Where-Object {
                $_.FullName -notmatch "\\node_modules\\" -and
                $_.FullName -notmatch "\\.next\\" -and
                $_.FullName -notmatch "\\dist\\" -and
                $_.FullName -notmatch "\\coverage\\" -and
                $_.FullName -notmatch "\\.git\\" -and
                $_.FullName -notmatch "\\__pycache__\\" -and
                $_.Name -ne "tsconfig.tsbuildinfo" -and
                $_.Extension -notin @(".pyc", ".pyo")
            }
        }
        else {
            $item
        }
    }

    $hashInput = $files |
        Sort-Object FullName |
        ForEach-Object {
            $relativePath = $_.FullName.Substring($RepoRoot.Length).TrimStart('\', '/')
            $hashRecord = Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName
            "{0}|{1}|{2}" -f $relativePath, $_.Length, $hashRecord.Hash
        }

    $joined = [string]::Join("`n", $hashInput)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($joined)
    $stream = [System.IO.MemoryStream]::new($bytes)
    try {
        return (Get-FileHash -InputStream $stream -Algorithm SHA256).Hash
    }
    finally {
        $stream.Dispose()
    }
}

function Get-StoredBuildFingerprint {
    if (-not (Test-Path $BuildFingerprintPath)) {
        return $null
    }

    return (Get-Content -Path $BuildFingerprintPath -Raw).Trim()
}

function Set-StoredBuildFingerprint {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Fingerprint
    )

    Set-Content -Path $BuildFingerprintPath -Value $Fingerprint
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

    $requiredImages = @("infra-api:latest", "infra-worker:latest", "infra-orchestrator:latest", "infra-web:latest")
    $missingImages = @($requiredImages | Where-Object { -not (Test-DockerImageExists -ImageName $_) })
    $currentFingerprint = Get-BuildFingerprint
    $storedFingerprint = Get-StoredBuildFingerprint
    $sourceChanged = $storedFingerprint -ne $currentFingerprint

    if ($Rebuild -or $missingImages.Count -gt 0 -or $sourceChanged) {
        if ($Rebuild) {
            Write-Host "Rebuilding API, worker, orchestrator, and web images..." -ForegroundColor Cyan
        }
        elseif ($missingImages.Count -gt 0) {
            Write-Host "Building missing app images..." -ForegroundColor Cyan
        }
        else {
            Write-Host "Source changes detected. Rebuilding app images..." -ForegroundColor Cyan
        }
        Invoke-Compose -ComposeArgs @("--profile", "app", "--profile", "web", "build", "api", "worker", "orchestrator", "web")
        Set-StoredBuildFingerprint -Fingerprint $currentFingerprint
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
