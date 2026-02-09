# Deployment Guide for Student Evaluation Azure Function

## Prerequisites

### 1. Azure Resources Required
- Azure Function App (Python 3.9+)
- Azure Key Vault
- Azure Storage Account (for function app storage)
- Application Insights (recommended for monitoring)

### 2. Local Development Tools
- [Azure Functions Core Tools](https://docs.microsoft.com/en-us/azure/azure-functions/functions-run-local)
- Python 3.9 or higher
- Azure CLI

## Setup Steps

### Step 1: Create Azure Resources

#### Create Resource Group
```bash
az group create --name rg-student-evaluation --location eastus
```

#### Create Storage Account
```bash
az storage account create --name <YOUR_STORAGE_ACCOUNT> --resource-group rg-student-evaluation --location eastus --sku Standard_LRS
```

#### Create Key Vault
```bash
az keyvault create --name <YOUR_KEY_VAULT> --resource-group rg-student-evaluation --location eastus
```

#### Store Google API Key in Key Vault
```bash
az keyvault secret set --vault-name <YOUR_KEY_VAULT> --name GOOGLEAPIKEY --value "your-google-api-key-here"
```

#### Create Function App
```bash
az functionapp create --resource-group rg-student-evaluation --consumption-plan-location eastus --runtime python --runtime-version 3.9 --functions-version 4 --name <YOUR_FUNCTION_APP> --storage-account <YOUR_STORAGE_ACCOUNT> --os-type Linux
```

### Step 2: Enable Managed Identity

```bash
az functionapp identity assign --name <YOUR_FUNCTION_APP> --resource-group rg-student-evaluation
```

Copy the `principalId` from the output.

### Step 3: Grant Key Vault Access

```bash
az keyvault set-policy --name <YOUR_KEY_VAULT> --object-id <principal-id-from-step-2> --secret-permissions get list
```

### Step 4: Configure Function App Settings

```bash
az functionapp config appsettings set --name <YOUR_FUNCTION_APP> --resource-group rg-student-evaluation --settings "KEY_VAULT_URL=https://<YOUR_KEY_VAULT>.vault.azure.net/"
```

### Step 5: Local Development Setup

1. Clone/navigate to the function directory:
```bash
cd AzureFunctions/StudentEvaluationFunction
```

2. Create virtual environment:
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Update `local.settings.json`:
```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "KEY_VAULT_URL": "https://<YOUR_KEY_VAULT>.vault.azure.net/",
    "GOOGLE_API_KEY": "your-google-api-key-for-local-testing"
  }
}
```

5. For local testing, you can bypass Key Vault by modifying the function to use the `GOOGLE_API_KEY` environment variable.

### Step 6: Test Locally

1. Start Azure Functions runtime:
```bash
func start
```

2. Test the endpoint:
```bash
python test_create_payload.py
curl -X POST http://localhost:7071/api/evaluate -H "Content-Type: application/json" -d @test_request.json
```

### Step 7: Deploy to Azure

```bash
func azure functionapp publish <YOUR_FUNCTION_APP>
```

### Step 8: Verify Deployment

Get the function URL:
```bash
az functionapp function show --name <YOUR_FUNCTION_APP> --resource-group rg-student-evaluation --function-name evaluate --query invokeUrlTemplate -o tsv
```

Test the deployed function:
```bash
curl -X POST "https://<YOUR_FUNCTION_APP>.azurewebsites.net/api/evaluate?code=<function-key>" -H "Content-Type: application/json" -d @test_request.json
```

## Configuration Updates

### Update Key Vault URL in Function Code

Edit `function_app.py` and update:
```python
KEY_VAULT_URL = "https://<YOUR_KEY_VAULT>.vault.azure.net/"
```

## Monitoring and Troubleshooting

### View Logs
```bash
az webapp log tail --name <YOUR_FUNCTION_APP> --resource-group rg-student-evaluation
```

### Application Insights
Enable Application Insights for better monitoring:
```bash
az monitor app-insights component create --app <YOUR_APP_INSIGHTS> --location eastus --resource-group rg-student-evaluation --application-type web
```

Link to Function App:
```bash
APPINSIGHTS_KEY=$(az monitor app-insights component show --app <YOUR_APP_INSIGHTS> --resource-group rg-student-evaluation --query instrumentationKey -o tsv)

az functionapp config appsettings set --name <YOUR_FUNCTION_APP> --resource-group rg-student-evaluation --settings "APPINSIGHTS_INSTRUMENTATIONKEY=$APPINSIGHTS_KEY"
```

## Security Best Practices

1. **Use Managed Identity**: Enabled by default in this setup
2. **Restrict Network Access**: Configure Function App networking if needed
3. **API Key Management**: Rotate Google API key regularly
4. **Function Keys**: Use function-level keys, rotate periodically
5. **CORS Configuration**: Configure allowed origins if calling from web apps

## Cost Optimization

1. Use Consumption Plan (pay per execution)
2. Optimize image/PDF sizes before sending
3. Monitor invocation counts and execution times
4. Set up budget alerts in Azure

## Updating the Function

To update the deployed function:

1. Make changes locally
2. Test with `func start`
3. Deploy with `func azure functionapp publish <YOUR_FUNCTION_APP>`

## Environment Variables Summary

| Variable | Description | Set In |
|----------|-------------|--------|
| KEY_VAULT_URL | Azure Key Vault URL | Function App Settings |
| GOOGLEAPIKEY | Google API Key | Key Vault Secret |
| AzureWebJobsStorage | Storage connection | Automatic |
| FUNCTIONS_WORKER_RUNTIME | Runtime type | Automatic |

## Troubleshooting Common Issues

### Issue: Cannot access Key Vault
**Solution**: Verify Managed Identity is enabled and has proper permissions

### Issue: Gemini API errors
**Solution**: Check API key validity and quota limits

### Issue: Function timeout
**Solution**: Increase timeout in host.json (default is 5 minutes for consumption plan)

### Issue: Large PDF processing fails
**Solution**: Consider Azure Durable Functions for long-running operations

## Next Steps

1. Implement support for `problem_images` and `reference_answer_images`
2. Add caching layer for repeated evaluations
3. Implement batch processing endpoint
4. Add webhook notifications for completed evaluations
5. Create a front-end interface for easier testing
