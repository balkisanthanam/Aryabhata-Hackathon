# Student Evaluation Azure Function - Quick Reference

## Project Structure

```
StudentEvaluationFunction/
├── function_app.py              # Main Azure Function code
├── requirements.txt             # Python dependencies
├── host.json                    # Function app configuration
├── local.settings.json          # Local development settings
├── .gitignore                   # Git ignore rules
├── README.md                    # Full documentation
├── DEPLOYMENT.md                # Deployment guide
├── test_create_payload.py       # Simple test payload creator
└── test_helper.py               # Advanced test helper with file encoding
```

## Key Features Implemented

✅ Fetches prompt template from Azure Blob Storage  
✅ Integrates with Azure Key Vault for secure API key retrieval  
✅ Uses Google Gemini 2.0 Flash model (upgrade to 2.5 Pro when available)  
✅ Accepts student answer image  
✅ Accepts chapter PDF via bytes or blob URL  
✅ Fills prompt placeholders: {class}, {Subject}, {Problem}, {RefAnswer}  
✅ Comprehensive error handling and validation  
✅ Returns detailed evaluation feedback  

## Quick Start

### 1. Install Dependencies
```powershell
cd c:\Bala\Coding\AryaBhatta\AzureFunctions\StudentEvaluationFunction
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Settings

Update `local.settings.json`:
```json
{
  "Values": {
    "KEY_VAULT_URL": "https://your-keyvault.vault.azure.net/",
    "GOOGLE_API_KEY": "your-api-key-for-local-testing"
  }
}
```

For local testing, modify `function_app.py` line ~20 to use environment variable:
```python
# For local testing, bypass Key Vault
import os
api_key = os.environ.get("GOOGLE_API_KEY", "")
if not api_key:
    api_key = get_api_key_from_keyvault()
```

### 3. Run Locally
```powershell
func start
```

### 4. Test
```powershell
python test_helper.py path\to\student_answer.jpg path\to\chapter.pdf
```

## API Endpoint

**POST** `/api/evaluate`

### Minimal Request Example
```json
{
  "image_bytes": "base64_encoded_image",
  "class": "10",
  "subject": "Mathematics",
  "problem": "Question text here",
  "reference_answer": "Expected answer",
  "pdf_blob_url": "https://blob-url/file.pdf"
}
```

### Response Example
```json
{
  "success": true,
  "evaluation": "Detailed feedback from Gemini..."
}
```

## Configuration Checklist

- [ ] Update `KEY_VAULT_URL` in `function_app.py`
- [ ] Store Google API key in Azure Key Vault as `GOOGLEAPIKEY`
- [ ] Enable Managed Identity on Function App
- [ ] Grant Key Vault access to Managed Identity
- [ ] Verify prompt URL is accessible: https://<YOUR_STORAGE>.blob.core.windows.net/feedback/Evaluation.txt

## Common Commands

### Local Development
```powershell
# Activate virtual environment
.venv\Scripts\activate

# Install/update dependencies
pip install -r requirements.txt

# Start function locally
func start

# View logs
# (logs appear in terminal when running locally)
```

### Deployment
```powershell
# Deploy to Azure
func azure functionapp publish <your-function-app-name>

# View remote logs
az webapp log tail --name <function-app-name> --resource-group <resource-group>
```

## Important Notes

### Security
- **Never commit** `local.settings.json` with real credentials
- Use Azure Key Vault for production API keys
- Use Managed Identity in Azure (avoid storing credentials in code)

### Limitations (Current Version)
- `problem_images` - Not yet implemented
- `reference_answer_images` - Not yet implemented
- Batch processing - Not yet implemented

### Model Information
- Currently uses: `gemini-2.0-flash-exp`
- Update to `gemini-2.5-pro` when available (line 66 in `function_app.py`)

## Troubleshooting

### Function won't start
- Check Python version: `python --version` (need 3.9+)
- Verify Azure Functions Core Tools: `func --version`
- Check all dependencies installed: `pip list`

### Key Vault access denied
- Verify Managed Identity is enabled
- Check Key Vault access policies
- Ensure `GOOGLEAPIKEY` secret exists

### Gemini API errors
- Verify API key is valid
- Check quota limits
- Ensure model name is correct

### Large file timeout
- Default timeout is 5 minutes (consumption plan)
- Consider smaller images/PDFs
- Or use Azure Durable Functions for longer processing

## Next Steps

1. **Test with real data**: Replace test files with actual student answers and chapters
2. **Deploy to Azure**: Follow DEPLOYMENT.md for production setup
3. **Add image support**: Implement `problem_images` and `reference_answer_images`
4. **Add monitoring**: Set up Application Insights dashboards
5. **Optimize costs**: Monitor usage and adjust plan if needed

## Support Files

- **README.md** - Full feature documentation
- **DEPLOYMENT.md** - Step-by-step Azure deployment guide
- **test_create_payload.py** - Simple test payload generator
- **test_helper.py** - Advanced testing with real files

## Links

- [Azure Functions Python Developer Guide](https://docs.microsoft.com/en-us/azure/azure-functions/functions-reference-python)
- [Google Gemini API Documentation](https://ai.google.dev/docs)
- [Azure Key Vault Documentation](https://docs.microsoft.com/en-us/azure/key-vault/)
