az login
az keyvault secret set --vault-name <YourVaultName> --name <SecretName> --value "<YourSecretValue>"

# Create a user-assigned identity

az identity create --name MyIdentity --resource-group <ResourceGroupName>

# Assign it to your Function App

az functionapp identity assign --name <FunctionAppName> --resource-group <ResourceGroupName> --identities <ResourceIdOfIdentity>

# 1. Enable Managed Identity and capture the ID

$principalId = az functionapp identity assign --name <your-function-app-name> --resource-group <resource-group> --query principalId -o tsv

# 2. Grant Key Vault access to that identity

az keyvault set-policy --name <key-vault-name> --object-id $principalId --secret-permissions get list

pg_isready -h <HOST_NAME> -p <PORT_NUMBER> -U <DATABASE_USER> -d <DATABASE_NAME>

$token = az account get-access-token --resource-type oss-rdbms --query accessToken -o tsv
az ad signed-in-user show --query userPrincipalName -o tsv
psql "host=<db-host> dbname=<db-name> user=<db-user> password=$token sslmode=require"

# See who you're logged in as

az account show --query user.name -o tsv

# Get your object ID

az ad signed-in-user show --query id -o tsv

az storage blob list --account-name <your-storage-account> --container-name <your-container> --prefix <folder-path/> --output table --query "[].{Name:name, Url:url}"

# Assign "Storage Blob Data Contributor" role to your identity

az role assignment create `
--assignee "<your-azure-ad-object-id>" `
    --role "Storage Blob Data Contributor" `
  --scope "/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.Storage/storageAccounts/<storage-account-name>"

## Postgresql

<postgres-server-name>

<postgres-admin-user>
<postgres-password-or-token>

az postgres flexible-server firewall-rule create \
  --resource-group YourResourceGroup \
  --name YourServerName \
  --rule-name MyHomeIP \
  --start-ip-address <Your_Current_IP> \
  --end-ip-address <Your_Current_IP>
  
## Azure Functions

curl -X POST "<FUNCTION_URL>?code=<FUNCTION_KEY>" ^
  -H "Content-Type: application/json" ^
  -d "{\"pdf_blob_url\": \"<PDF_BLOB_URL>\", \"exercise_name\": \"EXERCISES\", \"problem_number\": \"5.17\"}" ^
  --output problem_517.png
