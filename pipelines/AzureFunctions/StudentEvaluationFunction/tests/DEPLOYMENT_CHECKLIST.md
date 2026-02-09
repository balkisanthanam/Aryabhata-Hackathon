# Deployment Checklist - Problem Image Feature

## Pre-Deployment

- [ ] **Review Changes**
  - [x] Updated `function_app.py` with problem image support
  - [x] Optimized `Evaluation.txt` prompt for multimodal
  - [x] Created test scripts and documentation
  - [ ] Review all code changes for correctness

- [ ] **Local Testing** (Optional but Recommended)
  ```powershell
  cd <LOCAL_PATH>\AzureFunctions\StudentEvaluationFunction
  func start
  ```
  Then in another terminal:
  ```powershell
  python tests\test_with_problem_image.py
  ```

## Deployment Steps

### Step 1: Upload Updated Prompt to Blob Storage

```powershell
az storage blob upload `
  --account-name <YOUR_STORAGE> `
  --container-name feedback `
  --name Evaluation.txt `
  --file "<LOCAL_PATH>\Feedback\Prompt\Evaluation.txt" `
  --overwrite `
  --auth-mode login
```

**Verify:**
```powershell
# Check file was uploaded
az storage blob show --account-name <YOUR_STORAGE> --container-name feedback --name Evaluation.txt --auth-mode login --query properties.contentLength
```

### Step 2: Deploy Function App

```powershell
cd <LOCAL_PATH>\AzureFunctions\StudentEvaluationFunction
func azure functionapp publish <YOUR_FUNCTION_APP>
```

**Expected Output:**
- ✅ Build succeeds
- ✅ Dependencies installed
- ✅ Function deployed
- ✅ Invoke URL shown

### Step 3: Verify Deployment

```powershell
# Check function is running
az functionapp function show `
  --name <YOUR_FUNCTION_APP> `
  --resource-group rg-student-evaluation `
  --function-name evaluate_student_answer `
  --query "{name:name, status:properties.state}"
```

## Post-Deployment Testing

### Test 1: Backward Compatibility (Text Problem)

```powershell
cd tests
python test_prod.py `
  "<LOCAL_PATH>\Feedback\Data\PhysicsSample1.jpg" `
  "https://<YOUR_STORAGE>.blob.core.windows.net/feedback/11/Physics/keph204.pdf" `
  "<LOCAL_PATH>\Feedback\Data\ProblemFile.txt"
```

**Expected Result:**
- ✅ Status 200
- ✅ Evaluation returned
- ✅ Same behavior as before

### Test 2: New Feature (Problem Image)

```powershell
python test_with_problem_image.py
```

**Expected Result:**
- ✅ Status 200
- ✅ Evaluation considers problem image
- ✅ Response shows understanding of visual elements

### Test 3: Curl Test (Integration)

```powershell
# Create payload with problem text
python create_curl_payload.py `
  "<LOCAL_PATH>\Feedback\Data\PhysicsSample1.jpg" `
  "https://<YOUR_STORAGE>.blob.core.windows.net/feedback/11/Physics/keph204.pdf" `
  "<LOCAL_PATH>\Feedback\Data\ProblemFile.txt"

# Send request
.\test_curl.ps1

# Check response
cat response.json
```

## Validation Checklist

- [ ] **Function Deployed Successfully**
  - [ ] No deployment errors
  - [ ] Function shows as "Running" in Azure Portal

- [ ] **Prompt Template Updated**
  - [ ] New Evaluation.txt uploaded to blob storage
  - [ ] File size increased (new prompt is longer)

- [ ] **Backward Compatibility**
  - [ ] Text-only problems still work
  - [ ] Same JSON response structure
  - [ ] No breaking changes

- [ ] **New Feature Works**
  - [ ] Problem image accepted
  - [ ] Gemini processes multimodal input
  - [ ] Evaluation considers visual elements

- [ ] **Error Handling**
  - [ ] Missing both problem text and image returns error
  - [ ] Invalid base64 image returns clear error
  - [ ] All edge cases handled gracefully

## Rollback Plan (If Needed)

If issues occur:

### Rollback Prompt

```powershell
# Restore old prompt from backup
az storage blob upload `
  --account-name <YOUR_STORAGE> `
  --container-name feedback `
  --name Evaluation.txt `
  --file "<LOCAL_PATH>\Feedback\Prompt\Evaluation.txt.backup" `
  --overwrite `
  --auth-mode login
```

### Rollback Function

```powershell
# Revert to previous commit
cd <LOCAL_PATH>\AzureFunctions\StudentEvaluationFunction
git log --oneline  # Find previous commit hash
git checkout <previous-commit-hash> function_app.py

# Redeploy
func azure functionapp publish <YOUR_FUNCTION_APP>
```

## Post-Deployment Monitoring

### Check Function Logs

```powershell
az functionapp log tail `
  --name <YOUR_FUNCTION_APP> `
  --resource-group rg-student-evaluation
```

**Look for:**
- ✅ Successful evaluations
- ⚠️ Any errors or warnings
- ⚠️ Performance issues

### Monitor Costs

```powershell
# Check Azure consumption
az consumption usage list `
  --start-date 2025-11-25 `
  --end-date 2025-11-26 `
  --query "[?contains(instanceName, '<YOUR_FUNCTION_APP>')]"
```

**Monitor:**
- Function execution time
- Gemini API usage
- Bandwidth consumption

## Documentation Updates

- [x] Created PROBLEM_IMAGE_FEATURE.md
- [x] Created ENHANCEMENT_SUMMARY.md
- [x] Created DEPLOYMENT_CHECKLIST.md
- [ ] Update main README.md with new feature
- [ ] Add example problem images to repository

## Communication

After successful deployment:

- [ ] **Notify Users/Team**
  - New capability available
  - API changes documented
  - Example use cases shared

- [ ] **Update Integration Docs**
  - Client libraries
  - API documentation
  - Example code snippets

## Success Criteria

✅ Deployment is successful if:
1. Function deploys without errors
2. Backward compatibility maintained (text problems work)
3. New feature functional (image problems work)
4. No performance degradation
5. Error handling works correctly
6. Documentation complete and accurate

## Timeline

- **Estimated Deployment Time**: 5-10 minutes
- **Estimated Testing Time**: 10-15 minutes
- **Total Time**: 15-25 minutes

## Notes

- Deployment can be done during low-usage periods
- No downtime expected (Azure handles seamless deployment)
- Function key remains unchanged
- Managed Identity permissions unchanged
