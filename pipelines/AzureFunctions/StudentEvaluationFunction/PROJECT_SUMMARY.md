# Azure Function Project Summary

## Overview
This Azure Function evaluates student answers using Google Gemini AI. It compares handwritten student solutions against reference answers and provides detailed feedback using chapter context from PDFs.

## ✅ Implementation Status

### Core Features Implemented
- [x] HTTP trigger Azure Function endpoint (`/api/evaluate`)
- [x] Azure Blob Storage integration (fetches prompt template)
- [x] Azure Key Vault integration (secure API key retrieval)
- [x] Google Gemini 2.0 Flash integration
- [x] Base64 image input handling
- [x] PDF input via bytes or blob URL
- [x] Prompt template placeholder replacement
- [x] Comprehensive error handling
- [x] Input validation
- [x] Structured JSON responses

### Deferred Features (Future Iterations)
- [ ] `problem_images` support (additional problem images)
- [ ] `reference_answer_images` support (additional reference images)
- [ ] Batch processing endpoint
- [ ] Response caching
- [ ] Webhook notifications

## 📁 Project Structure

```
AzureFunctions/StudentEvaluationFunction/
│
├── function_app.py              # Main Azure Function (200+ lines)
│   ├── get_api_key_from_keyvault()    # Retrieves GOOGLEAPIKEY from Azure Key Vault
│   ├── fetch_prompt_from_blob()        # Gets Evaluation.txt from blob storage
│   ├── fill_prompt_template()          # Replaces {class}, {Subject}, etc.
│   ├── decode_base64_image()           # Decodes base64 image strings
│   ├── evaluate_with_gemini()          # Calls Gemini API
│   └── evaluate_student_answer()       # HTTP trigger endpoint
│
├── requirements.txt             # Python dependencies
│   ├── azure-functions
│   ├── azure-identity
│   ├── azure-keyvault-secrets
│   ├── google-generativeai
│   └── requests
│
├── host.json                    # Function app runtime configuration
├── local.settings.json          # Local development settings
├── .gitignore                   # Excludes sensitive files
│
├── README.md                    # Full documentation with API details
├── DEPLOYMENT.md                # Step-by-step Azure deployment guide
├── QUICKSTART.md                # Quick reference for developers
│
├── check_config.py              # Configuration validation script
├── test_create_payload.py       # Simple test payload generator
└── test_helper.py               # Advanced testing with file encoding
```

## 🔄 Data Flow

```
1. Client Request
   └─> POST /api/evaluate with JSON payload
       ├─> image_bytes (base64)
       ├─> class, subject, problem, reference_answer
       └─> pdf_bytes OR pdf_blob_url

2. Function Processing
   ├─> Validate inputs
   ├─> Decode base64 image
   ├─> Fetch PDF (from blob URL or decode from bytes)
   ├─> Fetch prompt template from Azure Blob Storage
   ├─> Fill prompt placeholders
   ├─> Retrieve Google API key from Azure Key Vault
   └─> Call Gemini API with prompt + image + PDF

3. Gemini Processing
   ├─> Analyzes student's handwritten answer
   ├─> Compares with reference answer
   ├─> Uses chapter PDF for context
   └─> Generates detailed feedback

4. Response
   └─> JSON response with evaluation results
```

## 🔐 Security Architecture

```
Azure Function (Managed Identity)
    ↓
Azure Key Vault
    └─> Secret: GOOGLEAPIKEY (Google API Key)
    
Azure Blob Storage (Public Read)
    └─> Prompt Template: Evaluation.txt

Google Gemini API
    └─> Authenticates with GOOGLEAPIKEY
```

## 📊 Input Specifications

### Required Fields
| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `image_bytes` | string | Base64 encoded student answer image | "iVBORw0KGgo..." |
| `class` | string | Student's class/grade | "10", "12", "JEEMain" |
| `subject` | string | Subject name | "Mathematics", "Physics" |
| `problem` | string | Problem statement (can include LaTeX) | "Solve: x^2 + 5x + 6 = 0" |
| `reference_answer` | string | Expected answer | "x = -2, x = -3" |

### Optional Fields (one required)
| Field | Type | Description |
|-------|------|-------------|
| `pdf_bytes` | string | Base64 encoded chapter PDF |
| `pdf_blob_url` | string | Azure Blob URL of chapter PDF |

### Future Fields (Not Yet Implemented)
- `problem_images`: List of base64 encoded images for problem
- `reference_answer_images`: List of base64 encoded images for reference answer

## 🚀 Deployment Requirements

### Azure Resources
1. **Resource Group**: Container for all resources
2. **Storage Account**: Required by Azure Functions
3. **Key Vault**: Stores Google API key securely
4. **Function App**: Hosts the function (Python 3.9+)
5. **Application Insights**: (Optional) For monitoring

### Configuration Steps
1. Create Azure resources (see DEPLOYMENT.md)
2. Enable Managed Identity on Function App
3. Grant Key Vault access to Managed Identity
4. Store Google API key in Key Vault as `GOOGLEAPIKEY`
5. Update `KEY_VAULT_URL` in function_app.py
6. Deploy function: `func azure functionapp publish <app-name>`

## 🧪 Testing

### Local Testing
```powershell
# 1. Activate virtual environment
.venv\Scripts\activate

# 2. Check configuration
python check_config.py

# 3. Start function
func start

# 4. Test with sample data
python test_helper.py path\to\image.jpg path\to\chapter.pdf
```

### Azure Testing
```bash
curl -X POST "https://<function-app>.azurewebsites.net/api/evaluate?code=<key>" \
  -H "Content-Type: application/json" \
  -d @test_request.json
```

## 📝 Prompt Template

Location: `https://<YOUR_STORAGE>.blob.core.windows.net/feedback/Evaluation.txt`

Placeholders:
- `{class}` → Replaced with student's class
- `{Subject}` → Replaced with subject name
- `{Problem}` → Replaced with problem statement
- `{RefAnswer}` → Replaced with reference answer

## 🔧 Configuration Files

### function_app.py
- Update `KEY_VAULT_URL` with your Key Vault URL
- Update model name when Gemini 2.5 Pro is available (line 66)

### local.settings.json (for local testing)
```json
{
  "Values": {
    "KEY_VAULT_URL": "https://your-kv.vault.azure.net/",
    "GOOGLE_API_KEY": "your-key-for-local-testing"
  }
}
```

### Azure Function App Settings (production)
```
KEY_VAULT_URL = https://your-kv.vault.azure.net/
(Managed Identity handles authentication)
```

## 📈 Performance Considerations

- **Timeout**: 5 minutes (consumption plan default)
- **Image Size**: Recommend < 5MB for optimal performance
- **PDF Size**: Recommend < 10MB for optimal performance
- **Concurrent Requests**: Limited by consumption plan (default 200)

## 💰 Cost Estimation

### Azure Functions (Consumption Plan)
- $0.20 per million executions
- $0.000016 per GB-second of execution
- First 1 million executions free

### Azure Key Vault
- $0.03 per 10,000 operations
- First 1,000 operations free

### Google Gemini API
- Check current pricing at ai.google.dev

## 🛠️ Troubleshooting

### Common Issues

1. **Key Vault Access Denied**
   - Ensure Managed Identity is enabled
   - Check access policies in Key Vault
   - Verify secret name is exactly "GOOGLEAPIKEY"

2. **Gemini API Errors**
   - Verify API key is valid
   - Check quota limits
   - Ensure model name is correct

3. **Function Timeout**
   - Reduce image/PDF sizes
   - Consider Azure Durable Functions for longer processing

4. **Cannot Fetch Prompt**
   - Verify blob URL is accessible
   - Check network connectivity from function

## 📚 Documentation Files

| File | Purpose | Audience |
|------|---------|----------|
| `README.md` | Complete feature documentation | All users |
| `DEPLOYMENT.md` | Step-by-step Azure setup | DevOps/Admins |
| `QUICKSTART.md` | Quick reference guide | Developers |
| `PROJECT_SUMMARY.md` | This file - overview | Technical leads |

## 🔄 Next Steps

### Immediate
1. Test with real student answers and PDFs
2. Deploy to Azure and verify end-to-end
3. Set up monitoring and alerts

### Short-term
1. Implement `problem_images` support
2. Implement `reference_answer_images` support
3. Add caching for repeated evaluations
4. Create front-end interface

### Long-term
1. Batch processing endpoint
2. Async processing with queues
3. Multi-language support
4. Integration with student management system

## 👥 Contact & Support

For issues or questions:
1. Review documentation in README.md, DEPLOYMENT.md, QUICKSTART.md
2. Check configuration with: `python check_config.py`
3. Review Azure Function logs in Azure Portal

## 📄 License & Usage

Internal project for educational evaluation purposes.
Ensure compliance with:
- Google Gemini API Terms of Service
- Azure Services Terms
- Data privacy regulations for student information

---

**Project Created**: November 12, 2025  
**Version**: 1.0.0  
**Status**: ✅ Ready for deployment
