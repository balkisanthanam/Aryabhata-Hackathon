# Test Azure Function with curl (PowerShell version)
# Works on Windows PowerShell or PowerShell Core

$FUNCTION_URL = if ($env:AZURE_FUNCTION_URL) { $env:AZURE_FUNCTION_URL } else { "<FUNCTION_URL>" }
$FUNCTION_KEY = if ($env:AZURE_FUNCTION_KEY) { $env:AZURE_FUNCTION_KEY } else { "<FUNCTION_KEY>" }
$PAYLOAD_FILE = "payload.json"

Write-Host "Testing Azure Function with curl" -ForegroundColor Cyan
Write-Host "=================================" -ForegroundColor Cyan
Write-Host "URL: $FUNCTION_URL"
Write-Host "Payload: $PAYLOAD_FILE"
Write-Host ""

if (-not (Test-Path $PAYLOAD_FILE)) {
    Write-Host "Error: $PAYLOAD_FILE not found!" -ForegroundColor Red
    Write-Host "Create it first with: python create_curl_payload.py <image_path>"
    exit 1
}

if ($FUNCTION_URL -eq "<FUNCTION_URL>" -or $FUNCTION_KEY -eq "<FUNCTION_KEY>") {
    Write-Host "Set AZURE_FUNCTION_URL and AZURE_FUNCTION_KEY before running this script." -ForegroundColor Red
    exit 1
}

Write-Host "Sending request..." -ForegroundColor Yellow
Write-Host ""

# Using curl (requires curl.exe to be in PATH - included in Windows 10+)
curl.exe -X POST "${FUNCTION_URL}?code=${FUNCTION_KEY}" `
     -H "Content-Type: application/json" `
     -d "@${PAYLOAD_FILE}" `
     -w "`n`nHTTP Status: %{http_code}`n" `
     -o response.json `
     --max-time 300

Write-Host ""
Write-Host "Response saved to: response.json" -ForegroundColor Green
Write-Host ""
Write-Host "Response preview:" -ForegroundColor Cyan
Get-Content response.json -Head 50
