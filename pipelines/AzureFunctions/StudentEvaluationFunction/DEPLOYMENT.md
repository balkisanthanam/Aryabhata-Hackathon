# Student Evaluation Function — Deployment Reference

Last updated: 2026-02-20

## 1. Resource Inventory

| Resource | Name | Resource Group | Purpose |
|---|---|---|---|
| Function App | `<FUNCTION_APP_NAME>` | `<FUNCTION_RESOURCE_GROUP>` | Python 3.11 Linux Consumption plan |
| PostgreSQL Flexible Server | `<DB_SERVER_NAME>` | `<DB_RESOURCE_GROUP>` | AAD + password auth enabled |
| Key Vault | `<KEY_VAULT_NAME>` | *(check portal)* | RBAC-based authorization (not access policies) |
| Blob Storage | `kalidasa` | `<BLOB_RESOURCE_GROUP>` | Prompts, PDFs, student uploads, pipeline artifacts |
| Queue Storage | `<QUEUE_STORAGE_ACCOUNT>` | `<FUNCTION_RESOURCE_GROUP>` | `feedback-jobs` queue + Durable Functions task hub |

**Managed Identity:** System-assigned on `<FUNCTION_APP_NAME>`
- Principal ID: `<MANAGED_IDENTITY_PRINCIPAL_ID>`
- Display Name: `<FUNCTION_APP_NAME>`

---

## 2. Deploying Code

```powershell
cd pipelines\AzureFunctions\StudentEvaluationFunction
func azure functionapp publish <FUNCTION_APP_NAME> --python
```

> **IMPORTANT:** `func azure functionapp publish` deploys **code only** — it does NOT push
> `local.settings.json` values. App settings must be configured separately (see §3).

After deployment, verify all 13 functions synced:
```
feedback_queue_trigger      [queueTrigger]
evaluation_orchestrator     [orchestrationTrigger]
read_evaluation             [activityTrigger]
fetch_student_images        [activityTrigger]
split_student_hw            [activityTrigger]
split_textbook              [activityTrigger]
parse_text_ref              [activityTrigger]
validate_inputs             [activityTrigger]
get_chapter_pdf             [activityTrigger]
evaluate_batch              [activityTrigger]
update_evaluation           [activityTrigger]
save_checkpoint             [activityTrigger]
load_checkpoint             [activityTrigger]
```

---

## 3. App Settings (Environment Variables)

These must exist on the Function App. Push them with:

```powershell
az functionapp config appsettings set `
  --name <FUNCTION_APP_NAME> `
  --resource-group <FUNCTION_RESOURCE_GROUP> `
  --settings `
    FEEDBACK_QUEUE_CONNECTION="<<QUEUE_STORAGE_ACCOUNT> connection string>" `
    DB_HOST="<DB_HOST>" `
    DB_NAME="postgres" `
    DB_USER="<FUNCTION_APP_NAME>" `
    DB_PORT="5432" `
    KEY_VAULT_URL="<KEY_VAULT_URL>" `
    KEY_VAULT_SECRET_NAME="<KEY_VAULT_SECRET_NAME>" `
    BLOB_STORAGE_URL="<BLOB_STORAGE_URL>" `
    PROMPTS_CONTAINER="feedback"
```

### Getting the <QUEUE_STORAGE_ACCOUNT> connection string

```powershell
az storage account show-connection-string `
  --name <QUEUE_STORAGE_ACCOUNT> `
  --resource-group <FUNCTION_RESOURCE_GROUP> `
  --query connectionString -o tsv
```

### Pre-existing settings (set automatically by Azure)

These are already configured and should NOT be overwritten:
- `AzureWebJobsStorage` — connection string to `<QUEUE_STORAGE_ACCOUNT>` (Durable Functions task hub)
- `FUNCTIONS_WORKER_RUNTIME` = `python`
- `FUNCTIONS_EXTENSION_VERSION` = `~4`

### Verify all settings

```powershell
az functionapp config appsettings list `
  --name <FUNCTION_APP_NAME> `
  --resource-group <FUNCTION_RESOURCE_GROUP> `
  --query "[].name" -o tsv
```

### Key notes on DB_USER

- `DB_USER` must be **`<FUNCTION_APP_NAME>`** (the Managed Identity display name)
- The function authenticates to PostgreSQL using `DefaultAzureCredential` → AAD token
- Do NOT use your personal AAD account (`<PERSONAL_AAD_ACCOUNT>`)

---

## 4. Managed Identity Permissions

### 4a. Required RBAC Role Assignments

| Storage/Service | Role | Scope | Why |
|---|---|---|---|
| `kalidasa` | **Storage Blob Data Contributor** | storage account | Read prompts/PDFs + **write** pipeline artifacts |
| `<KEY_VAULT_NAME>` | **Key Vault Secrets User** | vault | Read Gemini API key (`<KEY_VAULT_SECRET_NAME>`) |
| `<QUEUE_STORAGE_ACCOUNT>` | *(connection string)* | N/A | Queue trigger + Durable task hub use account key, not MI |

#### Assign blob contributor (if not already set)

```powershell
# Find kalidasa's resource group (it's NOT in <FUNCTION_RESOURCE_GROUP>)
az storage account show --name kalidasa --query resourceGroup -o tsv
# → <BLOB_RESOURCE_GROUP>

az role assignment create `
  --assignee "<MANAGED_IDENTITY_PRINCIPAL_ID>" `
  --role "Storage Blob Data Contributor" `
  --scope "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<BLOB_RESOURCE_GROUP>/providers/Microsoft.Storage/storageAccounts/kalidasa"
```

#### Assign Key Vault secrets reader (if not already set)

```powershell
az role assignment create `
  --assignee "<MANAGED_IDENTITY_PRINCIPAL_ID>" `
  --role "Key Vault Secrets User" `
  --scope "/subscriptions/<SUBSCRIPTION_ID>/providers/Microsoft.KeyVault/vaults/<KEY_VAULT_NAME>"
```

#### Verify role assignments

```powershell
az role assignment list `
  --assignee <MANAGED_IDENTITY_PRINCIPAL_ID> `
  --query "[].{role:roleDefinitionName, scope:scope}" -o table
```

### 4b. PostgreSQL AAD Admin Registration

The Managed Identity must be registered as an AAD administrator on the PostgreSQL server.
This is **separate** from RBAC — it's a PostgreSQL-level config.

#### Check current admins

```powershell
$serverId = "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<DB_RESOURCE_GROUP>/providers/Microsoft.DBforPostgreSQL/flexibleServers/<DB_SERVER_NAME>"

az rest --method GET `
  --url "${serverId}/administrators?api-version=2022-12-01" `
  --query "value[].{name:properties.principalName, type:properties.principalType}" `
  -o table
```

#### Register MI as admin (if not listed)

```powershell
$principalId = "<MANAGED_IDENTITY_PRINCIPAL_ID>"
$tenantId = "<TENANT_ID>"

az rest --method PUT `
  --url "${serverId}/administrators/${principalId}?api-version=2022-12-01" `
  --body "{
    \`"properties\`": {
      \`"principalType\`": \`"ServicePrincipal\`",
      \`"principalName\`": \`"<FUNCTION_APP_NAME>\`",
      \`"tenantId\`": \`"${tenantId}\`"
    }
  }"
```

> This operation takes ~60 seconds to complete.

---

## 5. Post-Deployment Checklist

After every deployment, verify:

- [ ] All 13 functions synced (check `func publish` output)
- [ ] App settings are present (`az functionapp config appsettings list`)
- [ ] `DB_USER` = `<FUNCTION_APP_NAME>` (not personal AAD account)
- [ ] MI has `Storage Blob Data Contributor` on `kalidasa`
- [ ] MI has `Key Vault Secrets User` on `<KEY_VAULT_NAME>`
- [ ] MI is registered as PostgreSQL AAD admin on `<DB_SERVER_NAME>`
- [ ] Restart function app after any settings change:
  ```powershell
  az functionapp restart --name <FUNCTION_APP_NAME> --resource-group <FUNCTION_RESOURCE_GROUP>
  ```

---

## 6. Troubleshooting

### Job stuck in PENDING

1. **Check app settings** — `func publish` does NOT deploy `local.settings.json`
2. **Check queue** — is the message sitting in `feedback-jobs` or moved to `feedback-jobs-poison`?
3. **Check function app state:**
   ```powershell
   az functionapp show --name <FUNCTION_APP_NAME> `
     --resource-group <FUNCTION_RESOURCE_GROUP> `
     --query state -o tsv
   ```
4. **Restart after config changes:**
   ```powershell
   az functionapp restart --name <FUNCTION_APP_NAME> --resource-group <FUNCTION_RESOURCE_GROUP>
   ```

### Poison queue

If the queue trigger fails 5 times, the message moves to `feedback-jobs-poison`.
Common causes:
- Missing app settings (DB, Key Vault, blob URLs)
- MI not authorized for PostgreSQL / Key Vault / Blob Storage
- `DB_USER` set to wrong identity

### Viewing logs

```powershell
# Stream live logs (Ctrl+C to stop)
az webapp log tail --name <FUNCTION_APP_NAME> --resource-group <FUNCTION_RESOURCE_GROUP>

# Application Insights (if configured)
az monitor app-insights query `
  --app <FUNCTION_APP_NAME> `
  --resource-group <FUNCTION_RESOURCE_GROUP> `
  --analytics-query "traces | top 20 by timestamp desc"
```

### Test the deployed function

```powershell
python tests/test_durable_e2e.py --target deployed `
  --student-work "path\to\student_work.jpg" `
  --text-ref "problem 10.1" `
  --subject Physics --class 11 --no-cleanup
```

Use `--no-cleanup` to keep the `solution_evaluations` row for inspection.

---

## 7. Gotchas & Lessons Learned

1. **`func publish` ≠ full deployment.** It only pushes code. App settings from
   `local.settings.json` are intentionally NOT deployed (they often contain local-only values).

2. **Resources span multiple resource groups.** `kalidasa` is in `<BLOB_RESOURCE_GROUP>`,
   `<DB_SERVER_NAME>` is in `<DB_RESOURCE_GROUP>`, function app is in `<FUNCTION_RESOURCE_GROUP>`.
   RBAC scope paths must use the correct resource group.

3. **Storage Blob Data Reader is not enough.** The function writes pipeline artifacts
   (via `utils/step_blob.py`), so it needs **Contributor**, not just Reader.

4. **PostgreSQL AAD admin ≠ Azure RBAC.** Granting the MI an Azure role on the PG server
   is not sufficient — it must also be registered as an AAD administrator on the server
   itself via the REST API or portal.

5. **Key Vault uses RBAC, not access policies.** `<KEY_VAULT_NAME>` is configured with RBAC-based
   authorization. Use role assignments (`Key Vault Secrets User`), not `az keyvault set-policy`.

6. **`AzureWebJobsStorage` and `FEEDBACK_QUEUE_CONNECTION` both point to `<QUEUE_STORAGE_ACCOUNT>`**
   but serve different purposes: the former is for Durable Functions runtime, the latter is
   for the queue trigger binding.

7. **Test script cleans up DB rows by default.** Use `--no-cleanup` flag to preserve
   `solution_evaluations` rows for post-mortem inspection.

