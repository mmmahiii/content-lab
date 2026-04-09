param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ApiBaseUrl = "http://127.0.0.1:8000",
    [string]$OrgId = "",
    [string]$PageId = "",
    [ValidateSet("page", "global")]
    [string]$PolicyScope = "page",
    [string]$ActorId = "operator:manual-smoke",
    [string]$PagePlatform = "instagram",
    [string]$PageDisplayName = "Smoke Test Page",
    [string]$PageHandle = "@smoketest",
    [string]$FamilyName = "Smoke Family",
    [string]$VariantLabel = "A"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($PageId -and -not $OrgId) {
    throw "Provide -OrgId when reusing an existing -PageId."
}

$script:RequestCounter = 0
$envFile = Join-Path $RepoRoot ".env"
$dockerComposeFile = Join-Path $RepoRoot "infra/docker-compose.yml"

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Write-Detail {
    param([string]$Message)
    Write-Host $Message -ForegroundColor DarkGray
}

function Assert-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

function ConvertTo-SqlLiteral {
    param([string]$Value)
    return "'" + $Value.Replace("'", "''") + "'"
}

function ConvertTo-ShSingleQuoted {
    param([string]$Value)
    return "'" + $Value.Replace("'", "'""'""'") + "'"
}

function Get-EnvSetting {
    param([string]$Name)

    $processValue = [System.Environment]::GetEnvironmentVariable($Name)
    if (-not [string]::IsNullOrWhiteSpace($processValue)) {
        return $processValue.Trim()
    }

    if (-not (Test-Path $envFile)) {
        return $null
    }

    $line = Get-Content $envFile | Where-Object { $_ -match "^\s*$Name=(.*)$" } | Select-Object -First 1
    if ($null -eq $line) {
        return $null
    }

    $rawValue = ($line -split "=", 2)[1].Trim()
    if ($rawValue.Length -ge 2) {
        if (
            ($rawValue.StartsWith('"') -and $rawValue.EndsWith('"')) -or
            ($rawValue.StartsWith("'") -and $rawValue.EndsWith("'"))
        ) {
            $rawValue = $rawValue.Substring(1, $rawValue.Length - 2)
        }
    }
    return $rawValue
}

function Assert-RunwayKeyConfigured {
    $runwayKey = Get-EnvSetting -Name "RUNWAY_API_KEY"
    if ([string]::IsNullOrWhiteSpace($runwayKey) -or $runwayKey -eq "changeme") {
        throw "RUNWAY_API_KEY is not configured in .env or the current environment."
    }
}

function New-RequestId {
    $script:RequestCounter += 1
    return "manual-smoke-{0:d3}" -f $script:RequestCounter
}

function Invoke-ApiJson {
    param(
        [ValidateSet("GET", "POST", "PATCH")]
        [string]$Method,
        [string]$Path,
        [object]$Body = $null
    )

    $headers = @{
        "X-Actor-Id" = $ActorId
        "X-Request-Id" = New-RequestId
    }
    $uri = "{0}{1}" -f $ApiBaseUrl.TrimEnd("/"), $Path
    $params = @{
        Method = $Method
        Uri = $uri
        Headers = $headers
        ErrorAction = "Stop"
    }
    if ($null -ne $Body) {
        $params["ContentType"] = "application/json"
        $params["Body"] = ($Body | ConvertTo-Json -Depth 20)
    }
    return Invoke-RestMethod @params
}

function Assert-ApiHealthy {
    try {
        $health = Invoke-RestMethod -Method GET -Uri ("{0}/health" -f $ApiBaseUrl.TrimEnd("/")) -ErrorAction Stop
    } catch {
        throw "API health check failed at $ApiBaseUrl/health. Start the API before running this smoke."
    }

    if ($health.status -ne "ok") {
        throw "API health check returned an unexpected payload: $($health | ConvertTo-Json -Depth 10 -Compress)"
    }
}

function Invoke-PostgresQuery {
    param([string]$Sql)

    $output = & docker compose -f $dockerComposeFile exec -T postgres `
        psql -U contentlab -d contentlab -v ON_ERROR_STOP=1 -At -F "|" -c $Sql 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Postgres query failed.`n$output"
    }
    # Single-line psql output is a [string]; piping it to Where-Object iterates *characters*.
    # Normalize to an array of lines so .Count and joins behave correctly under StrictMode.
    $lines = if ($null -eq $output) {
        @()
    } elseif ($output -is [array]) {
        $output
    } else {
        @($output.ToString() -split '\r?\n')
    }
    return @($lines | Where-Object { $_ -ne "" -and $_ -ne $null })
}

function Assert-ComposeServiceRunning {
    param([string]$ServiceName)

    $status = (& docker compose -f $dockerComposeFile ps --status running --services 2>$null) |
        Where-Object { $_ -eq $ServiceName }
    if (-not $status) {
        throw "Docker Compose service '$ServiceName' is not running. Start infra before this smoke."
    }
}

function Get-MinioListing {
    param(
        [string]$Bucket,
        [string]$Prefix
    )

    $minioUser = Get-EnvSetting -Name "MINIO_ROOT_USER"
    $minioPassword = Get-EnvSetting -Name "MINIO_ROOT_PASSWORD"
    if ([string]::IsNullOrWhiteSpace($minioUser) -or [string]::IsNullOrWhiteSpace($minioPassword)) {
        throw "MINIO_ROOT_USER or MINIO_ROOT_PASSWORD is not configured."
    }

    $aliasSet = "mc alias set local http://minio:9000 {0} {1} >/dev/null" -f `
        (ConvertTo-ShSingleQuoted $minioUser), `
        (ConvertTo-ShSingleQuoted $minioPassword)
    $listCommand = "mc ls --recursive local/{0}/{1}" -f $Bucket, $Prefix.TrimStart("/")
    $command = "{0} && {1}" -f $aliasSet, $listCommand

    $output = & docker compose -f $dockerComposeFile run --rm --no-deps --entrypoint /bin/sh `
        minio-init -c $command 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "MinIO listing failed.`n$output"
    }
    return @($output | Where-Object { $_ -and $_.Trim() })
}

function Assert-Contains {
    param(
        [System.Collections.IEnumerable]$Collection,
        [string]$Expected,
        [string]$Label
    )

    $items = @($Collection)
    if ($items -notcontains $Expected) {
        throw "$Label does not include '$Expected'. Actual values: $($items -join ', ')"
    }
}

function Assert-Truth {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

Write-Step "Checking prerequisites"
Assert-Command -Name "docker"
Assert-Command -Name "poetry"
Assert-Command -Name "ffmpeg"
Assert-ComposeServiceRunning -ServiceName "postgres"
Assert-ComposeServiceRunning -ServiceName "minio"
Assert-RunwayKeyConfigured
Assert-ApiHealthy

$bucket = Get-EnvSetting -Name "MINIO_BUCKET"
if ([string]::IsNullOrWhiteSpace($bucket)) {
    $bucket = "content-lab"
}

$orgCreated = $false
if ([string]::IsNullOrWhiteSpace($OrgId)) {
    Write-Step "Creating a fresh smoke-test org directly in Postgres"
    $OrgId = ([guid]::NewGuid()).Guid
    $orgSlug = "manual-smoke-{0}" -f (Get-Date -Format "yyyyMMddHHmmss")
    $insertOrgSql = "insert into orgs (id, name, slug) values ({0}, {1}, {2});" -f `
        (ConvertTo-SqlLiteral $OrgId), `
        (ConvertTo-SqlLiteral "Manual Smoke Org"), `
        (ConvertTo-SqlLiteral $orgSlug)
    Invoke-PostgresQuery -Sql $insertOrgSql | Out-Null
    $orgCreated = $true
    Write-Detail "Created org $OrgId ($orgSlug)."
} else {
    Write-Step "Reusing existing org $OrgId"
    $orgLookup = Invoke-PostgresQuery -Sql (
        "select id, slug from orgs where id = {0};" -f (ConvertTo-SqlLiteral $OrgId)
    )
    if ($orgLookup.Count -eq 0) {
        throw "Org $OrgId was not found."
    }
    Write-Detail "Found org: $($orgLookup[0])"
}

if ([string]::IsNullOrWhiteSpace($PageId)) {
    Write-Step "Creating an owned page through the real API"
    $pageExternalId = "manual-smoke-page-{0}" -f (Get-Date -Format "yyyyMMddHHmmss")
    $page = Invoke-ApiJson -Method POST -Path "/orgs/$OrgId/pages" -Body @{
        platform = $PagePlatform
        display_name = $PageDisplayName
        external_page_id = $pageExternalId
        handle = $PageHandle
        ownership = "owned"
        metadata = @{
            persona = @{
                label = "Calm educator"
                audience = "Busy founders"
                content_pillars = @("operations")
            }
            constraints = @{
                allow_direct_cta = $true
                max_hashtags = 4
            }
            timezone = "UTC"
            locale = "en"
        }
    }
    $PageId = [string]$page.id
    Write-Detail "Created page $PageId."
} else {
    Write-Step "Reusing existing page $PageId"
    $page = Invoke-ApiJson -Method GET -Path "/orgs/$OrgId/pages/$PageId"
    if ([string]$page.ownership -ne "owned") {
        throw "Page $PageId is not owned; manual smoke requires an owned page."
    }
    Write-Detail "Found owned page '$($page.display_name)'."
}

Write-Step "Upserting the applicable policy"
$policyBody = @{
    mode_ratios = @{
        exploit = 0.0
        explore = 1.0
        mutation = 0.0
        chaos = 0.0
    }
    budget = @{
        per_run_usd_limit = 20.0
        daily_usd_limit = 50.0
        monthly_usd_limit = 500.0
    }
}
if ($PolicyScope -eq "global") {
    $policy = Invoke-ApiJson -Method PATCH -Path "/orgs/$OrgId/policy/global" -Body $policyBody
    Write-Detail "Updated global policy $($policy.id)."
} else {
    $policy = Invoke-ApiJson -Method PATCH -Path "/orgs/$OrgId/policy/page/$PageId" -Body $policyBody
    Write-Detail "Updated page policy $($policy.id)."
}

Write-Step "Creating a reel family"
$family = Invoke-ApiJson -Method POST -Path "/orgs/$OrgId/pages/$PageId/reel-families" -Body @{
    name = "$FamilyName $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")"
    mode = "explore"
    metadata = @{
        smoke = $true
        source = "scripts/manual-smoke-reel.ps1"
    }
}
$familyId = [string]$family.id
Write-Detail "Created family $familyId."

Write-Step "Creating a generated reel"
$reel = Invoke-ApiJson -Method POST -Path "/orgs/$OrgId/pages/$PageId/reel-families/$familyId/reels" -Body @{
    origin = "generated"
    status = "draft"
    variant_label = $VariantLabel
    metadata = @{
        smoke = $true
        source = "scripts/manual-smoke-reel.ps1"
    }
}
$reelId = [string]$reel.id
Write-Detail "Created reel $reelId."

Write-Step "Queueing process_reel via the real trigger route"
$queuedRun = Invoke-ApiJson -Method POST -Path "/orgs/$OrgId/pages/$PageId/reels/$reelId/trigger" -Body @{
    input_params = @{
        priority = "high"
    }
    metadata = @{
        source = "manual-smoke"
    }
}
$runId = [string]$queuedRun.id
Write-Detail "Queued run $runId."

Write-Step "Executing the real process_reel flow with the queued run_id"
Push-Location (Join-Path $RepoRoot "apps/orchestrator")
try {
    # Prefect logs to stderr. Windows PowerShell 5 treats merged stderr as
    # NativeCommandError; PS 7+ can also honor stderr when ErrorAction is Stop.
    $restoreEap = $ErrorActionPreference
    $restoreNativeErr = $null
    $ErrorActionPreference = "Continue"
    if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
        $restoreNativeErr = $PSNativeCommandUseErrorActionPreference
        $PSNativeCommandUseErrorActionPreference = $false
    }
    try {
        $flowOutput = & poetry run python -m content_lab_orchestrator.cli run `
            --flow process_reel `
            --reel-id $reelId `
            --run-id $runId 2>&1 |
            ForEach-Object {
                if ($_ -is [System.Management.Automation.ErrorRecord]) {
                    $_.Exception.Message
                } else {
                    "$_"
                }
            } |
            Out-String
    } finally {
        $ErrorActionPreference = $restoreEap
        if ($null -ne $restoreNativeErr) {
            $PSNativeCommandUseErrorActionPreference = $restoreNativeErr
        }
    }
    if ($LASTEXITCODE -ne 0) {
        throw "process_reel execution failed.`n$flowOutput"
    }
    Write-Detail ($flowOutput.Trim())
} finally {
    Pop-Location
}

Write-Step "Loading final API state"
$runDetail = Invoke-ApiJson -Method GET -Path "/orgs/$OrgId/runs/$runId"
$packageDetail = Invoke-ApiJson -Method GET -Path "/orgs/$OrgId/packages/$runId"
$reelDetail = Invoke-ApiJson -Method GET -Path "/orgs/$OrgId/pages/$PageId/reels/$reelId"

Write-Step "Verifying API-level success criteria"
Assert-Truth -Condition ([string]$reelDetail.status -eq "ready") -Message "Expected reel status 'ready' but found '$($reelDetail.status)'."
Assert-Truth -Condition ([string]$runDetail.status -eq "succeeded") -Message "Expected run status 'succeeded' but found '$($runDetail.status)'."
Assert-Truth -Condition ([string]$packageDetail.status -eq "succeeded") -Message "Expected package status 'succeeded' but found '$($packageDetail.status)'."

$taskTypes = @($runDetail.tasks | ForEach-Object { [string]$_.task_type })
foreach ($requiredTask in @("process_reel", "creative_planning", "asset_resolution", "editing", "qa", "packaging")) {
    Assert-Contains -Collection $taskTypes -Expected $requiredTask -Label "Run tasks"
}

$artifactNames = @($packageDetail.artifacts | ForEach-Object { [string]$_.name })
foreach ($requiredArtifact in @("final_video", "cover", "caption_variants", "posting_plan")) {
    Assert-Contains -Collection $artifactNames -Expected $requiredArtifact -Label "Package artifacts"
}
Assert-Truth -Condition (-not [string]::IsNullOrWhiteSpace([string]$packageDetail.provenance_uri)) -Message "Package provenance_uri is missing."
Assert-Truth -Condition (-not [string]::IsNullOrWhiteSpace([string]$packageDetail.manifest_uri)) -Message "Package manifest_uri is missing."

Write-Step "Inspecting Postgres state"
$runRows = Invoke-PostgresQuery -Sql (
    "select id, workflow_key, status from runs where id = {0};" -f (ConvertTo-SqlLiteral $runId)
)
$taskRows = Invoke-PostgresQuery -Sql (
    "select task_type, status from tasks where run_id = {0} order by created_at, task_type;" -f (ConvertTo-SqlLiteral $runId)
)
$reelRows = Invoke-PostgresQuery -Sql (
    "select id, status from reels where id = {0};" -f (ConvertTo-SqlLiteral $reelId)
)
$outboxRows = Invoke-PostgresQuery -Sql (
    "select event_type, delivery_status, aggregate_id from outbox_events where aggregate_id = {0} order by created_at;" -f (ConvertTo-SqlLiteral $runId)
)

Assert-Truth -Condition ($runRows.Count -eq 1) -Message "Run row for $runId was not found."
Assert-Truth -Condition ($reelRows.Count -eq 1) -Message "Reel row for $reelId was not found."
Assert-Truth -Condition ($taskRows.Count -ge 6) -Message "Expected at least 6 task rows for run $runId."
Assert-Truth -Condition (@($outboxRows | Where-Object { $_ -like "process_reel.package_ready|*" }).Count -ge 1) -Message "Expected a process_reel.package_ready outbox row for run $runId."

Write-Host ($runRows -join [Environment]::NewLine)
Write-Host ($taskRows -join [Environment]::NewLine)
Write-Host ($outboxRows -join [Environment]::NewLine)

Write-Step "Listing the package prefix directly from MinIO"
$minioListing = Get-MinioListing -Bucket $bucket -Prefix "reels/packages/$reelId"
if (@($minioListing).Count -eq 0) {
    throw "No objects were listed in MinIO for reels/packages/$reelId."
}
Write-Host ($minioListing -join [Environment]::NewLine)

$minioExpectedFiles = @(
    "final_video.mp4",
    "cover.png",
    "caption_variants.txt",
    "posting_plan.json",
    "provenance.json",
    "package_manifest.json"
)
foreach ($fileName in $minioExpectedFiles) {
    $matching = @($minioListing | Where-Object { $_ -match [regex]::Escape($fileName) })
    Assert-Truth -Condition ($matching.Count -ge 1) -Message "MinIO listing is missing $fileName for reel $reelId."
}

Write-Step "Smoke succeeded"
$summary = [ordered]@{
    org_id = $OrgId
    page_id = $PageId
    reel_family_id = $familyId
    reel_id = $reelId
    run_id = $runId
    reel_status = [string]$reelDetail.status
    run_status = [string]$runDetail.status
    package_root_uri = [string]$packageDetail.package_root_uri
    policy_scope = $PolicyScope
    org_created = $orgCreated
}
$summary | ConvertTo-Json -Depth 10
