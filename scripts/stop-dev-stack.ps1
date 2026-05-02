$ErrorActionPreference = "SilentlyContinue"

$ports = 3000, 8000
foreach ($port in $ports) {
    $processIds = Get-NetTCPConnection -LocalPort $port |
        Select-Object -ExpandProperty OwningProcess -Unique

    foreach ($processId in $processIds) {
        if ($processId -and $processId -ne $PID) {
            taskkill /PID $processId /T /F | Out-Null
        }
    }
}

$repoNeedle = "content-lab"
$commandNeedles = @(
    "content_lab_api.main:app",
    "content_lab_worker.worker",
    "next dev"
)

$processes = Get-Process -Name powershell, python, python3.11, node -ErrorAction SilentlyContinue
foreach ($process in $processes) {
    if ($process.Id -eq $PID) {
        continue
    }

    $commandLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $($process.Id)").CommandLine
    if ($commandLine -notlike "*$repoNeedle*") {
        continue
    }

    foreach ($needle in $commandNeedles) {
        if ($commandLine -like "*$needle*") {
            taskkill /PID $process.Id /T /F | Out-Null
            break
        }
    }
}

Write-Host "Stopped local API/web/worker dev processes. Docker infra was left running."
