az login
az keyvault secret set --vault-name <YourVaultName> --name <SecretName> --value "<YourSecretValue>"

# Create a user-assigned identity

az identity create --name MyIdentity --resource-group <ResourceGroupName>

# Assign it to your Function App

az functionapp identity assign --name <FunctionAppName> --resource-group <ResourceGroupName> --identities <ResourceIdOfIdentity>

# 1. Enable Managed Identity and capture the ID

$principalId = az functionapp identity assign --name <your-function-app-name> --resource-group rg-student-evaluation --query principalId -o tsv

# 2. Grant Key Vault access to that identity

az keyvault set-policy --name <YOUR_KEYVAULT_NAME> --object-id $principalId --secret-permissions get list

pg_isready -h <HOST_NAME> -p <PORT_NUMBER> -U <DATABASE_USER> -d <DATABASE_NAME>
pg_isready -h <YOUR_PG_SERVER>.postgres.database.azure.com -p 5432 -U <DB_ADMIN_USER> -d postgres

$token = az account get-access-token --resource-type oss-rdbms --query accessToken -o tsv
az ad signed-in-user show --query userPrincipalName -o tsv
psql "host=<YOUR_PG_SERVER>.postgres.database.azure.com dbname=postgres user=<YOUR_ENTRA_USER>@<YOUR_TENANT>.onmicrosoft.com password=$token sslmode=require"

# See who you're logged in as

az account show --query user.name -o tsv

# Get your object ID

az ad signed-in-user show --query id -o tsv

az storage blob list --account-name <your-storage-account> --container-name <your-container> --prefix <folder-path/> --output table --query "[].{Name:name, Url:url}"

az storage blob list --account-name <your-storage-account> --container-name feedback --prefix 11/Maths --output table --query "[].{Name:name, Url:url}"

# Assign "Storage Blob Data Contributor" role to your identity

az role assignment create `
--assignee "<your-azure-ad-object-id>" `
    --role "Storage Blob Data Contributor" `
    --scope "/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.Storage/storageAccounts/<your-storage-account>"

## Postgresql

<YOUR_PG_SERVER>

<DB_ADMIN_USER>
<DB_ADMIN_PASSWORD>

az postgres flexible-server firewall-rule create \
  --resource-group YourResourceGroup \
  --name YourServerName \
  --rule-name MyHomeIP \
  --start-ip-address <Your_Current_IP> \
  --end-ip-address <Your_Current_IP>
  
## Azure Functions

curl -X POST "<https://<YOUR_FUNCTION_APP>.azurewebsites.net/api/extract_image?code=<YOUR_FUNCTION_KEY>>" ^
  -H "Content-Type: application/json" ^
  -d "{\"pdf_blob_url\": \"<https://<YOUR_STORAGE_ACCOUNT>.blob.core.windows.net/feedback/11/Maths/keph105.pdf\>", \"exercise_name\": \"EXERCISES\", \"problem_number\": \"5.17\"}" ^
  --output problem_517.png
