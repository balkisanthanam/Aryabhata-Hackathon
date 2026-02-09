# Pre-Flight Checklist for Student Evaluation Azure Function

Use this checklist before deploying to production.

## ✅ Development Environment Setup

### Local Development
- [ ] Python 3.9 or higher installed (`python --version`)
- [ ] Azure Functions Core Tools installed (`func --version`)
- [ ] Azure CLI installed (`az --version`)
- [ ] All dependencies installed (`pip install -r requirements.txt`)
- [ ] Virtual environment activated

### Code Configuration
- [ ] `KEY_VAULT_URL` updated in `function_app.py` (line ~16)
- [ ] `local.settings.json` configured for local testing
- [ ] Google API key available for testing (or Key Vault access)
- [ ] Prompt template URL verified: https://<YOUR_STORAGE>.blob.core.windows.net/feedback/Evaluation.txt

### Verification
- [ ] Run `python check_config.py` - all checks pass
- [ ] Function starts without errors (`func start`)
- [ ] Test payload can be created (`python test_create_payload.py`)

---

## ✅ Azure Resources Setup

### Resource Group
- [ ] Resource group created: `az group create --name rg-student-evaluation --location eastus`
- [ ] Verify: `az group show --name rg-student-evaluation`

### Storage Account
- [ ] Storage account created for function app
- [ ] Name: <YOUR_STORAGE_ACCOUNT> (or your choice, must be globally unique)
- [ ] Command: `az storage account create --name <YOUR_STORAGE_ACCOUNT> --resource-group rg-student-evaluation --location eastus --sku Standard_LRS`
- [ ] Verify: `az storage account show --name <YOUR_STORAGE_ACCOUNT> --resource-group rg-student-evaluation`

### Key Vault
- [ ] Key Vault created
- [ ] Name: <YOUR_KEY_VAULT> (or your choice)
- [ ] Command: `az keyvault create --name <YOUR_KEY_VAULT> --resource-group rg-student-evaluation --location eastus`
- [ ] Google API key stored as secret "GOOGLEAPIKEY"
- [ ] Command: `az keyvault secret set --vault-name <YOUR_KEY_VAULT> --name GOOGLEAPIKEY --value "your-api-key"`
- [ ] Verify: `az keyvault secret show --vault-name <YOUR_KEY_VAULT> --name GOOGLEAPIKEY`

### Function App
- [ ] Function app created
- [ ] Name: <YOUR_FUNCTION_APP> (or your choice, must be globally unique)
- [ ] Runtime: Python 3.9
- [ ] Plan: Consumption (serverless)
- [ ] Command: `az functionapp create --resource-group rg-student-evaluation --consumption-plan-location eastus --runtime python --runtime-version 3.9 --functions-version 4 --name <YOUR_FUNCTION_APP> --storage-account <YOUR_STORAGE_ACCOUNT> --os-type Linux`
- [ ] Verify: `az functionapp show --name <YOUR_FUNCTION_APP> --resource-group rg-student-evaluation`

### Managed Identity
- [ ] Managed Identity enabled on Function App
- [ ] Command: `az functionapp identity assign --name <YOUR_FUNCTION_APP> --resource-group rg-student-evaluation`
- [ ] Principal ID copied (shown in output)
- [ ] Verify: `az functionapp identity show --name <YOUR_FUNCTION_APP> --resource-group rg-student-evaluation`

### Key Vault Access Policy
- [ ] Function App granted access to Key Vault
- [ ] Permissions: Get, List secrets
- [ ] Command: `az keyvault set-policy --name <YOUR_KEY_VAULT> --object-id <principal-id> --secret-permissions get list`
- [ ] Verify: Test accessing secret from function app

### Application Settings
- [ ] KEY_VAULT_URL configured in function app settings
- [ ] Command: `az functionapp config appsettings set --name <YOUR_FUNCTION_APP> --resource-group rg-student-evaluation --settings "KEY_VAULT_URL=https://<YOUR_KEY_VAULT>.vault.azure.net/"`
- [ ] Verify: `az functionapp config appsettings list --name <YOUR_FUNCTION_APP> --resource-group rg-student-evaluation`

---

## ✅ Testing Phase

### Local Testing
- [ ] Function runs locally without errors
- [ ] Test with sample image and PDF
- [ ] Verify prompt fetching works
- [ ] Verify Key Vault access (or local API key) works
- [ ] Verify Gemini API call succeeds
- [ ] Check response format is correct
- [ ] Test error handling (missing fields, invalid data)

### Test Cases
- [ ] Test Case 1: Valid request with PDF blob URL
- [ ] Test Case 2: Valid request with PDF bytes
- [ ] Test Case 3: Missing required field (should return 400)
- [ ] Test Case 4: Invalid image data (should return error)
- [ ] Test Case 5: Unreachable PDF URL (should return error)
- [ ] Test Case 6: Large image/PDF (check timeout handling)

### Performance Testing
- [ ] Measure average response time (should be 30-180 seconds)
- [ ] Test with different image sizes
- [ ] Test with different PDF sizes
- [ ] Verify timeout settings are appropriate

---

## ✅ Deployment

### Pre-Deployment
- [ ] All local tests passing
- [ ] Code committed to version control
- [ ] Azure resources created and verified
- [ ] Managed Identity and permissions configured
- [ ] Function app settings configured

### Deployment
- [ ] Deploy function: `func azure functionapp publish <YOUR_FUNCTION_APP>`
- [ ] Deployment succeeds without errors
- [ ] Verify deployment: Check Azure Portal

### Post-Deployment Verification
- [ ] Function appears in Azure Portal
- [ ] Function key retrieved: `az functionapp keys list --name <YOUR_FUNCTION_APP> --resource-group rg-student-evaluation`
- [ ] Test endpoint URL constructed: `https://<YOUR_FUNCTION_APP>.azurewebsites.net/api/evaluate?code=<function-key>`

---

## ✅ Production Testing

### Smoke Tests
- [ ] Call function with test payload
- [ ] Verify 200 response for valid request
- [ ] Verify 400 response for invalid request
- [ ] Check evaluation content is meaningful
- [ ] Verify logs in Azure Portal

### Integration Tests
- [ ] Test from actual client application
- [ ] Test with real student answer images
- [ ] Test with real chapter PDFs
- [ ] Verify end-to-end workflow

### Error Scenarios
- [ ] Test with missing image
- [ ] Test with invalid base64
- [ ] Test with missing PDF source
- [ ] Test with invalid Key Vault access (should log error)
- [ ] Test with invalid Gemini API key (should return error)

---

## ✅ Monitoring Setup

### Application Insights (Recommended)
- [ ] Application Insights created
- [ ] Command: `az monitor app-insights component create --app <YOUR_APP_INSIGHTS> --location eastus --resource-group rg-student-evaluation --application-type web`
- [ ] Linked to Function App
- [ ] Verify telemetry is being collected

### Alerts
- [ ] Set up alert for function failures
- [ ] Set up alert for high response times
- [ ] Set up alert for quota issues

### Logging
- [ ] Verify logs appear in Azure Portal
- [ ] Command to view: `az webapp log tail --name <YOUR_FUNCTION_APP> --resource-group rg-student-evaluation`
- [ ] Test log streaming

---

## ✅ Security Review

### Access Control
- [ ] Function-level authentication enabled (default)
- [ ] Function keys secured and not committed to code
- [ ] Key Vault access restricted to Function App Managed Identity
- [ ] No hardcoded secrets in code

### Network Security
- [ ] CORS configured if needed for web clients
- [ ] IP restrictions configured if needed
- [ ] HTTPS enforced (automatic for Azure Functions)

### Data Privacy
- [ ] Student data handling reviewed
- [ ] Ensure compliance with applicable regulations
- [ ] Consider data retention policies

---

## ✅ Documentation

### Code Documentation
- [ ] README.md complete and accurate
- [ ] DEPLOYMENT.md tested and verified
- [ ] QUICKSTART.md helpful for new users
- [ ] Code comments adequate

### Operational Documentation
- [ ] Deployment process documented
- [ ] Troubleshooting guide available
- [ ] Contact information for support

### User Documentation
- [ ] API endpoint documented
- [ ] Request/response format documented
- [ ] Error codes explained
- [ ] Client integration examples provided

---

## ✅ Production Readiness

### Performance
- [ ] Response times acceptable
- [ ] Timeout settings appropriate
- [ ] Concurrent request handling verified

### Reliability
- [ ] Error handling comprehensive
- [ ] Retry logic in clients (if needed)
- [ ] Graceful degradation on failures

### Scalability
- [ ] Consumption plan limits understood
- [ ] Scaling strategy defined if needed
- [ ] Cost estimates calculated

### Maintenance
- [ ] Update process defined
- [ ] Rollback plan in place
- [ ] Monitoring and alerting active

---

## ✅ Go-Live Checklist

### Final Checks
- [ ] All previous checklist items completed
- [ ] Production testing successful
- [ ] Stakeholders informed
- [ ] Support team briefed

### Go-Live
- [ ] Function URL shared with clients
- [ ] Function keys distributed securely
- [ ] Monitoring dashboard accessible
- [ ] On-call support arranged

### Post Go-Live
- [ ] Monitor for 24 hours
- [ ] Check error rates
- [ ] Review performance metrics
- [ ] Gather user feedback

---

## 📋 Quick Reference

### Important URLs
- Azure Portal: https://portal.azure.com
- Function App: `https://<YOUR_FUNCTION_APP>.azurewebsites.net`
- Key Vault: `https://<YOUR_KEY_VAULT>.vault.azure.net`
- Prompt Template: `https://<YOUR_STORAGE>.blob.core.windows.net/feedback/Evaluation.txt`

### Important Commands
```bash
# View logs
az webapp log tail --name <YOUR_FUNCTION_APP> --resource-group rg-student-evaluation

# Restart function app
az functionapp restart --name <YOUR_FUNCTION_APP> --resource-group rg-student-evaluation

# Update app settings
az functionapp config appsettings set --name <YOUR_FUNCTION_APP> --resource-group rg-student-evaluation --settings "KEY=VALUE"

# Get function keys
az functionapp keys list --name <YOUR_FUNCTION_APP> --resource-group rg-student-evaluation

# Redeploy
func azure functionapp publish <YOUR_FUNCTION_APP>
```

---

**Checklist Version**: 1.0  
**Last Updated**: November 12, 2025  
**Status**: Ready for use

---

## Sign-Off

- [ ] Developer: Verified all development tasks complete
- [ ] DevOps: Verified all infrastructure deployed correctly
- [ ] QA: Verified all tests passing
- [ ] Security: Verified security requirements met
- [ ] Product Owner: Approved for production deployment

**Date**: _______________

**Deployed By**: _______________

**Production URL**: _______________

**Notes**: _______________________________________________________________

___________________________________________________________________
