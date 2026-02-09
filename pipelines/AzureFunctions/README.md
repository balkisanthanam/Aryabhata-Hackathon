# Azure Functions for AryaBhatta Project

This directory contains Azure Functions for the AryaBhatta educational platform.

## Available Functions

### 1. StudentEvaluationFunction

**Purpose**: Evaluates student answers using Google Gemini AI

**Location**: `StudentEvaluationFunction/`

**Endpoint**: `POST /api/evaluate`

**Status**: ✅ Ready for deployment

**Documentation**: See [StudentEvaluationFunction/README.md](StudentEvaluationFunction/README.md)

**Quick Start**:
```powershell
cd StudentEvaluationFunction
pip install -r requirements.txt
func start
```

## Architecture Overview

```
AzureFunctions/
│
└── StudentEvaluationFunction/          # Student answer evaluation
    ├── function_app.py                 # Main function code
    ├── requirements.txt                # Dependencies
    ├── README.md                       # Full documentation
    ├── DEPLOYMENT.md                   # Deployment guide
    └── QUICKSTART.md                   # Quick reference
```

## Common Setup

### Prerequisites

1. [Azure Functions Core Tools](https://docs.microsoft.com/en-us/azure/azure-functions/functions-run-local)
2. Python 3.9+
3. Azure CLI (for deployment)
4. Azure subscription

### Local Development

Each function has its own `local.settings.json` that needs to be configured.

### Deployment

Each function can be deployed independently:

```powershell
cd <FunctionName>
func azure functionapp publish <azure-function-app-name>
```

## Azure Resources Required

All functions may need:

- Resource Group
- Storage Account (for Functions runtime)
- Function App (per function or shared)
- Key Vault (for secrets)
- Application Insights (recommended)

## Function Naming Convention

Function names follow the pattern: `<Capability><Type>`

Examples:
- `StudentEvaluationFunction`
- `QuestionGenerationFunction` (future)
- `ContentExtractionFunction` (future)

## Security

- All functions use Azure Managed Identity where possible
- Secrets stored in Azure Key Vault
- Function-level authentication enabled by default
- CORS configured per function requirements

## Monitoring

- Application Insights integration available
- Logs accessible via Azure Portal or CLI
- Custom metrics can be added per function

## Cost Management

- Most functions use Consumption Plan (pay-per-execution)
- Monitor execution counts and duration
- Set up budget alerts in Azure

## Support

For function-specific issues, see the README in each function's directory.

For general Azure Functions questions:
- [Azure Functions Documentation](https://docs.microsoft.com/en-us/azure/azure-functions/)
- [Python Developer Guide](https://docs.microsoft.com/en-us/azure/azure-functions/functions-reference-python)

---

**Last Updated**: November 12, 2025
