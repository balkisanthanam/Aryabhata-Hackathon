# --- CONFIGURATION (CHANGE THESE) ---
$ResourceGroup = "YourResourceGroup"   # e.g., "MyProject-RG"
$ServerName    = "YourPostgresServer"  # e.g., "my-startup-db"
$RuleName      = "MyHomeIP"            # The name of the rule in Azure
# ------------------------------------

Write-Host "Fetching current Public IP..." -ForegroundColor Cyan
$CurrentIP = Invoke-RestMethod -Uri "https://api.ipify.org"

Write-Host "Detected IP: $CurrentIP" -ForegroundColor Green
Write-Host "Updating Azure Firewall Rule '$RuleName'..." -ForegroundColor Cyan

# This command creates the rule if it doesn't exist, or updates it if it does
az postgres flexible-server firewall-rule create `
    --resource-group $ResourceGroup `
    --name $ServerName `
    --rule-name $RuleName `
    --start-ip-address $CurrentIP `
    --end-ip-address $CurrentIP `
    --output none

Write-Host "Success! Firewall updated." -ForegroundColor Green
