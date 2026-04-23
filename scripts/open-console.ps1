param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ConsoleUrl = "http://127.0.0.1:3000",
    [int]$MaxWaitSeconds = 240,
    [switch]$NoBrowser,
    [switch]$SkipBuild,
    [switch]$Rebuild,
    [switch]$DockerWeb
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$BuildFingerprintPath = Join-Path $RepoRoot $(if ($DockerWeb) { ".console-docker-web-build-fingerprint" } else { ".console-backend-build-fingerprint" })
$ConsoleStatePath = Join-Path $RepoRoot ".console-state.json"
$ConsoleWebLogPath = Join-Path $RepoRoot ".console-web.log"

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

function Invoke-PreflightRevisionCheck {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    $errFile = [System.IO.Path]::GetTempFileName()
    try {
        if ($env:CONTENT_LAB_PREFLIGHT_DATABASE_URL) {
            $dbUrl = $env:CONTENT_LAB_PREFLIGHT_DATABASE_URL
        }
        else {
            # Host port must match infra/docker-compose.yml (postgres 5433:5432).
            $dbUrl = "postgresql+psycopg://contentlab:contentlab@127.0.0.1:5433/contentlab"
        }

        $poetry = Get-Command poetry -ErrorAction SilentlyContinue
        $apiDir = Join-Path $RepoRoot "apps/api"
        if ($poetry -and (Test-Path -LiteralPath (Join-Path $apiDir "pyproject.toml"))) {
            $savedDbUrl = $env:DATABASE_URL
            try {
                $env:DATABASE_URL = $dbUrl
                Push-Location $apiDir
                $stdout = & poetry run python migrations/preflight_revision_check.py 2>$errFile
                $exit = $LASTEXITCODE
            }
            finally {
                if ($null -ne $savedDbUrl) {
                    $env:DATABASE_URL = $savedDbUrl
                }
                else {
                    Remove-Item -Path Env:DATABASE_URL -ErrorAction SilentlyContinue
                }
                Pop-Location
            }
        }
        else {
            $stdout = docker compose --ansi never -f infra/docker-compose.yml --profile app run --rm api poetry run python migrations/preflight_revision_check.py 2>$errFile
            $exit = $LASTEXITCODE
        }

        $rawErr = if (Test-Path -LiteralPath $errFile) {
            Get-Content -LiteralPath $errFile -Raw
        }
        else {
            $null
        }
        # Get-Content -Raw can return $null for an empty file; StrictMode rejects $null.Length downstream.
        $stderrText = if ($null -eq $rawErr) { "" } else { [string]$rawErr }
        return [PSCustomObject]@{
            ExitCode = $exit
            Stdout   = $stdout
            Stderr   = $stderrText
        }
    }
    finally {
        Remove-Item -LiteralPath $errFile -ErrorAction SilentlyContinue
    }
}

function Get-PostgresDataVolumeName {
    $raw = docker compose --ansi never -f infra/docker-compose.yml ps -q postgres 2>$null
    if (-not $raw) {
        return $null
    }

    $containerId = $raw.Trim()
    if ($containerId.Length -eq 0) {
        return $null
    }

    $mountsJson = docker inspect --format '{{json .Mounts}}' $containerId 2>$null
    if (-not $mountsJson) {
        return $null
    }

    $mounts = $mountsJson | ConvertFrom-Json
    foreach ($mount in $mounts) {
        if ($mount.Destination -eq '/var/lib/postgresql/data' -and $mount.Name) {
            return [string]$mount.Name
        }
    }

    return $null
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
    param(
        [bool]$IncludeWeb = $false
    )

    $paths = @(
        "infra/docker-compose.yml",
        "infra/Dockerfile.api",
        "infra/Dockerfile.worker",
        "infra/Dockerfile.orchestrator",
        "apps/api",
        "apps/worker",
        "apps/orchestrator",
        "packages"
    )

    if ($IncludeWeb) {
        $paths += @(
            "package.json",
            "pnpm-lock.yaml",
            "pnpm-workspace.yaml",
            "tsconfig.base.json",
            "infra/Dockerfile.web",
            "apps/web"
        )
    }

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

function Test-HttpReady {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    }
    catch {
        return $false
    }
}

function Get-ConsolePort {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    $uri = [Uri]$Url
    if ($uri.Port -gt 0) {
        return $uri.Port
    }

    if ($uri.Scheme -eq "https") {
        return 443
    }

    return 80
}

function Quote-PowerShellString {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    return "'$($Value.Replace("'", "''"))'"
}

function Get-ConsoleState {
    if (-not (Test-Path -LiteralPath $ConsoleStatePath)) {
        return $null
    }

    try {
        return Get-Content -LiteralPath $ConsoleStatePath -Raw | ConvertFrom-Json
    }
    catch {
        Write-Host "Ignoring unreadable console state file: $ConsoleStatePath" -ForegroundColor Yellow
        return $null
    }
}

function Set-ConsoleState {
    param(
        [Parameter(Mandatory = $true)]
        [object]$State
    )

    $State | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $ConsoleStatePath
}

function Clear-ConsoleState {
    if (Test-Path -LiteralPath $ConsoleStatePath) {
        Remove-Item -LiteralPath $ConsoleStatePath -Force
    }
}

function Test-ProcessAlive {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ProcessId
    )

    return [bool](Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Stop-ProcessTree {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ProcessId
    )

    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue)
    foreach ($child in $children) {
        Stop-ProcessTree -ProcessId ([int]$child.ProcessId)
    }

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Get-PortListeners {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -Property LocalAddress, LocalPort, OwningProcess -Unique)
}

function Get-PortOwnerMessage {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $listeners = @(Get-PortListeners -Port $Port)
    if ($listeners.Count -eq 0) {
        return "No listener is using port $Port."
    }

    $lines = foreach ($listener in $listeners) {
        $processId = [int]$listener.OwningProcess
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
        if ($process) {
            "PID $processId ($($process.Name)): $($process.CommandLine)"
        }
        else {
            "PID ${processId}: process details unavailable"
        }
    }

    return "Port $Port is already in use:`n$($lines -join "`n")"
}

function Wait-ForPortFree {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [int]$TimeoutSeconds = 30
    )

    $deadline = [datetime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([datetime]::UtcNow -lt $deadline) {
        if (@(Get-PortListeners -Port $Port).Count -eq 0) {
            return
        }

        Start-Sleep -Seconds 1
    }

    throw (Get-PortOwnerMessage -Port $Port)
}

function Stop-TrackedLocalWeb {
    $state = Get-ConsoleState
    if (-not $state -or $state.mode -ne "local-web-dev" -or -not $state.webPid) {
        return
    }

    $webPid = [int]$state.webPid
    if (Test-ProcessAlive -ProcessId $webPid) {
        Write-Host "Stopping tracked local web dev server (PID $webPid)..." -ForegroundColor Cyan
        Stop-ProcessTree -ProcessId $webPid
    }

    Clear-ConsoleState
}

function Stop-DockerWebService {
    $containerId = Get-ComposeContainerId -Service "web"
    if (-not $containerId) {
        return
    }

    Write-Host "Stopping Docker web service so local Next.js can own port 3000..." -ForegroundColor Cyan
    Invoke-Compose -ComposeArgs @("--profile", "web", "rm", "-sf", "web")
}

function Import-RootEnvFile {
    $envPath = Join-Path $RepoRoot ".env"
    if (-not (Test-Path -LiteralPath $envPath)) {
        return
    }

    foreach ($line in Get-Content -LiteralPath $envPath) {
        $trimmed = $line.Trim()
        if ($trimmed.Length -eq 0 -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }

        $separatorIndex = $trimmed.IndexOf("=")
        $name = $trimmed.Substring(0, $separatorIndex).Trim()
        $value = $trimmed.Substring($separatorIndex + 1).Trim()
        if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        if ($name.Length -gt 0) {
            Set-Item -Path "Env:$name" -Value $value
        }
    }
}

function Set-LocalWebEnvironment {
    Import-RootEnvFile
    $env:CONTENT_LAB_API_BASE_URL = "http://127.0.0.1:8000"
    $env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000"
    $env:NEXT_PUBLIC_CONTENT_LAB_API_BASE_URL = "http://127.0.0.1:8000"

    if ($env:CONTENT_LAB_OPERATOR_ORG_ID) {
        $env:NEXT_PUBLIC_CONTENT_LAB_OPERATOR_ORG_ID = $env:CONTENT_LAB_OPERATOR_ORG_ID
    }
}

function Start-OrReuseLocalWeb {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [int]$TimeoutSeconds = 120
    )

    Ensure-Command -Name "pnpm"
    Set-LocalWebEnvironment
    Stop-DockerWebService

    $port = Get-ConsolePort -Url $Url
    $state = Get-ConsoleState
    if ($state -and $state.mode -eq "local-web-dev" -and $state.webPid) {
        $webPid = [int]$state.webPid
        if (Test-ProcessAlive -ProcessId $webPid) {
            try {
                Wait-ForHttpReady -Url $Url -TimeoutSeconds 5
                Write-Host "Reusing local web dev server (PID $webPid)." -ForegroundColor Green
                return
            }
            catch {
                Write-Host "Tracked local web dev server is not responding; restarting it." -ForegroundColor Yellow
                Stop-ProcessTree -ProcessId $webPid
                Clear-ConsoleState
            }
        }
        else {
            Clear-ConsoleState
        }
    }

    Wait-ForPortFree -Port $port -TimeoutSeconds 30

    $repoLiteral = Quote-PowerShellString -Value $RepoRoot
    $logLiteral = Quote-PowerShellString -Value $ConsoleWebLogPath
    $command = "`$ErrorActionPreference = 'Stop'; Set-Location -LiteralPath $repoLiteral; pnpm --filter web dev *> $logLiteral"

    Write-Host "Starting local Next.js dev server with hot reload..." -ForegroundColor Cyan
    $process = Start-Process -FilePath "powershell.exe" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command) `
        -WorkingDirectory $RepoRoot `
        -WindowStyle Hidden `
        -PassThru

    Set-ConsoleState -State ([PSCustomObject]@{
        mode = "local-web-dev"
        webPid = $process.Id
        port = $port
        url = $Url
        logPath = $ConsoleWebLogPath
        startedAt = [DateTimeOffset]::Now.ToString("o")
    })

    try {
        Wait-ForHttpReady -Url $Url -TimeoutSeconds $TimeoutSeconds
    }
    catch {
        Write-Host "Local web dev server failed to become ready. Recent log output:" -ForegroundColor Red
        if (Test-Path -LiteralPath $ConsoleWebLogPath) {
            Get-Content -LiteralPath $ConsoleWebLogPath -Tail 80
        }

        Stop-TrackedLocalWeb
        throw
    }
}

Push-Location $RepoRoot
try {
    Ensure-Command -Name "docker"
    Ensure-EnvFile
    Ensure-DockerDaemon

    if ($SkipBuild -and $Rebuild) {
        throw "Use either -SkipBuild or -Rebuild, not both."
    }

    if ($SkipBuild) {
        Write-Host "Skipping Docker image builds because -SkipBuild was supplied." -ForegroundColor Yellow
    }

    Write-Host "Starting infrastructure..." -ForegroundColor Cyan
    Invoke-Compose -ComposeArgs @("up", "-d", "postgres", "redis", "minio")

    Wait-ForComposeService -Service "postgres" -AcceptedStatus @("healthy", "running") -TimeoutSeconds $MaxWaitSeconds
    Wait-ForComposeService -Service "redis" -AcceptedStatus @("healthy", "running") -TimeoutSeconds $MaxWaitSeconds
    Wait-ForComposeService -Service "minio" -AcceptedStatus @("healthy", "running") -TimeoutSeconds $MaxWaitSeconds

    Write-Host "Ensuring MinIO bucket..." -ForegroundColor Cyan
    Invoke-Compose -ComposeArgs @("up", "minio-init")

    $requiredImages = @("infra-api:latest", "infra-worker:latest", "infra-orchestrator:latest")
    if ($DockerWeb) {
        $requiredImages += "infra-web:latest"
    }

    Write-Host "Checking required Docker images..." -ForegroundColor Cyan
    $missingImages = @($requiredImages | Where-Object { -not (Test-DockerImageExists -ImageName $_) })

    if ($SkipBuild -and $missingImages.Count -gt 0) {
        throw "Missing required Docker images: $($missingImages -join ', '). Run .\open-console.ps1 without -SkipBuild, or run with -Rebuild."
    }

    if ($Rebuild -or ($missingImages.Count -gt 0 -and -not $SkipBuild)) {
        $currentFingerprint = Get-BuildFingerprint -IncludeWeb ([bool]$DockerWeb)

        if ($Rebuild) {
            if ($DockerWeb) {
                Write-Host "Rebuilding API, worker, orchestrator, and web images..." -ForegroundColor Cyan
            }
            else {
                Write-Host "Rebuilding API, worker, and orchestrator images..." -ForegroundColor Cyan
            }
        }
        elseif ($missingImages.Count -gt 0) {
            Write-Host "Building missing app images..." -ForegroundColor Cyan
        }

        $buildArgs = @("--profile", "app", "build", "api", "worker", "orchestrator")
        if ($DockerWeb) {
            $buildArgs = @("--profile", "app", "--profile", "web", "build", "api", "worker", "orchestrator", "web")
        }

        Invoke-Compose -ComposeArgs $buildArgs
        Set-StoredBuildFingerprint -Fingerprint $currentFingerprint
    }
    else {
        if ($DockerWeb) {
            Write-Host "Reusing existing app and web images. Use -Rebuild when you want a fresh image build." -ForegroundColor Cyan
        }
        else {
            Write-Host "Reusing existing backend app images. Web UI will run locally with hot reload." -ForegroundColor Cyan
        }
    }

    $apiHealthUrl = "http://127.0.0.1:8000/health"
    if (-not $Rebuild -and (Test-HttpReady -Url $apiHealthUrl)) {
        Write-Host "API is already healthy; skipping migration check for faster relaunch. Use -Rebuild after backend/schema changes." -ForegroundColor Cyan
    }
    else {
        Write-Host "Applying database migrations..." -ForegroundColor Cyan
        $postgresVol = Get-PostgresDataVolumeName

        # #region agent log
        $debugLogPath = Join-Path $RepoRoot "debug-bf703d.log"
        $pf = Invoke-PreflightRevisionCheck -RepoRoot $RepoRoot
        $jsonLine = ($pf.Stdout -split "`r?`n") | Where-Object { $_ -match '^\s*\{' } | Select-Object -Last 1
        $parsed = $null
        if ($jsonLine) {
            try {
                $parsed = $jsonLine | ConvertFrom-Json
            }
            catch {
                $parsed = $null
            }
        }
        $stderrTail = [string]$pf.Stderr
        if ($stderrTail.Length -gt 2000) {
            $stderrTail = $stderrTail.Substring($stderrTail.Length - 2000)
        }
        $logPayload = [ordered]@{
            sessionId    = "bf703d"
            runId        = "preflight"
            hypothesisId = "H1-H5"
            location     = "open-console.ps1:ApplyMigrations"
            message      = "preflight_revision_check"
            data         = @{
                exitCode              = $pf.ExitCode
                postgresVolume        = $postgresVol
                stderrTail            = $stderrTail
                parsed                = $parsed
                H1_unknown_revision   = [bool]($parsed -and $parsed.stale -and $parsed.unknown_script_versions -and $parsed.unknown_script_versions.Count -gt 0)
                H2_empty_db_mismatch  = [bool]($pf.ExitCode -ne 0 -and $parsed -and (-not $parsed.db_versions -or $parsed.db_versions.Count -eq 0))
                H3_preflight_failed   = [bool]($pf.ExitCode -eq 1)
                H4_multiple_unknown   = [bool]($parsed -and $parsed.unknown_script_versions -and $parsed.unknown_script_versions.Count -gt 1)
                H5_no_postgres_volume = [bool](-not $postgresVol)
            }
            timestamp    = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        }
        Add-Content -LiteralPath $debugLogPath -Value (($logPayload | ConvertTo-Json -Compress -Depth 10))
        # #endregion

        if ($pf.ExitCode -eq 1) {
            throw "Migration preflight failed (exit $($pf.ExitCode)). Stdout: $($pf.Stdout) Stderr: $($pf.Stderr)"
        }

        if ($pf.ExitCode -eq 2) {
            if ($env:CONTENT_LAB_NO_AUTO_DB_RESET -eq "1") {
                $bad = if ($parsed -and $parsed.unknown_script_versions) { $parsed.unknown_script_versions -join ', ' } else { "?" }
                throw "Database reports Alembic revision(s) not in this repo ($bad). Unset CONTENT_LAB_NO_AUTO_DB_RESET to allow resetting the local Postgres volume, or run docker compose -f infra/docker-compose.yml down -v (removes compose volumes)."
            }
            if (-not $postgresVol) {
                throw "Migration preflight reports a stale Alembic revision but could not resolve the Postgres Docker volume name."
            }
            Write-Host "Local Postgres has an unknown Alembic revision (not in this repo). Resetting Postgres data volume..." -ForegroundColor Yellow
            Invoke-Compose -ComposeArgs @("stop", "postgres")
            Invoke-Compose -ComposeArgs @("rm", "-f", "postgres")
            docker volume rm $postgresVol
            if ($LASTEXITCODE -ne 0) {
                throw "docker volume rm failed for $postgresVol"
            }
            Invoke-Compose -ComposeArgs @("up", "-d", "postgres")
            Wait-ForComposeService -Service "postgres" -AcceptedStatus @("healthy", "running") -TimeoutSeconds $MaxWaitSeconds

            $pfAfter = Invoke-PreflightRevisionCheck -RepoRoot $RepoRoot
            $jsonAfter = ($pfAfter.Stdout -split "`r?`n") | Where-Object { $_ -match '^\s*\{' } | Select-Object -Last 1
            $parsedAfter = $null
            if ($jsonAfter) {
                try {
                    $parsedAfter = $jsonAfter | ConvertFrom-Json
                }
                catch {
                    $parsedAfter = $null
                }
            }
            # #region agent log
            $logAfter = [ordered]@{
                sessionId    = "bf703d"
                runId        = "post-reset"
                hypothesisId = "H1-H5"
                location     = "open-console.ps1:ApplyMigrations"
                message      = "preflight_revision_check_after_volume_reset"
                data         = @{
                    exitCode       = $pfAfter.ExitCode
                    parsed         = $parsedAfter
                    stale_after    = if ($parsedAfter) { [bool]$parsedAfter.stale } else { $null }
                }
                timestamp    = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
            }
            Add-Content -LiteralPath $debugLogPath -Value (($logAfter | ConvertTo-Json -Compress -Depth 10))
            # #endregion
            if ($pfAfter.ExitCode -ne 0) {
                throw "Migration preflight failed after Postgres reset (exit $($pfAfter.ExitCode)). Stdout: $($pfAfter.Stdout) Stderr: $($pfAfter.Stderr)"
            }
        }

        Invoke-Compose -ComposeArgs @("--profile", "app", "run", "--rm", "api", "poetry", "run", "alembic", "upgrade", "head")
    }

    if ($DockerWeb) {
        Stop-TrackedLocalWeb
        Write-Host "Starting API, worker, orchestrator, and Docker web..." -ForegroundColor Cyan
        $upArgs = @("--profile", "app", "--profile", "web", "up", "-d", "api", "worker", "orchestrator", "web")
    }
    else {
        Write-Host "Starting API, worker, and orchestrator in Docker..." -ForegroundColor Cyan
        $upArgs = @("--profile", "app", "up", "-d", "api", "worker", "orchestrator")
    }

    Invoke-Compose -ComposeArgs $upArgs

    Wait-ForComposeService -Service "api" -AcceptedStatus @("healthy", "running") -TimeoutSeconds $MaxWaitSeconds
    Wait-ForHttpReady -Url $apiHealthUrl -TimeoutSeconds $MaxWaitSeconds

    if ($DockerWeb) {
        Wait-ForComposeService -Service "web" -AcceptedStatus @("healthy", "running") -TimeoutSeconds $MaxWaitSeconds
        Wait-ForHttpReady -Url $ConsoleUrl -TimeoutSeconds $MaxWaitSeconds
        Set-ConsoleState -State ([PSCustomObject]@{
            mode = "docker-web"
            port = Get-ConsolePort -Url $ConsoleUrl
            url = $ConsoleUrl
            startedAt = [DateTimeOffset]::Now.ToString("o")
        })
    }
    else {
        Start-OrReuseLocalWeb -Url $ConsoleUrl -TimeoutSeconds $MaxWaitSeconds
    }

    if (-not $NoBrowser) {
        Start-Process $ConsoleUrl
    }

    Write-Host ""
    Write-Host "Console ready at $ConsoleUrl" -ForegroundColor Green
    if (-not $DockerWeb) {
        Write-Host "Web UI is running locally with hot reload. Logs: $ConsoleWebLogPath" -ForegroundColor Cyan
    }
    Write-Host "To stop the stack later, run:" -ForegroundColor Cyan
    Write-Host "  powershell -NoProfile -File scripts/stop-console.ps1" -ForegroundColor White
}
finally {
    Pop-Location
}
