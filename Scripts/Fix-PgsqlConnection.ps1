# Fix-PgsqlConnection.ps1
# Resets the VS Code pgsql extension's `user` field to the correct EXT Entra principal.
# Run this whenever the PostgreSQL connection fails with "password authentication failed".
# Also wired as a VS Code startup task in .vscode/tasks.json.

$settingsPath = Join-Path $env:APPDATA 'Code\User\settings.json'
$extUser = $env:PGSQL_ENTRA_USER
$server  = $env:PGSQL_SERVER_HOST

if ([string]::IsNullOrWhiteSpace($extUser) -or [string]::IsNullOrWhiteSpace($server)) {
    Write-Host "Set PGSQL_ENTRA_USER and PGSQL_SERVER_HOST before running this script."
    exit 1
}

if (-not (Test-Path $settingsPath)) {
    Write-Host "VS Code settings.json not found at $settingsPath"
    exit 1
}

$json = Get-Content $settingsPath -Raw | ConvertFrom-Json

$updated = $false
foreach ($c in $json.'pgsql.connections') {
    if ($c.server -eq $server) {
        $c.user          = $extUser
        $c.entraUserName = $extUser
        $c.connectTimeout = 60
        $updated = $true
    }
}

if ($updated) {
    $json | ConvertTo-Json -Depth 100 | Set-Content -Path $settingsPath -Encoding UTF8
    Write-Host "OK  pgsql profile fixed: user = $extUser"
} else {
    Write-Host "SKIP  No pgsql profile found for $server"
}
