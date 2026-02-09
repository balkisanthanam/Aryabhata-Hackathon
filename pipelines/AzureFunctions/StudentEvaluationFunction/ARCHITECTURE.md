# Student Evaluation Function - Architecture Diagram

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              CLIENT APPLICATION                          │
│  (Web App / Mobile App / Python Script / API Gateway)                   │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
                              │ HTTP POST /api/evaluate
                              │ Content-Type: application/json
                              │ {
                              │   "image_bytes": "base64...",
                              │   "class": "10",
                              │   "subject": "Mathematics",
                              │   "problem": "...",
                              │   "reference_answer": "...",
                              │   "pdf_blob_url": "https://..."
                              │ }
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     AZURE FUNCTION APP                                   │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  StudentEvaluationFunction                                        │  │
│  │  Runtime: Python 3.9                                              │  │
│  │  Trigger: HTTP POST                                               │  │
│  │  Auth: Function Key                                               │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                              │                                           │
│        ┌─────────────────────┼─────────────────────┐                    │
│        │                     │                     │                    │
│        ▼                     ▼                     ▼                    │
│  ┌──────────┐         ┌──────────┐          ┌──────────┐               │
│  │ Validate │         │  Decode  │          │  Fetch   │               │
│  │  Inputs  │────────▶│  Images  │──────────▶│   PDF    │               │
│  └──────────┘         └──────────┘          └──────────┘               │
│                                                    │                    │
└────────────────────────────────────────────────────┼────────────────────┘
                                                     │
                    ┌────────────────────────────────┼────────────────┐
                    │                                │                │
                    ▼                                ▼                ▼
    ┌──────────────────────────┐    ┌───────────────────────┐   ┌────────────────┐
    │   AZURE KEY VAULT        │    │  AZURE BLOB STORAGE   │   │ EXTERNAL PDF   │
    │                          │    │                       │   │   (Optional)   │
    │  Secret: GOOGLEAPIKEY     │    │  Evaluation.txt       │   │                │
    │  (Google API Key)        │    │  (Prompt Template)    │   │  Chapter PDF   │
    │                          │    │                       │   │                │
    │  Auth: Managed Identity  │    │  Access: Public Read  │   │ Via Blob URL   │
    └────────────┬─────────────┘    └───────────┬───────────┘   └────────┬───────┘
                 │                              │                        │
                 └──────────────┬───────────────┘                        │
                                │                                        │
                                ▼                                        │
    ┌─────────────────────────────────────────────────────────────────────┐
    │                    FUNCTION PROCESSING                               │
    │                                                                      │
    │  1. Retrieve API Key from Key Vault                                 │
    │  2. Fetch Prompt Template from Blob Storage                         │
    │  3. Fill Placeholders: {class}, {Subject}, {Problem}, {RefAnswer}   │
    │  4. Prepare Content: Prompt + Student Image + Chapter PDF           │
    │                                                                      │
    └───────────────────────────────────┬──────────────────────────────────┘
                                        │
                                        ▼
                        ┌───────────────────────────────┐
                        │   GOOGLE GEMINI API           │
                        │                               │
                        │   Model: gemini-2.0-flash-exp │
                        │   (upgrade to 2.5-pro later)  │
                        │                               │
                        │   Input:                      │
                        │   - Filled Prompt             │
                        │   - Student Answer Image      │
                        │   - Chapter PDF               │
                        │                               │
                        │   Output:                     │
                        │   - Detailed Evaluation       │
                        │   - Feedback                  │
                        │   - Solution Steps            │
                        └────────────┬──────────────────┘
                                     │
                                     ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │                        RESPONSE                                      │
    │                                                                      │
    │  Success (200):                                                     │
    │  {                                                                   │
    │    "success": true,                                                 │
    │    "evaluation": "The student's solution is correct..."             │
    │  }                                                                   │
    │                                                                      │
    │  Error (400/500):                                                   │
    │  {                                                                   │
    │    "success": false,                                                │
    │    "error": "Error description"                                     │
    │  }                                                                   │
    └─────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
                        ┌─────────────────┐
                        │  CLIENT APP     │
                        │  Displays       │
                        │  Evaluation     │
                        └─────────────────┘
```

## Data Flow Sequence

```
1. CLIENT                                 2. AZURE FUNCTION
   │                                         │
   ├─ Prepare Request                       │
   │  • Convert image to base64             │
   │  • Prepare problem text                │
   │  • Include PDF URL/bytes               │
   │                                         │
   ├─ HTTP POST ──────────────────────────▶ ├─ Receive Request
   │                                         │
   │                                         ├─ Validate Inputs
   │                                         │  ✓ image_bytes exists
   │                                         │  ✓ Required fields present
   │                                         │  ✓ PDF source available
   │                                         │
   │                                         ├─ Decode Base64
   │                                         │  • Student answer image
   │                                         │  • PDF (if provided as bytes)
   │                                         │
   │                            ┌────────────┼─ Fetch Resources
   │                            │            │  ├─▶ Key Vault (API Key)
   │                            │            │  ├─▶ Blob Storage (Prompt)
   │                            │            │  └─▶ PDF Source
   │                            │            │
   │                            └────────────┼─ Fill Prompt Template
   │                                         │  • Replace {class}
   │                                         │  • Replace {Subject}
   │                                         │  • Replace {Problem}
   │                                         │  • Replace {RefAnswer}
   │                                         │
   │                                         ├─ Call Gemini API
   │                                         │  • Send prompt
   │                                         │  • Send student image
   │                                         │  • Send chapter PDF
   │                                         │
   │                            ┌────────────┼─ Wait for AI Response
   │                            │            │  (Can take 30-180 seconds)
   │                            │            │
   │                            └────────────┼─ Process Response
   │                                         │  • Extract evaluation
   │                                         │  • Format JSON
   │                                         │
   ├─ Receive Response ◀──────────────────── ├─ Return Result
   │                                         │
   ├─ Display Evaluation                    │
   │  • Show feedback                        │
   │  • Highlight errors                     │
   │  • Provide solution                     │
   │                                         │
```

## Component Responsibilities

```
┌─────────────────────────────────────────────────────────────────┐
│  COMPONENT             │  RESPONSIBILITY                         │
├────────────────────────┼─────────────────────────────────────────┤
│  Client Application    │  • Capture student answer image         │
│                        │  • Prepare problem and reference        │
│                        │  • Call Azure Function                  │
│                        │  • Display evaluation results           │
├────────────────────────┼─────────────────────────────────────────┤
│  Azure Function        │  • Validate inputs                      │
│                        │  • Orchestrate workflow                 │
│                        │  • Handle errors                        │
│                        │  • Return formatted response            │
├────────────────────────┼─────────────────────────────────────────┤
│  Azure Key Vault       │  • Store Google API key securely        │
│                        │  • Provide Managed Identity access      │
├────────────────────────┼─────────────────────────────────────────┤
│  Azure Blob Storage    │  • Host prompt template                 │
│                        │  • Optionally host chapter PDFs         │
├────────────────────────┼─────────────────────────────────────────┤
│  Google Gemini API     │  • Analyze student answer               │
│                        │  • Compare with reference               │
│                        │  • Generate detailed feedback           │
│                        │  • Provide solution steps               │
└────────────────────────┴─────────────────────────────────────────┘
```

## Deployment Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                    AZURE RESOURCE GROUP                            │
│  Name: rg-student-evaluation                                      │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  Azure Function App                                          │ │
│  │  Name: <YOUR_FUNCTION_APP>                               │ │
│  │  Plan: Consumption (Serverless)                              │ │
│  │  Runtime: Python 3.9                                         │ │
│  │  Region: East US                                             │ │
│  │                                                              │ │
│  │  Settings:                                                   │ │
│  │    KEY_VAULT_URL = https://<YOUR_KEY_VAULT>.vault.azure.net/ │ │
│  │                                                              │ │
│  │  Identity:                                                   │ │
│  │    Managed Identity: ENABLED                                │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  Azure Key Vault                                             │ │
│  │  Name: <YOUR_KEY_VAULT>                                       │ │
│  │  SKU: Standard                                               │ │
│  │                                                              │ │
│  │  Secrets:                                                    │ │
│  │    GOOGLEAPIKEY = <google-api-key>                           │ │
│  │                                                              │ │
│  │  Access Policies:                                            │ │
│  │    Function App MI: Get, List Secrets                       │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  Storage Account                                             │ │
│  │  Name: <YOUR_STORAGE_ACCOUNT>                                   │ │
│  │  SKU: Standard_LRS                                           │ │
│  │  Purpose: Function app storage                               │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  Application Insights (Optional)                             │ │
│  │  Name: <YOUR_APP_INSIGHTS>                            │ │
│  │  Purpose: Monitoring and diagnostics                         │ │
│  └──────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│                  EXTERNAL RESOURCES                                │
│                                                                    │
│  Azure Blob Storage (<YOUR_STORAGE> account)                            │
│    Container: feedback                                            │
│    File: Evaluation.txt                                           │
│    Access: Public Read                                            │
│                                                                    │
│  Google Cloud                                                     │
│    Service: Gemini API                                            │
│    Model: gemini-2.0-flash-exp                                    │
│    Auth: API Key from Key Vault                                   │
└───────────────────────────────────────────────────────────────────┘
```

## Error Handling Flow

```
Request ──▶ Validation ──▶ Process ──▶ Response
              │              │
              │ FAIL         │ ERROR
              │              │
              ▼              ▼
         ┌─────────────────────────┐
         │   Error Response        │
         │   HTTP 400/500          │
         │   {                     │
         │     "success": false,   │
         │     "error": "..."      │
         │   }                     │
         └─────────────────────────┘
              │
              ▼
         ┌─────────────────────────┐
         │   Logging               │
         │   • App Insights        │
         │   • Function Logs       │
         │   • Error Tracking      │
         └─────────────────────────┘
```

---

This architecture ensures:
- ✅ Secure API key management
- ✅ Scalable serverless processing
- ✅ Comprehensive error handling
- ✅ Easy monitoring and debugging
- ✅ Cost-effective pay-per-use model
