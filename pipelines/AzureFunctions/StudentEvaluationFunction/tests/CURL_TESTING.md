# Testing with curl

This guide shows how to test the Azure Function using curl from any machine.

## Quick Start

### 1. Create the JSON payload

```bash
# On the machine with the test image
python create_curl_payload.py path/to/student_answer.jpg
```

This creates `payload.json` with your image encoded as base64.

### 2. Run the test

**On Windows (PowerShell):**
```powershell
.\test_curl.ps1
```

**On Linux/Mac/Git Bash:**
```bash
bash test_curl.sh
```

**Manual curl command:**
```bash
curl -X POST "https://<YOUR_FUNCTION_APP>.azurewebsites.net/api/evaluate?code=<YOUR_FUNCTION_KEY>" \
     -H "Content-Type: application/json" \
     -d @payload.json \
     -o response.json
```

## Testing from a Different Machine

### Option A: Transfer the payload file

1. Create `payload.json` on a machine with the test image:
   ```bash
   python create_curl_payload.py student_answer.jpg
   ```

2. Copy `payload.json` to the other machine (via USB, email, etc.)

3. Run curl on the other machine:
   ```bash
   curl -X POST "https://<YOUR_FUNCTION_APP>.azurewebsites.net/api/evaluate?code=YOUR_KEY" \
        -H "Content-Type: application/json" \
        -d @payload.json
   ```

### Option B: Manual payload creation

On any machine with the image file:

```bash
# Encode image to base64
base64 student_answer.jpg > image_base64.txt

# Or on Windows PowerShell:
[Convert]::ToBase64String([IO.File]::ReadAllBytes("student_answer.jpg")) > image_base64.txt
```

Then create `payload.json` manually:
```json
{
  "image_bytes": "<paste base64 string here>",
  "pdf_blob_url": "https://<YOUR_STORAGE_ACCOUNT>.blob.core.windows.net/feedback/sample-chapter.pdf",
  "class": "10",
  "subject": "Mathematics",
  "problem": "Solve: 2x + 5 = 15",
  "reference_answer": "x = 5"
}
```

## Payload Format

The JSON payload must include:

```json
{
  "image_bytes": "base64_encoded_image_string",
  "pdf_blob_url": "https://...",  // OR "pdf_bytes": "base64_encoded_pdf"
  "class": "10",
  "subject": "Mathematics",
  "problem": "The problem statement",
  "reference_answer": "The correct answer"
}
```

## Response Format

Successful response (HTTP 200):
```json
{
  "status": "success",
  "feedback": "Gemini's feedback here...",
  "solution": "Gemini's solution here..."
}
```

Error response (HTTP 400/500):
```json
{
  "status": "error",
  "message": "Error description"
}
```

## Troubleshooting

### "Connection refused" or timeout
- Check the function URL is correct
- Verify the function app is running: `az functionapp show --name <YOUR_FUNCTION_APP> --resource-group <YOUR_RESOURCE_GROUP>`

### "Unauthorized" (HTTP 401)
- Check the function key is correct
- Get the latest key: `az functionapp keys list --name <YOUR_FUNCTION_APP> --resource-group <YOUR_RESOURCE_GROUP>`

### "Bad Request" (HTTP 400)
- Verify the JSON payload is valid
- Check that image_bytes is properly base64 encoded
- Ensure either pdf_bytes or pdf_blob_url is provided (not both)

### Response is too slow
- The function may be cold-starting (first request after idle)
- Large files take longer to process
- Gemini API calls can take 30-60 seconds

## Function Details

- **URL**: https://<YOUR_FUNCTION_APP>.azurewebsites.net/api/evaluate
- **Method**: POST
- **Auth**: Function key in query string `?code=...`
- **Timeout**: 5 minutes (300 seconds)
- **Max payload size**: ~50 MB (Azure Functions limit)

## Security Notes

⚠️ **The function key in these scripts is a secret!**

- Don't commit it to public repositories
- Rotate it periodically: `az functionapp keys renew --name <YOUR_FUNCTION_APP> --resource-group <YOUR_RESOURCE_GROUP> --key-name default`
- Use environment variables for CI/CD pipelines
