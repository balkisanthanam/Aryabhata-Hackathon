# On-Demand Image Extraction Azure Function

This Azure Function extracts specific problem images from educational PDF documents on-demand. It uses Google Gemini 2.0 Flash Experimental model to identify problem locations and PyMuPDF to extract high-quality images.

## Features

- **AI-Powered Extraction**: Uses Google Gemini to intelligently locate problems in PDF documents
- **Precise Bounding Box Detection**: Extracts exact regions containing problems, including multi-page problems
- **High-Quality Image Output**: Returns 300 DPI PNG images
- **Azure Integration**: Fetches PDFs from Azure Blob Storage and uses Azure Key Vault for API keys
- **Multi-Segment Support**: Handles problems that span multiple pages by stitching images vertically

## API Endpoint

**URL**: `/api/extract_image`  
**Method**: `POST`  
**Content-Type**: `application/json`

### Request Body

```json
{
  "pdf_blob_url": "https://<YOUR_STORAGE>.blob.core.windows.net/feedback/11/Maths/kemh106.pdf",
  "exercise_name": "Exercise 8.1",
  "problem_number": "12"
}
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pdf_blob_url` | string | Yes | Full Azure Blob Storage URL of the PDF file |
| `exercise_name` | string | Yes | Name of the exercise section (e.g., "Exercise 8.1", "Chapter 11 Exercises") |
| `problem_number` | string | Yes | Problem number to extract (e.g., "12", "11.8") |

### Response

**Success (200 OK)**
- **Content-Type**: `image/png`
- **Body**: Binary PNG image data
- **Headers**: 
  - `Content-Disposition`: `inline; filename=problem_{number}.png`

**Error (400 Bad Request)**
```json
{
  "error": "Missing required fields: problem_number"
}
```

**Error (422 Unprocessable Entity)**
```json
{
  "success": false,
  "error": "No segments found in Gemini response",
  "raw_response": {...}
}
```

**Error (500 Internal Server Error)**
```json
{
  "success": false,
  "error": "Error message details"
}
```

## How It Works

1. **Fetch PDF**: Downloads the PDF from Azure Blob Storage
2. **Load Prompt**: Retrieves the extraction prompt template from blob storage
3. **Call Gemini API**: Sends the PDF and problem context to Gemini 2.0 Flash Experimental
4. **Parse Coordinates**: Extracts bounding box coordinates from Gemini's JSON response
5. **Crop Image**: Uses PyMuPDF to crop the specified regions at 300 DPI
6. **Stitch (if needed)**: Vertically combines multiple segments for multi-page problems
7. **Return Image**: Sends the PNG image back to the client

## Bounding Box Format

Gemini returns coordinates in a normalized 0-1000 scale:

```json
{
  "problem_id": "12",
  "segments": [
    {
      "page_number": 8,
      "bbox": [150, 100, 300, 900]
    }
  ]
}
```

- **bbox format**: `[ymin, xmin, ymax, xmax]`
- **Coordinate system**: Top-left is (0,0), bottom-right is (1000,1000)
- **Multiple segments**: Supported for problems spanning multiple pages

## Setup and Configuration

### Prerequisites

- Python 3.9 or higher
- Azure Functions Core Tools
- Azure subscription with:
  - Azure Key Vault (for Google API key)
  - Azure Blob Storage (for PDFs and prompts)

### Environment Variables

Configure in `local.settings.json` for local development:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "GEMINI_MODEL": "gemini-3-pro-preview"
  }
}
```

**Available Gemini Models:**
- `gemini-3-pro-preview` - Primary model, most capable and accurate (default)
- `gemini-2.5-pro` - Fallback model, stable alternative

**To change the model:** Update `GEMINI_MODEL` in `local.settings.json` for local testing, or set it in Azure Portal → Configuration → Application Settings for production.

### Azure Configuration

Update these constants in `function_app.py`:

```python
KEY_VAULT_URL = os.environ.get("KEY_VAULT_URL", "https://<YOUR_KEY_VAULT>.vault.azure.net/")
KEY_VAULT_SECRET_NAME = os.environ.get("KEY_VAULT_SECRET_NAME", "GOOGLEAPIKEY")
PROMPT_BLOB_URL = os.environ.get("PROMPT_BLOB_URL", "https://<YOUR_STORAGE>.blob.core.windows.net/feedback/ExtractionPipeline/ImageBasedExtraction/prompts/OnDemandImage_prompt.txt")
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-3-pro-preview')  # Configurable via environment
```

### Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run locally:
```bash
func start
```

### Deployment

Deploy to Azure:
```bash
func azure functionapp publish <your-function-app-name>
```

## Example Usage

### Using cURL

```bash
curl -X POST "http://localhost:7071/api/extract_image" \
  -H "Content-Type: application/json" \
  -d '{
    "pdf_blob_url": "https://<YOUR_STORAGE>.blob.core.windows.net/feedback/11/Maths/kemh106.pdf",
    "exercise_name": "Exercise 8.1",
    "problem_number": "12"
  }' \
  --output problem_12.png
```

### Using Python

```python
import requests

url = "http://localhost:7071/api/extract_image"
payload = {
    "pdf_blob_url": "https://<YOUR_STORAGE>.blob.core.windows.net/feedback/11/Maths/kemh106.pdf",
    "exercise_name": "Exercise 8.1",
    "problem_number": "12"
}

response = requests.post(url, json=payload)

if response.status_code == 200:
    with open("problem_12.png", "wb") as f:
        f.write(response.content)
    print("Image saved successfully!")
else:
    print(f"Error: {response.json()}")
```

### Using JavaScript/TypeScript

```typescript
async function extractProblemImage(
  pdfUrl: string, 
  exercise: string, 
  problemNum: string
): Promise<Blob> {
  const response = await fetch('http://localhost:7071/api/extract_image', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      pdf_blob_url: pdfUrl,
      exercise_name: exercise,
      problem_number: problemNum,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error);
  }

  return response.blob();
}

// Usage
const imageBlob = await extractProblemImage(
  'https://<YOUR_STORAGE>.blob.core.windows.net/feedback/11/Maths/kemh106.pdf',
  'Exercise 8.1',
  '12'
);

// Display in browser
const imageUrl = URL.createObjectURL(imageBlob);
document.getElementById('problemImage').src = imageUrl;
```

## Dependencies

- **azure-functions**: Azure Functions Python SDK
- **azure-identity**: Managed Identity authentication
- **azure-keyvault-secrets**: Key Vault integration
- **azure-storage-blob**: Blob Storage client
- **google-generativeai**: Google Gemini API client
- **PyMuPDF**: PDF processing and image extraction
- **Pillow**: Image manipulation and stitching
- **requests**: HTTP client for blob fetching

## Prompt Template

The function uses a specialized prompt stored at:
```
ExtractionPipeline/ImageBasedExtraction/prompts/OnDemandImage_prompt.txt
```

The prompt instructs Gemini to:
- Locate the exercise section in the PDF
- Find the specific problem number
- Identify precise bounding boxes for all problem components
- Handle multi-page problems by returning multiple segments

## Troubleshooting

### Common Issues

1. **"No segments found in Gemini response"**
   - The exercise name or problem number may not exist in the PDF
   - Check the exact spelling and formatting of the exercise name

2. **"Error retrieving API key from Key Vault"**
   - Ensure Managed Identity is enabled on the Function App
   - Verify the Function App has "Get" permissions on Key Vault secrets

3. **"Error fetching blob"**
   - Check that the PDF URL is accessible
   - Verify Managed Identity has "Storage Blob Data Reader" role if using private blobs

4. **"Failed to parse Gemini response as JSON"**
   - The model may have returned text instead of JSON
   - Check the prompt template and ensure it requests JSON output

## Performance Considerations

- **PDF Size**: Large PDFs (>50 MB) may take longer to process
- **DPI Setting**: Currently set to 300 DPI for high quality; adjust in `get_pixmap(dpi=300)` if needed
- **Timeout**: Default Azure Functions timeout is 5 minutes (configurable in host.json)
- **Cold Start**: First request may take 10-15 seconds due to cold start

## Security

- API keys are stored securely in Azure Key Vault
- Uses Managed Identity for authentication (no hardcoded credentials)
- Function-level authentication required (auth level in URL)
- Supports both public and private blob access

## License

Part of the AryaBhatta educational platform.
