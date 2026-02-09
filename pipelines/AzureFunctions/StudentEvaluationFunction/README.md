# Azure Function: Student Answer Evaluation

This Azure Function evaluates student answers using Google Gemini AI model.

## Features

- Accepts student's handwritten answer as image
- Compares against reference answer
- Uses chapter PDF for context
- Provides detailed feedback and solution
- Integrates with Azure Key Vault for secure API key storage

## Prerequisites

1. Azure Functions Core Tools
2. Python 3.9 or higher
3. Azure Key Vault with `GOOGLEAPIKEY` secret
4. Google Gemini API access

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Update `local.settings.json` with your Key Vault URL

3. Ensure you have access to Azure Key Vault with the Google API key stored as `GOOGLEAPIKEY`

## Configuration

Update the following in `function_app.py`:
- `KEY_VAULT_URL`: Your Azure Key Vault URL

The prompt template is automatically fetched from:
`https://<YOUR_STORAGE>.blob.core.windows.net/feedback/Evaluation.txt`

## API Endpoint

**POST** `/api/evaluate`

### Request Body

```json
{
  "image_bytes": "base64_encoded_student_answer_image",
  "class": "10",
  "subject": "Mathematics",
  "problem": "Solve the quadratic equation: x^2 + 5x + 6 = 0",
  "reference_answer": "x = -2, x = -3",
  "pdf_bytes": "base64_encoded_pdf_optional",
  "pdf_blob_url": "https://your-blob-url.com/chapter.pdf"
}
```

### Required Fields

- `image_bytes`: Base64 encoded image of student's answer (JPEG/PNG)
- `class`: Student's class (e.g., "10", "12", "JEEMain")
- `subject`: Subject name (e.g., "Mathematics", "Physics")
- `problem`: The problem statement (can include LaTeX formulas)
- `reference_answer`: Expected answer for comparison

### Optional Fields (one required)

- `pdf_bytes`: Base64 encoded PDF of the chapter
- `pdf_blob_url`: Azure Blob Storage URL of the chapter PDF

### Response

#### Success (200)
```json
{
  "success": true,
  "evaluation": "Detailed evaluation feedback from Gemini..."
}
```

#### Error (400/500)
```json
{
  "success": false,
  "error": "Error message"
}
```

## Local Testing

1. Start the function locally:
```bash
func start
```

2. Send a test request:
```bash
curl -X POST http://localhost:7071/api/evaluate \
  -H "Content-Type: application/json" \
  -d @test_request.json
```

## Deployment

Deploy to Azure:
```bash
func azure functionapp publish <YOUR_FUNCTION_APP_NAME>
```

## Security Notes

- API key is stored securely in Azure Key Vault
- Function uses Function-level authentication
- Use Azure Managed Identity for production deployments
- Ensure blob storage has appropriate access controls

## Future Enhancements

- Support for `problem_images` (additional images for problem)
- Support for `reference_answer_images` (additional images for reference answer)
- Batch evaluation support
- Response caching

## Troubleshooting

### Key Vault Access Issues
Ensure your Azure Function has proper permissions:
- Enable Managed Identity on Function App
- Grant "Key Vault Secrets User" role to the identity

### Gemini API Issues
- Verify API key is valid
- Check Gemini model availability (update model name if needed)
- Review API quotas and limits

## Model Information

Currently using: `gemini-2.0-flash-exp`
Update to `gemini-2.5-pro` when available.
