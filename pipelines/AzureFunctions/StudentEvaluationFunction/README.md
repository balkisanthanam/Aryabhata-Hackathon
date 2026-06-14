# Student Evaluation — Azure Durable Function (Python)

Fully standalone Python Azure Durable Function that evaluates student homework solutions against textbook problems using Google Gemini AI.

## Architecture (v4 — Unified Flow)

```
feedback-jobs queue → Queue Trigger → Durable Orchestrator
    → read_evaluation (DB: PENDING → PROCESSING)
    → fetch_student_images (download student HW pages)
    → fetch textbook images (optional — reuses fetch_student_images)
    → parse_text_ref (Gemini text parsing — always required)
    → validate_inputs (resolve class/board/subject/chapter)
    → get_chapter_pdf (DB lookup + blob fetch)
    → evaluate_batch ×N (fan-out, EVAL_BATCH_SIZE per call, default 3)
        ↑ ALL student pages sent to each batch
        ↑ Optional textbook page images as additional context
        ↑ Gemini locates relevant work on the pages
    → update_evaluation (DB: → COMPLETED/FAILED)
```

> **v4 Unified Flow**: `problem_text_ref` is always required.
> `problem_image_url` is optional — if provided, the textbook page image
> is fetched and sent to Gemini as additional visual context alongside
> student pages. No split/crop for either student or textbook images.

**Interface**: `solution_evaluations` table only. No HTTP calls to/from TS server.

## Prerequisites

- Python 3.10+
- Azure Functions Core Tools v4
- Azure CLI (logged in for `DefaultAzureCredential`)
- `feedback-jobs` queue exists in Azure Storage

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Start the function app
func start
```

## Testing

```bash
# Manual test: insert a test row + push to queue
python tests/test_durable_e2e.py --test manual

# Check status
python tests/test_durable_e2e.py --status <job_id>

# Full automated test
python tests/test_durable_e2e.py --test all

# Cleanup
python tests/test_durable_e2e.py --cleanup-only <job_id>
```

## File Structure

```
├── function_app.py           — Queue trigger + Durable Functions registration
├── orchestrator.py           — Orchestrator logic (v4 unified single flow)
├── host.json                 — Azure Functions host config
├── requirements.txt          — Python dependencies
├── local.settings.json       — Local environment variables
├── utils/
│   ├── gemini_client.py      — Gemini API with retry + Key Vault
│   ├── db.py                 — PostgreSQL with Azure AD token
│   ├── blob_storage.py       — Blob fetch with Managed Identity
│   ├── image_processing.py   — PIL crop/stitch (legacy, used by split_textbook)
│   └── prompt_loader.py      — Prompt loading + template fill
├── activities/
│   ├── read_evaluation.py    — Read DB record, set PROCESSING
│   ├── fetch_student_images.py — Download images (reused for textbook pages)
│   ├── split_student_hw.py   — Legacy: Gemini bounding box + PIL crop (unused)
│   ├── parse_text_ref.py     — Parse text reference to problem numbers
│   ├── split_textbook.py     — Legacy: Split textbook page image (unused in v4)
│   ├── validate_inputs.py    — Validate class/board/subject/chapter (v4: always requires parsed_ref)
│   ├── get_chapter_pdf.py    — Fetch chapter PDF
│   ├── evaluate_batch.py     — Unified multi-problem eval (v4: optional textbook pages)
│   ├── evaluate_batch_v1_split_based.py — Backup of pre-v3 eval
│   └── update_evaluation.py  — Update DB with results
├── prompts/
│   └── Evaluation.txt        — v4 evaluation prompt template
└── tests/
    ├── test_activities.py    — CLI tool for isolated activity testing (v4)
    ├── test_durable_e2e.py   — End-to-end test script
    └── ...                   — Legacy test helpers
```

## Gemini Models

| Task | Model |
|------|-------|
| Evaluation | `gemini-3-pro-image-preview` |
| Textbook bounding boxes | `gemini-3-pro-preview` |
| Text parsing | `gemini-2.5-flash-lite` |

## Key Decisions

See [PLAN.md](PLAN.md) for full architecture decisions and rationale.
