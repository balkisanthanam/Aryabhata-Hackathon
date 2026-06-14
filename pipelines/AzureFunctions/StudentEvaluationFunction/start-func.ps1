<#
.SYNOPSIS
    Start the Student Evaluation Azure Function locally.

.DESCRIPTION
    Sets required environment variables and launches `func start`.
    - PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python  (avoids gRPC C extension crash on Python 3.14)
    - languageWorkers__python__defaultExecutablePath  (optional; set via PYTHON_WORKER_PATH)

.EXAMPLE
    .\start-func.ps1
    .\start-func.ps1 -Verbose
#>
[CmdletBinding()]
param()

# ── Environment setup ─────────────────────────────────────────────────────────
$env:PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION = "python"
if ($env:PYTHON_WORKER_PATH) {
    $env:languageWorkers__python__defaultExecutablePath = $env:PYTHON_WORKER_PATH
}

# Skip IMDS probe — locally we always use AzureCliCredential, so avoid the
# 2-3 second timeout on every DefaultAzureCredential call.
$env:AZURE_IDENTITY_DISABLE_IMDS = "true"

# ── Kill stale processes on our port ──────────────────────────────────────────
$port = 7072
$stale = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($stale) {
    Write-Host "Killing stale process on port $port..." -ForegroundColor Yellow
    $stale | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}

# ── Launch ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Starting Student Evaluation Function on port $port" -ForegroundColor Cyan
Write-Host "  Python: $env:languageWorkers__python__defaultExecutablePath" -ForegroundColor DarkGray
Write-Host "  Protobuf: pure-Python mode" -ForegroundColor DarkGray
Write-Host ""

func start
